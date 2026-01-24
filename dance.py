import json
import time

from utils.Dynamixelutils import dynamixel
from dynamixel_sdk import *                    # Uses Dynamixel SDK library
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer




# ===========
#   MOTORS 
# ===========
port = '/dev/tty.usbserial-FT62AODN'
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

def osc_dance(unused_addr, *args):
    
    mode_name = args[0]
    bpm = args[1]
    duration_s = args[2]

    if mode_name not in DANCE_MODES:
        print(f"Mode '{mode_name}' not found!")
        return

    events = DANCE_MODES[mode_name]
    beat_to_sec = 60 / bpm

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

    start_time = time.time()
    print(f"Starting dance mode '{mode_name}' at {bpm} BPM for {duration_s} seconds...")

    while True:
        t = time.time() - start_time
        if t >= duration_s:
            break

        for e in scaled_events:
            if t >= e["start_s"]:
                n = int((t - e["start_s"]) / e["period_s"])
                next_trigger = e["start_s"] + n * e["period_s"]
                if 0 <= t - next_trigger < 0.02:  # trigger window
                    motor = MOTOR_MAP[e["motor"]]
                    vel = e["velocity"]
                    motor(-1, e["position"], vel, 0)

        time.sleep(0.01)

if __name__ == "__main__":
    dispatcher.map("/dance", osc_dance)

    NeckTilt.initmotor()
    HeadTurn.initmotor()

    for motor in motors:
        print(f"Enabling torque for motor ID {motor.ID}")
        motor.enable_torque()

    try:
        server = BlockingOSCUDPServer(("127.0.0.1", 9010), dispatcher)
        server.serve_forever()  # Blocks forever
    except:
        moveNeckTilt(-1, 0, 0.01, 1)
        for motor in motors:
            motor.disable_torque()
        NeckTilt.shutdownSeq()
        HeadTurn.shutdownSeq()
    finally:
        moveNeckTilt(-1, 0, 0.01, 1)
        for motor in motors:
            motor.disable_torque()
        NeckTilt.shutdownSeq()
        HeadTurn.shutdownSeq()
