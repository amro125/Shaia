import json
import librosa
import random
import sounddevice as sd
import soundfile as sf
import time
import numpy as np

from utils.Dynamixelutils import dynamixel
from concurrent.futures import ThreadPoolExecutor
from dynamixel_sdk import *                    # Uses Dynamixel SDK library
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from Dance.AudioAnalysis import get_audio_sections, lip_sync

# ===========
#   MOTORS 
# ===========
port = '/dev/tty.usbserial-FT62AP2P'
packethandle = PacketHandler(2.0)
porthandle = PortHandler(port)

if not porthandle.openPort():
    raise RuntimeError(f"Failed to open port {port}")

if not porthandle.setBaudRate(57600):
    raise RuntimeError(f"Failed to set baudrate for port {port}")

dispatcher = Dispatcher()

HeadTurn = dynamixel(10,porthandle,packethandle,BAUD = 57600)
HeadTilt = dynamixel(11,porthandle,packethandle,BAUD = 57600)
Mouth    = dynamixel(12,porthandle,packethandle,BAUD = 57600)
NeckTilt = dynamixel(13,porthandle,packethandle,BAUD = 57600)
NeckTurn = dynamixel(14,porthandle,packethandle,BAUD = 57600)
motors = [HeadTurn, HeadTilt, Mouth, NeckTurn, NeckTilt]


def moveHeadTurn(unused_addr, *args):
    min = 100
    max = 260
    pos = args[0]
    goal = pos * (max - min) + min
    print(f"Head turn goal: {goal}")
    velocity = args[1]
    wait = True if args[2] == 1 else False
    HeadTurn.moveto(goal,wait=wait,velocity=velocity)

def moveHeadTilt(unused_addr, *args):
    min = 140
    max = 64
    pos = args[0]
    goal = pos * (max - min) + min
    print(f"Head tilt goal: {goal}")
    velocity = args[1]
    wait = True if args[2] == 1 else False
    HeadTilt.moveto(goal,wait=wait,velocity=velocity)

def moveMouth(unused_addr, *args):
    min = 341
    max = 320
    pos = args[0]
    goal = pos * (max - min) + min
    print(f"Mouth goal: {goal}")
    velocity = args[1]
    wait = True if args[2] == 1 else False
    Mouth.moveto(goal,wait=wait,velocity=velocity)

def moveNeckTilt(unused_addr, *args):
    min = 156
    max = 210
    pos = args[0]
    goal = pos * (max - min) + min
    print(f"Neck tilt goal: {goal}")
    velocity = args[1]
    wait = True if args[2] == 1 else False
    NeckTilt.moveto(goal,wait=wait,velocity=velocity)

def moveNeckTurn(unused_addr, *args):
    min = 85
    max = 193
    pos = args[0]
    goal = pos * (max - min) + min
    print(f"Neck turn goal: {goal}")
    velocity = args[1]
    wait = True if args[2] == 1 else False
    NeckTurn.moveto(goal,wait=wait,velocity=velocity)


# ==================
#   DANCE MOVES 
# ==================
MOTOR_MAP = {
    "HeadTurn": moveHeadTurn,
    "HeadTilt": moveHeadTilt,
    "NeckTurn": moveNeckTurn,
    "NeckTilt": moveNeckTilt,
    "Mouth": moveMouth
}

with open("Dance/danceModes.json", "r") as f:
    DANCE_MODES = json.load(f)

def normalize_bpm(bpm, bpm_min, bpm_max):
    """
    Fold BPM by factors of 2 until it fits nicely in [bpm_min, bpm_max].
    """
    dance_bpm = bpm

    # Fold down (too fast → half-time)
    while dance_bpm > bpm_max:
        dance_bpm /= 2

    # Fold up (too slow → double-time)
    while dance_bpm < bpm_min:
        dance_bpm *= 2

    return dance_bpm

def play_audio(audio_filepath):
    data, samplerate = sf.read(audio_filepath, dtype='float32')
    sd.play(data, samplerate)
    return data, samplerate

def make_tick(sr=44100, freq=1000, duration=0.03):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tick = 0.5 * np.sin(2 * np.pi * freq * t)
    return tick.astype(np.float32), sr

TICK_SOUND, TICK_SR = make_tick()
def play_tick():
    sd.play(TICK_SOUND, TICK_SR, blocking=False)

def schedule_dance_moves(tempo_sections, section_modes, duration_s, scale=1.0):
    sections_schedule = []
    for i, section in enumerate(tempo_sections):
        section_start = section['start_s']
        section_end = tempo_sections[i+1]['start_s'] if i+1 < len(tempo_sections) else duration_s
        mode = section_modes[i]
        bpm_val = section['bpm']
        bpm_min = DANCE_MODES[mode]['bpm_min']
        bpm_max = DANCE_MODES[mode]['bpm_max']
        bpm = normalize_bpm(bpm_val, bpm_min, bpm_max)
        beat_to_sec = 60 / bpm
        
        # precompute scaled events
        events = []
        for e in DANCE_MODES[mode]['moves']:

            base_pos = e['position']
            scaled_pos = 0.5 + (base_pos - 0.5) * scale
            scaled_pos = max(0.0, min(1.0, scaled_pos))

            events.append({
                'motor': e['motor'],
                'start_s': section_start + e['startBeat']*beat_to_sec,
                'period_s': e['periodBeat']*beat_to_sec,
                'position': scaled_pos,
                'velocity': e['velocity']
            })
        
        section_json = {
            'start_s': section_start,
            'end_s': section_end,
            'mode': mode,
            'bpm_val': bpm_val,
            'bpm': bpm,
            'beat_to_sec': beat_to_sec,
            'events': events
        }
        sections_schedule.append(section_json)

        print(f"Section {i}: BPM={bpm}; StartTime={section_start}s; Mode={mode}.")

    return sections_schedule

LIP_SYNC_ADVANCE_TIME = 0.2

def osc_dance(unused_addr, *args):
    """
    Usage:
      # USE CASE 1: /dance test duration_s mode1 bpm1 start1 mode2 bpm2 start2 ...
      # USE CASE 2: /dance audio_filepath
    """
    
    if len(args) < 1:
        raise ValueError("OSC /dance requires at least 1 arguments")
    
    audio_filepath = args[0]
    env_times, env_values = lip_sync(audio_filepath, threshold=0.05)

    # neutral position
    moveHeadTurn(-1, 0.5, 0.02, 0)
    moveHeadTilt(-1, 0.5, 0.02, 0)
    moveMouth(-1, 0, 0.02, 0)
    moveNeckTurn(-1, 0.5, 0.02, 0)
    moveNeckTilt(-1, 0.5, 0.02, 1)

    data, sr = play_audio(audio_filepath)
    audio, sr = librosa.load(audio_filepath, sr=None)
    duration_s = len(audio) / sr

    try:
        start_time = time.time()
        mouth_idx = -1
        while True:
            t = time.time() - start_time
            if t >= duration_s:
                print("reached maximum duration, stopping robot movement")
                break
            
            # lip syncing
            if len(env_times) > 0 and mouth_idx + 1 < len(env_times) and t >= env_times[mouth_idx + 1] - LIP_SYNC_ADVANCE_TIME:
                mouth_idx += 1
                moveMouth(-1, env_values[mouth_idx], 0.1, 0)
            time.sleep(0.01)
    finally:
        sd.wait()  # blocks until playback finishes

if __name__ == "__main__":
    dispatcher.map("/dance", osc_dance)

    NeckTilt.initmotor()
    HeadTurn.initmotor()

    for motor in motors:
        print(f"Enabling torque for motor ID {motor.ID}")
        motor.enable_torque()

    song_list = {
        1: "./data/bedroomTalk_opening.wav",
        2: "./data/janeDoe.wav",
        3: "./data/supernatural_opening.wav",
        4: "./data/tattoo_opening.wav",
        5: "./data/weWillRockYou_opening.wav",
        6: "./data/byeSummer_opening.wav",
        7: "./data/tattoo.wav",
        8: "./data/bedroomTalk.wav",
        9: "./data/weWillRockYou.wav",
        10: "./data/needYouNow.wav"
    }
    try:
        server = BlockingOSCUDPServer(("127.0.0.1", 9010), dispatcher)
        # server.serve_forever()  # Blocks forever

        # /dance audio_filepath
        osc_dance("/dance", song_list[8])

    except Exception as e:
        print(f"Caught exception: {e}")
        moveNeckTilt(-1, 0, 0.01, 1)
        for motor in motors:
            motor.disable_torque()
        NeckTilt.shutdownSeq()
        HeadTurn.shutdownSeq()
    finally:
        print("Cleaning up")
        moveNeckTilt(-1, 0, 0.01, 1)
        for motor in motors:
            motor.disable_torque()
        NeckTilt.shutdownSeq()
        HeadTurn.shutdownSeq()
