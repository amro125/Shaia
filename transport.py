"""Helpers + shared serial transport."""

import threading

import serial

from defs import (
    NOTE_POSITION_TABLE, MIN_NOTE, MAX_NOTE, SLIDER_LIMIT, BLACK_KEY_PCS,
    SLIDER_W, SLIDER_B, HOME_FRAME,
)


def is_white_key(note: int) -> int:
    return 0 if (note % 12) in BLACK_KEY_PCS else 1


def midi_to_position(note: int) -> int:
    if note < MIN_NOTE or note > MAX_NOTE:
        return -1
    return NOTE_POSITION_TABLE[note - MIN_NOTE]


class SerialTransport:
    """Single serial port carrying slider, striker, and home commands.

    ASCII line protocol parsed by the strikers Arduino sketch — each command
    ends in '\\n', which the firmware uses to delimit frames:

        slider:  b"m"  + slider_id + pos_hi + pos_lo + b"\\n"  (5 bytes)
                 slider_id is 1-indexed; pos is per-arm-local mm, big-endian
        striker: b"<mode>" + striker_id + velocity + b"\\n"    (4 bytes)
        home:    b"h\\x00\\x00\\n"                              (4 bytes)
    """

    def __init__(self, port: str, baudrate: int):
        self._lock = threading.Lock()
#        self._ser = serial.Serial(port, baudrate=baudrate, timeout=0.1)

    def send_slider(self, arm_id: int, position_mm: int) -> None:
        position_mm = max(0, min(SLIDER_LIMIT, position_mm))
        arm_mm = SLIDER_W[arm_id] * position_mm + SLIDER_B[arm_id]
        slider_id = (arm_id + 1) & 0xFF
        buf = bytes([
            ord('m'),
            slider_id,
            (arm_mm >> 8) & 0xFF,
            arm_mm & 0xFF,
            ord('\n'),
        ])
        with self._lock:
            self._ser.write(buf)

    def send_striker(self, striker_id: int, midi_velocity: int, mode: str) -> None:
        midi_velocity = max(0, min(127, midi_velocity))
        buf = bytes([ord(mode), striker_id & 0xFF, midi_velocity, ord('\n')])
        with self._lock:
            self._ser.write(buf)

    def send_home(self) -> None:
        with self._lock:
            self._ser.write(HOME_FRAME)

    def close(self) -> None:
        with self._lock:
            self._ser.close()
