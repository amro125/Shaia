"""Shared constants for the mini-Shimon Python runtime (arms + head)."""

import os

NUM_ARMS = 2
OCTAVES_TO_TRY = (0, 1, -1)
MIN_NOTE = 48
MAX_NOTE = 95
SLIDER_LIMIT = 1385
DLY_S = 0.45
STRIKE_TIME_S = 0.050

NOTE_POSITION_TABLE = (
    0, 10, 44, 73, 102, 157, 184, 212, 240, 267, 294, 324, 377, 406, 434,
    463, 490, 546, 574, 599, 624, 651, 673, 698, 749, 771, 798, 820, 846,
    894, 919, 945, 969, 993, 1018, 1044, 1092, 1118, 1142, 1167, 1193, 1240,
    1266, 1291, 1315, 1339, 1364, 1385, 1385,
)
BOUNDARIES = ((0, 40), (40, 0))
INITIAL_POSITION = (0, SLIDER_LIMIT)
BLACK_KEY_PCS = frozenset({1, 3, 6, 8, 10})

DEFAULT_ARM_PORT = "/dev/tty.usbmodem1101"
DEFAULT_ARM_BAUD = 115200
DEFAULT_HEAD_PORT = "/dev/tty.usbserial-FT62AP2P"
DEFAULT_HEAD_BAUD = 57600

DEFAULT_OSC_HOST = "0.0.0.0"
DEFAULT_OSC_PORT = 9000

ARM_OSC_ROUTE = "/arm"
HEAD_OSC_ROUTE = "/head"
HEAD_STOP_OSC_ROUTE = "/head_stop"

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
DEFAULT_DANCE_MODES_PATH = os.path.normpath(
    os.path.join(_HERE, "..", "Shaia", "Dance", "danceModes.json")
)

GESTURE_TICK_S = 0.05
GESTURE_TRIGGER_WINDOW_S = 0.07
DEFAULT_BPM = 60.0
