import json
import librosa
import sounddevice as sd
import soundfile as sf
import time
import numpy as np

from utils.Dynamixelutils import dynamixel
from dynamixel_sdk import *                    # Uses Dynamixel SDK library
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer



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
    min = 320
    max = 341
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

with open("danceModes.json", "r") as f:
    DANCE_MODES = json.load(f)

def get_audio_info(audio_filepath: str):
    print("Extracting audio features...")
    audio, sr = librosa.load(audio_filepath, sr=None)

    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sr)
    tempo = tempo
    print(f"Detected BPM: {tempo}")

    # First beat time in seconds
    if len(beat_frames) > 0:
        first_beat_s = librosa.frames_to_time(beat_frames[0], sr=sr)
    else:
        first_beat_s = 0.0
    print(f"detected first beat at {first_beat_s:.3f}s")

    duration_s = len(audio) / sr
    print(f"detected duration: {duration_s}s")

    return tempo, duration_s, first_beat_s


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


# [bpm1, bpm2, bpm3]
# [startsec1, startsec2, startsec3]
def osc_dance(unused_addr, *args):
    """
    Usage:
      /dance mode audio_filepath
      /dance mode bpm duration_s
    """
    
    if len(args) < 2:
        raise ValueError("OSC /dance requires at least 2 arguments")

    mode = args[0]
    if mode not in DANCE_MODES:
        raise ValueError(f"Mode '{mode}' not found!")

    if isinstance(args[1], str):
        audio_filepath = args[1]
        bpm_raw, duration_s, first_beat_s = get_audio_info(audio_filepath)
        use_audio = True
    elif len(args) >= 3:
        bpm_raw = int(args[1])
        duration_s = int(args[2])
        first_beat_s = 0.0    
        use_audio = False
    else:
        raise ValueError(
            "Invalid OSC args. Use (mode, audio_filepath) or (mode, bpm, duration_s)"
        )

    if bpm_raw <= 10 or bpm_raw > 300:
        raise ValueError(f"Invalid BPM: {bpm_raw}")
    if duration_s <= 0:
        raise ValueError(f"Invalid duration: {duration_s}")
    print(f"OSC dance: mode={mode}, bpm={bpm_raw}, duration={duration_s}")


    # neutral position
    moveHeadTurn(-1, 0.5, 0.02, 0)
    moveHeadTilt(-1, 0.5, 0.02, 0)
    moveMouth(-1, 0.5, 0.02, 0)
    moveNeckTurn(-1, 0.5, 0.02, 1)
    # moveNeckTilt(-1, 0.5, 0.02, 1)

    bpm_min = DANCE_MODES[mode]["bpm_min"]
    bpm_max = DANCE_MODES[mode]["bpm_max"]
    bpm = normalize_bpm(bpm_raw, bpm_min, bpm_max)

    print(
        f"BPM mapping: audio BPM {bpm_raw} → dance BPM {bpm} "
        f"(range {bpm_min}-{bpm_max} defined in danceModes.json)"
    )

    events = DANCE_MODES[mode]["moves"]
    beat_to_sec = 60 / bpm
    next_tick_time = 0.0

    scaled_events = []
    for e in events:
        scaled_start = e["startBeat"] * beat_to_sec
        scaled_period = e["periodBeat"] * beat_to_sec
        scaled_events.append({
            "motor": e["motor"],
            "start_s": scaled_start,
            "period_s": scaled_period,
            "position": e["position"],
            "velocity": e["velocity"]
        })

    if use_audio:
        data, sr = play_audio(audio_filepath)
        time.sleep(first_beat_s)  # wait until first beat

    try:
        start_time = time.time()
        print(f"Starting dance mode '{mode}' at {bpm} BPM for {duration_s} seconds...")

        while True:
            t = time.time() - start_time
            if t >= duration_s - first_beat_s:
                print("reached maximum duration, stopping robot movement")
                break

            if not use_audio and t >= next_tick_time:
                play_tick()
                next_tick_time += beat_to_sec

            for i, e in enumerate(scaled_events):
                if t >= e["start_s"]:
                    n = int((t - e["start_s"]) / e["period_s"])
                    next_trigger = e["start_s"] + n * e["period_s"]
                    if 0 <= t - next_trigger < 0.07:  # trigger window
                        motor = MOTOR_MAP[e["motor"]]
                        vel = e["velocity"]
                        motor(-1, e["position"], vel, 0)

            time.sleep(0.01)
    finally:
        if use_audio:
            sd.wait()  # blocks until playback finishes

modes = {
    1: "nod_sway",
    2: "head_circle",
    3: "ar_sway",
    4: "lq_sway",
    5: "circle",
    6: "build"
}
song_list = {
    1: "./data/bedroomTalk_opening.wav",
    2: "./data/janeDoe.wav",
    3: "./data/supernatural_opening.wav",
    4: "./data/tattoo_opening.wav",
    5: "./data/weWillRockYou.wav",
    6: "./data/byeSummer_opening.wav",
}

if __name__ == "__main__":
    dispatcher.map("/dance", osc_dance)

    NeckTilt.initmotor()
    HeadTurn.initmotor()

    for motor in motors:
        print(f"Enabling torque for motor ID {motor.ID}")
        motor.enable_torque()

    try:
        server = BlockingOSCUDPServer(("127.0.0.1", 9010), dispatcher)
        # server.serve_forever()  # Blocks forever
        osc_dance("/dance", modes[6], song_list[6])
        # osc_dance("/dance", modes[5], 35, 24)
    except:
        print("Caught exception")
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
