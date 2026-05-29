"""Shared constants for the mini-Shimon Python runtime (arms + head)."""

import os

NUM_ARMS = 2
OCTAVES_TO_TRY = (0, 1, -1)
MIN_NOTE = 53   # F3
MAX_NOTE = 83   # B5
SLIDER_LIMIT = 546   # mm: B5 at 516 mm + 30 mm clearance to arm 1 home
DLY_S = 0.45
STRIKE_TIME_S = 0.050

# Lowest note F3 sits 6 mm from arm 0 home. White keys are spaced 30 mm apart
# (18 whites: F3, G3, A3, B3, C4 ... B5, ending at 516 mm). Black keys sit at
# the midpoint between their two adjacent whites. Indexed by (midi - MIN_NOTE).
NOTE_POSITION_TABLE = (
    6,  21,  36,  51,  66,  81,  96, 126, 141, 156,
    171, 186, 216, 231, 246, 261, 276, 291, 306, 336,
    351, 366, 381, 396, 426, 441, 456, 471, 486, 501,
    516,
)
BOUNDARIES = ((0, 40), (40, 0))
INITIAL_POSITION = (0, SLIDER_LIMIT)
BLACK_KEY_PCS = frozenset({1, 3, 6, 8, 10})

# --- StrikersOther wire format ----------------------------------------------
# 11-byte little-endian frame on the shared serial port:
#   [0]    0xAA      sync
#   [1]    uint8     sliderID  (1/2 = slider move; 0xFE = home all; else = no slider)
#   [2..5] int32     slider target ticks
#   [6..7] int16     slider duration (1 ms ticks)
#   [8]    uint8     strikerID (>=3 = strike; else ignored)
#   [9]    uint8     velocity  (0-127)
#   [10]   uint8     action    (0 = single hit, 1 = tremolo)
FRAME_FMT = "<BBiHBBB"
SLIDER_MOVE_DURATION_MS = 450

# Slider encoder: 40 mm per full revolution, EC45_ENC_RES_SLIDER = 1024 ticks/rev.
SLIDER_TICKS_PER_REV = 1024
SLIDER_MM_PER_REV = 40
MM_TO_TICKS = SLIDER_TICKS_PER_REV / SLIDER_MM_PER_REV

# Per-arm transform from the shared rail mm coordinate (0..SLIDER_LIMIT) to each
# arm's home-relative mm: arm_mm = SLIDER_W[id] * shared_mm + SLIDER_B[id].
# Arm 0 homes at the lowest note (0 mm) and moves up with positive ticks.
# Arm 1 homes at the highest note (SLIDER_LIMIT) and moves down with positive ticks.
SLIDER_W = (1, -1)
SLIDER_B = (0, SLIDER_LIMIT)

DEFAULT_ARM_PORT = "/dev/tty.usbmodem1101"
DEFAULT_ARM_BAUD = 115200
DEFAULT_HEAD_PORT = "/dev/tty.usbserial-FT62AP2P"
DEFAULT_HEAD_BAUD = 57600

DEFAULT_OSC_HOST = "0.0.0.0"
DEFAULT_OSC_PORT = 9000

ARM_OSC_ROUTE = "/arm"
ARM_HOME_OSC_ROUTE = "/arm_home"
HEAD_OSC_ROUTE = "/head"
HEAD_STOP_OSC_ROUTE = "/head_stop"

# Home command for the ASCII strikers firmware: parseCommand requires
# len(cmd) >= 4 and the trailing '\n' triggers stringComplete in serialEvent.
HOME_FRAME = b"h\x00\x00\n"

# normalized_position [0,1] is mapped to [min, max] in dynamixel-degree space.
# Values lifted from Shaia/Dance/dance.py.
HEAD_MOTORS = {
    "HeadTurn": {"id": 10, "min": 100, "max": 260},
    "HeadTilt": {"id": 11, "min": 140, "max":  64},
    "Mouth":    {"id": 12, "min": 341, "max": 320},
    "NeckTilt": {"id": 13, "min": 156, "max": 210},
    "NeckTurn": {"id": 14, "min":  85, "max": 193},
}

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DANCE_MODES_PATH = os.path.join(_HERE, "Dance", "danceModes.json")

GESTURE_TICK_S = 0.05
GESTURE_TRIGGER_WINDOW_S = 0.07
DEFAULT_BPM = 60.0
