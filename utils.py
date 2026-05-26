"""Helpers + shared serial transport."""

import threading

import serial

from defs import NOTE_POSITION_TABLE, MIN_NOTE, MAX_NOTE, SLIDER_LIMIT, BLACK_KEY_PCS


def is_white_key(note: int) -> int:
    return 0 if (note % 12) in BLACK_KEY_PCS else 1


def midi_to_position(note: int) -> int:
    if note < MIN_NOTE or note > MAX_NOTE:
        return -1
    return NOTE_POSITION_TABLE[note - MIN_NOTE]


class SerialTransport:
    """Single serial port carrying both slider and striker frames.

    Slider frame:  b'm' + armId(1) + pos_hi(1) + pos_lo(1) + b'\\n'   (5B, pos is uint16 BE mm)
    Striker frame: <mode>(1) + strikerId(1) + midiVel(1) + b'\\n'     (4B)
    Mode chars: 's' slow, 'f' fast, 't' tremolo, 'p' tremolo-stop, 'c' choreo, 'r' restart.
    """

    def __init__(self, port: str, baudrate: int):
        self._lock = threading.Lock()
        self._ser = serial.Serial(port, baudrate=baudrate, timeout=0.1)

    def send_slider(self, arm_id: int, position_mm: int) -> None:
        position_mm = max(0, min(SLIDER_LIMIT, position_mm))
        buf = bytes([
            ord('m'),
            arm_id & 0xFF,
            (position_mm >> 8) & 0xFF,
            position_mm & 0xFF,
            ord('\n'),
        ])
        with self._lock:
            self._ser.write(buf)

    def send_striker(self, striker_id: int, midi_velocity: int, mode: str) -> None:
        midi_velocity = max(0, min(127, midi_velocity))
        buf = bytes([ord(mode), striker_id & 0xFF, midi_velocity, ord('\n')])
        with self._lock:
            self._ser.write(buf)

    def close(self) -> None:
        with self._lock:
            self._ser.close()
