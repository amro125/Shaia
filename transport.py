"""Helpers + shared serial transport."""

import struct
import threading

import serial

from defs import (
    NOTE_POSITION_TABLE, MIN_NOTE, MAX_NOTE, SLIDER_LIMIT, BLACK_KEY_PCS,
    FRAME_FMT, SLIDER_MOVE_DURATION_MS, MM_TO_TICKS, SLIDER_W, SLIDER_B,
)


def is_white_key(note: int) -> int:
    return 0 if (note % 12) in BLACK_KEY_PCS else 1


def midi_to_position(note: int) -> int:
    if note < MIN_NOTE or note > MAX_NOTE:
        return -1
    return NOTE_POSITION_TABLE[note - MIN_NOTE]


class SerialTransport:
    """Single serial port carrying both slider and striker frames.

    Wire format matches StrikersOther/Strikers.ino: 11-byte little-endian frame
    with 0xAA sync. See defs.FRAME_FMT for field layout. A single frame can
    drive a slider and a striker; this class sends each independently with the
    unused half zeroed.
    """

    def __init__(self, port: str, baudrate: int):
        self._lock = threading.Lock()
        self._ser = serial.Serial(port, baudrate=baudrate, timeout=0.1)

    def send_slider(self, arm_id: int, position_mm: int,
                    duration_ms: int = SLIDER_MOVE_DURATION_MS) -> None:
        # StrikersOther's slider IDs are 1-indexed (1 or 2); arm_id is 0-indexed.
        position_mm = max(0, min(SLIDER_LIMIT, position_mm))
        arm_mm = SLIDER_W[arm_id] * position_mm + SLIDER_B[arm_id]
        position_ticks = int(round(arm_mm * MM_TO_TICKS))
        slider_id = (arm_id + 1) & 0xFF
        buf = struct.pack(FRAME_FMT, 0xAA, slider_id, position_ticks,
                          int(duration_ms), 0, 0, 0)
        with self._lock:
            self._ser.write(buf)

    def send_striker(self, striker_id: int, midi_velocity: int, mode: str) -> None:
        midi_velocity = max(0, min(127, midi_velocity))
        action = 1 if mode == 't' else 0
        buf = struct.pack(FRAME_FMT, 0xAA, 0, 0, 0,
                          striker_id & 0xFF, midi_velocity, action)
        with self._lock:
            self._ser.write(buf)

    def close(self) -> None:
        with self._lock:
            self._ser.close()
