import json
import os
import threading
import time

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
MAX_RECORD_TIME = 30  # seconds
# Recording state
is_recording = False
recorded_frames = []
# OSC control
playback_on = False  # disable OSC during playback
snapshots_before_record = {}
save_path = "GestureInput/recorded_frames.json"

def enter_record_mode():
    print(f"Moving to neutral position...")
    # neutral position
    moveHeadTurn(-1, 0.5, 0.25, 0)
    moveHeadTilt(-1, 0.5, 0.25, 0)
    moveMouth(-1, 0.5, 0.25, 0)
    moveNeckTurn(-1, 0.5, 0.02, 0)
    moveNeckTilt(-1, 0.8, 0.02, 1)

    print(f"Entering record mode")
    # some of the head motors have high gear ratio, so disabling the torque to make them more pushable
    for m in nonGravityMotors:
        m.disable_torque()
    # motors like neck tilt is more prone to gravity, so switch to current-based position mode for some resisting force
    for m in gravityMotors:
        snapshots_before_record[m.ID] = m.snapshot_settings()
        m.set_operating_mode(CURRENT_BASED_POSITION_MODE)
        m.set_p_gain(POSITION_P_GAIN)  
        m.set_goal_current(GOAL_CURRENT_NECK) 
        
def exit_record_mode():
    print(f"Exiting record mode.")
    for m in nonGravityMotors:
        m.enable_torque()
    for m in gravityMotors:
        snapshot = snapshots_before_record.get(m.ID)
        if snapshot:
            m.restore_settings(snapshot)
    snapshots_before_record.clear()
    print(f"Restored all motors to settings before the record.")
    try:
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
    while is_recording and (time.time() - start_time < MAX_RECORD_TIME):
        frame = {str(m.ID): m.read_position() for m in motors}
        frame["t"] = time.perf_counter()
        recorded_frames.append(frame)
        time.sleep(RECORD_DT)
    if is_recording:  # automatically stop if time limit exceeded
        print(f"Reached max record time of {MAX_RECORD_TIME} seconds, stopping recording.")
        is_recording = False
    exit_record_mode()

def playback():
    global is_recording, playback_on, recorded_frames
    print(f"Starting to playback the recorded movements of motors {[m.ID for m in motors]}")
    is_recording = False
    playback_on = True  # stop OSC from moving motors

    for i, frame in enumerate(recorded_frames):
        if not playback_on:
            print("Playback stopped by user.")
            break
        for m in motors:
            m.moveto(frame[str(m.ID)], convertToTick=False)
        time.sleep(RECORD_DT)

    playback_on = False
    print("Playback finished")


def osc_record(unused_addr, *args):
    global is_recording, recorded_frames
    if is_recording or playback_on:
        print("Recording/Playback in progress, skipping command. To execute command, run /stop first.")
        return
    print("User triggered record")
    recorded_frames = []
    is_recording = True
    # Run in a separate thread so the OSC server stays responsive
    threading.Thread(target=record_loop, daemon=True).start()

def osc_stop(unused_addr, *args):
    global is_recording, playback_on
    print("User stopped recording/playback")
    is_recording = False
    playback_on = False

def osc_play(unused_addr, *args):
    global is_recording, playback_on, recorded_frames
    if is_recording or playback_on:
        print("Recording/Playback in progress, skipping command. To execute command, run /stop first.")
        return
    print("User triggered playback")
    try:
        with open(save_path, "r") as f:
            recorded_frames = json.load(f)
        print(f"Read recorded frames from {save_path}")
    except Exception as e:
        print(f"Error reading recorded frames: {e}")
    # Run in a separate thread so the OSC server stays responsive
    threading.Thread(target=playback, daemon=True).start()

if __name__ == "__main__":

    dispatcher.map("/neck", moveNeckTilt)
    dispatcher.map("/headturn", moveHeadTurn)
    dispatcher.map("/headtilt", moveHeadTilt)
    dispatcher.map("/mouth", moveMouth)

    dispatcher.map("/record", osc_record)
    dispatcher.map("/stop", osc_stop)
    dispatcher.map("/play", osc_play)

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
