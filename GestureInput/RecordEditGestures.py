# This file is an extension from Shaiahead that allows Gesture Editing during playback.

import json
import os
import threading
import time

import sounddevice as sd
import numpy as np

from utils.Dynamixelutils import dynamixel
from dynamixel_sdk import *                    # Uses Dynamixel SDK library
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

dispatcher = Dispatcher()

# ===========
#   MOTORS 
# ===========
port = '/dev/tty.usbserial-FT62AP2P'
packethandle = PacketHandler(2.0)
porthandle = PortHandler(port)

HeadTurn = dynamixel(10,porthandle,packethandle,BAUD = 57600)
HeadTilt = dynamixel(11,porthandle,packethandle,BAUD = 57600)
Mouth    = dynamixel(12,porthandle,packethandle,BAUD = 57600)
NeckTilt = dynamixel(13,porthandle,packethandle,BAUD = 57600)
NeckTurn = dynamixel(14,porthandle,packethandle,BAUD = 57600)

HEAD_MOTORS = [HeadTurn, HeadTilt, Mouth]
NECK_MOTORS = [NeckTurn, NeckTilt]

# motors to disable torque during recording (they don't need to hold against gravity)
nonGravityMotors = [HeadTurn, HeadTilt, Mouth, NeckTurn]
# motors to switch to current-based position mode during recording for holding with current
gravityMotors = [NeckTilt]
motors = nonGravityMotors + gravityMotors


# HeadTurn 100-260
# Headtilt 3) 64-140
# Mouth 2) 320-341
# Neck tilt 156-210
# Neck turn 85-193

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


# =========================
#   RECORD MODE VARIABLES 
# ========================
CURRENT_BASED_POSITION_MODE = 5
# P GAIN - Soft holding; lower -> returns more slowly
POSITION_P_GAIN = 50 
# GOAL CURRENT - Total force Dynamixel uses for its motions; lower -> more pushable
GOAL_CURRENT_NECK = 50
# GOAL_CURRENT_HEAD = 0 

RECORD_DT = 0.005 # record delta time / interval
MAX_RECORD_TIME = 600 # seconds
# Recording state
is_recording = False
recorded_frames = []
# OSC control
playback_on = False  # disable OSC during playback
motor_settings_snapshots = {}
save_path = "GestureInput/recorded_frames.json"

# =====================
#   THREADING LOCKS
# =====================
state_lock = threading.Lock()   # protects shared runtime state
file_lock = threading.Lock()    # protects file read/write
port_lock = threading.Lock()    # protects Dynamixel serial communication

# ==========
#    STOP
# ==========

def osc_stop(unused_addr, *args):
    global is_recording, playback_on
    print("User stopped recording/playback")
    with state_lock:
        is_recording = False
        playback_on = False

# ==========
#   RECORD
# ==========

def enter_record_mode():
    global motor_settings_snapshots

    print(f"Moving to neutral position...")
    with port_lock:
        # neutral position
        moveHeadTurn(-1, 0.5, 0.25, 0)
        moveHeadTilt(-1, 0.5, 0.25, 0)
        moveMouth(-1, 0.5, 0.25, 0)
        moveNeckTurn(-1, 0.5, 0.01, 0)
        moveNeckTilt(-1, 0.8, 0.01, 1)

    print(f"Entering record mode")
    with port_lock:
    # some of the head motors have high gear ratio, so disabling the torque to make them more pushable
        for m in nonGravityMotors:
            m.disable_torque()
        # motors like neck tilt is more prone to gravity, so switch to current-based position mode for some resisting force
        for m in gravityMotors:
            snapshot = m.snapshot_settings()

            # protect dictionary write only
            with state_lock:
                motor_settings_snapshots[m.ID] = snapshot

            m.set_operating_mode(CURRENT_BASED_POSITION_MODE)
            m.set_p_gain(POSITION_P_GAIN)
            m.set_goal_current(GOAL_CURRENT_NECK)
        
def exit_record_mode():
    global motor_settings_snapshots
    print("Exiting record mode.")
    
    with port_lock:
        for m in nonGravityMotors:
            m.enable_torque()
        for m in gravityMotors:
            with state_lock:
                snapshot = motor_settings_snapshots.get(m.ID)
            if snapshot:
                m.restore_settings(snapshot)
    # clear dictionary safely
    with state_lock:
        motor_settings_snapshots = {}
    print("Restored all motors to settings before the record.")

    try:
        with file_lock:
            with open(save_path, "w") as f:
                json.dump(recorded_frames, f, indent=2)
        print(f"Saved recorded frames to {os.path.abspath(save_path)}")
    except Exception as e:
        print(f"Error saving recorded frames: {e}")

def record_loop():
    global recorded_frames, is_recording
    enter_record_mode()
    start_time = time.time()
    print(f"Starting to record movements of motors {[m.ID for m in motors]}")

    while True:
        with state_lock:
            if not is_recording or (time.time() - start_time >= MAX_RECORD_TIME):
                break

        frame = {}
        for m in motors:
            with port_lock:
                frame[str(m.ID)] = m.read_position()
        frame["t"] = time.perf_counter()

        with state_lock:
            recorded_frames.append(frame)

        time.sleep(RECORD_DT)

    with state_lock:
        if is_recording:
            print(f"Reached max record time of {MAX_RECORD_TIME} seconds, stopping recording.")
            is_recording = False

    exit_record_mode()

def osc_record(unused_addr, *args):
    global is_recording, recorded_frames
    with state_lock:
        if is_recording or playback_on:
            print("Recording/Playback in progress, skipping command. To execute command, run /stop first.")
            return
        print("User triggered record")
        recorded_frames = []
        is_recording = True
    # Run in a separate thread so the OSC server stays responsive
    threading.Thread(target=record_loop, daemon=True).start()

# ==========
#   EDIT
# ==========
editing_group = []
edited_frames = {} 
# {
#   <frame_i>: {
#       {
#           <motor_id>: <motor_pos>,
#           <motor_id>: <motor_pos>,
#           <motor_id>: <motor_pos>
#       }
#   }
# }
def osc_edit_neck(unused_addr, *args):
    start_edit_group(NECK_MOTORS)

def osc_edit_head(unused_addr, *args):
    start_edit_group(HEAD_MOTORS)

def osc_stop_edit(unused_addr, *args):
    stop_edit_group()

def start_edit_group(motor_group):
    global editing_group, motor_settings_snapshots
    with state_lock:
        editing_group = motor_group

    print(f"Motors {[m.ID for m in editing_group]} entering edit/record mode")
    for m in motor_group:
        with port_lock:
            if m in nonGravityMotors:
                m.disable_torque()
            if m in gravityMotors:
                snapshot = m.snapshot_settings()
                # set mode/current while still in port lock
                m.set_operating_mode(CURRENT_BASED_POSITION_MODE)
                m.set_p_gain(POSITION_P_GAIN)  
                m.set_goal_current(GOAL_CURRENT_NECK)
                with state_lock:
                    motor_settings_snapshots[m.ID] = snapshot

def stop_edit_group():
    global editing_group, edited_frames, recorded_frames, motor_settings_snapshots

    print(f"Restoring motors {[m.ID for m in editing_group]} from edit/record mode")

    for m in editing_group:
        with port_lock:
            if m in nonGravityMotors:
                m.enable_torque()
        if m in gravityMotors:
            with state_lock:
                snapshot = motor_settings_snapshots.get(m.ID)
            if snapshot:
                with port_lock:
                    m.restore_settings(snapshot)

    print("Merging edited frames with recorded frames")

    with state_lock:
        for frame_i, motors_new_pos in edited_frames.items():
            if frame_i < len(recorded_frames):
                recorded_frames[frame_i].update(motors_new_pos)

    print(f"Finished editing motors: {[m.ID for m in editing_group]}")

    try:
        with file_lock:
            with open(save_path, "w") as f:
                json.dump(recorded_frames, f, indent=2)
        print(f"Saved recorded frames after editing to {os.path.abspath(save_path)}")
    except Exception as e:
        print(f"Error saving recorded frames after editing: {e}")

    with state_lock:
        editing_group = []
        edited_frames = {}
        motor_settings_snapshots = {}

# ==========
#  PLAYBACK
# ==========
def play_ting(duration=0.05, freq=1000, sample_rate=44100, volume=0.3):
    """
    Play a short sine wave 'ting'
    duration: seconds
    freq: Hz
    sample_rate: audio sample rate
    volume: 0.0 - 1.0
    """
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    wave = np.sin(2 * np.pi * freq * t) * volume
    sd.play(wave, samplerate=sample_rate)
    # Do not block, playback continues asynchronously

def playback():
    global is_recording, playback_on, recorded_frames, editing_group, edited_frames
    print(f"Starting to playback the recorded movements of motors {[m.ID for m in motors]}")
    
    with state_lock:
        is_recording = False
        playback_on = True

    i = 0  # frame index

    while True:
        with state_lock:
            if not playback_on:
                break
            if i >= len(recorded_frames):
                # if len(editing_group) > 0:
                #     # We can either break here (stop playback entirely), or just stop the editing mode.
                #     # stop_edit_group()
                #     print("Editing should not exceed original length of recording. Stopping playback and editing...")
                #     break
                play_ting()  # play short "ting" to signal iteration
                i = 0 

            if len(recorded_frames) == 0:
                break

            frame = recorded_frames[i]
            current_editing_group = list(editing_group)

        for m in motors:
            if m in current_editing_group:
                # read current position while editing
                with port_lock:
                    pos = m.read_position()
                with state_lock:
                    edited_frame = edited_frames.get(i, {})
                    edited_frame[str(m.ID)] = pos
                    edited_frames[i] = edited_frame
            else:
                # regular playback
                with port_lock:
                    m.moveto(frame[str(m.ID)], convertToTick=False)

        time.sleep(RECORD_DT)
        i += 1

    with state_lock:
        playback_on = False
        editing_active = len(editing_group) > 0

    if editing_active:
        stop_edit_group()

    print("Playback finished")

def osc_play(unused_addr, *args):
    global is_recording, playback_on, recorded_frames
    with state_lock:
        if is_recording or playback_on:
            print("Recording/Playback in progress, skipping command. To execute command, run /stop first.")
            return
    print("User triggered playback")
    try:
        with file_lock:
            with open(save_path, "r") as f:
                loaded = json.load(f)
        with state_lock:
            recorded_frames = loaded
        print(f"Read recorded frames from {save_path}")
    except Exception as e:
        print(f"Error reading recorded frames: {e}")
        return
    
    # Run in a separate thread so the OSC server stays responsive
    threading.Thread(target=playback, daemon=True).start()


if __name__ == "__main__":
    dispatcher.map("/record", osc_record)
    dispatcher.map("/stop", osc_stop)
    dispatcher.map("/play", osc_play)

    dispatcher.map("/editNeck", osc_edit_neck)
    dispatcher.map("/editHead", osc_edit_head)
    dispatcher.map("/stopEdit", osc_stop_edit)

    # server = BlockingOSCUDPServer(("127.0.0.1", 9000), dispatcher)

    NeckTilt.initmotor()
    HeadTurn.initmotor()

    for motor in motors:
        print(f"Enabling torque for motor ID {motor.ID}")
        motor.enable_torque()

    try:
        server = BlockingOSCUDPServer(("127.0.0.1", 9010), dispatcher)
        server.serve_forever()  # Blocks forever
    except:
        if is_recording:
            exit_record_mode()
        moveNeckTilt(-1, 0, 0.01, 1)
        for motor in motors:
            motor.disable_torque()
        NeckTilt.shutdownSeq()
        HeadTurn.shutdownSeq()
    finally:
        if is_recording:
            exit_record_mode()
        moveNeckTilt(-1, 0, 0.01, 1)
        for motor in motors:
            motor.disable_torque()
        NeckTilt.shutdownSeq()
        HeadTurn.shutdownSeq()
