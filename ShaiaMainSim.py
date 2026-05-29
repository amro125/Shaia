"""Mini-Shimon arm SIMULATOR: same OSC interface as ShaiaMain, but no hardware.

Drop-in replacement of SerialTransport that prints the arm, the note it would
play, and the exact 11-byte StrikersOther frame it would send to the MCU.

OSC routes match ShaiaMain.py:
  /arm <note> <velocity>
  /arm_home
  /head <gesture> [bpm]
  /head_stop
"""

import argparse
import binascii
import logging
import sys
import threading

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from defs import (
    DEFAULT_DANCE_MODES_PATH, DEFAULT_BPM,
    DEFAULT_OSC_HOST, DEFAULT_OSC_PORT,
    ARM_OSC_ROUTE, ARM_HOME_OSC_ROUTE, HEAD_OSC_ROUTE, HEAD_STOP_OSC_ROUTE,
    SLIDER_LIMIT, SLIDER_W, SLIDER_B, HOME_FRAME,
)
from arms import ArmController
from head import DummyHeadMotors, GestureRunner


_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _note_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{(midi // 12) - 1}"


def _hex(buf: bytes) -> str:
    return binascii.hexlify(buf, " ").decode().upper()


class SimulatedTransport:
    """Mirrors SerialTransport's API but prints frames instead of writing them."""

    def __init__(self):
        self._lock = threading.Lock()

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
            logging.info(
                "[SIM SLIDER ] arm=%d slider_id=%d rail=%dmm arm_local=%dmm frame=%s",
                arm_id, slider_id, position_mm, arm_mm, _hex(buf),
            )

    def send_striker(self, striker_id: int, midi_velocity: int, mode: str) -> None:
        midi_velocity = max(0, min(127, midi_velocity))
        buf = bytes([ord(mode), striker_id & 0xFF, midi_velocity, ord('\n')])
        with self._lock:
            logging.info(
                "[SIM STRIKER] striker_id=%d vel=%d mode=%s frame=%s",
                striker_id, midi_velocity, mode, _hex(buf),
            )

    def send_home(self) -> None:
        with self._lock:
            logging.info("[SIM HOME   ] frame=%s", _hex(HOME_FRAME))

    def close(self) -> None:
        pass


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dance-modes", default=DEFAULT_DANCE_MODES_PATH)
    p.add_argument("--osc-host", default=DEFAULT_OSC_HOST)
    p.add_argument("--osc-port", type=int, default=DEFAULT_OSC_PORT)
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(threadName)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    arm_transport = SimulatedTransport()
    arms = ArmController(arm_transport)
    arms.start()

    motors = DummyHeadMotors()
    gestures = GestureRunner(args.dance_modes, motors)
    gestures.start()

    def on_arm(_addr, *osc_args):
        if len(osc_args) < 2:
            logging.warning("Ignoring /arm with %d args", len(osc_args))
            return
        note = int(osc_args[0])
        vel = int(osc_args[1])
        logging.info("[SIM /arm    ] note=%d (%s) vel=%d", note, _note_name(note), vel)
        arms.handle_note(note, vel)

    def on_arm_home(_addr, *_osc_args):
        logging.info("[SIM /arm_home] homing sliders")
        arms.home()

    def on_head(_addr, *osc_args):
        if len(osc_args) < 1:
            logging.warning("Ignoring /head with 0 args")
            return
        name = str(osc_args[0])
        bpm = float(osc_args[1]) if len(osc_args) >= 2 else DEFAULT_BPM
        gestures.play(name, bpm)

    def on_head_stop(_addr, *_osc_args):
        gestures.stop()

    dispatcher = Dispatcher()
    dispatcher.map(ARM_OSC_ROUTE, on_arm)
    dispatcher.map(ARM_HOME_OSC_ROUTE, on_arm_home)
    dispatcher.map(HEAD_OSC_ROUTE, on_head)
    dispatcher.map(HEAD_STOP_OSC_ROUTE, on_head_stop)

    server = ThreadingOSCUDPServer((args.osc_host, args.osc_port), dispatcher)
    logging.info(
        "[SIM] Listening on %s:%d  arms=SIMULATED  head=dummy",
        args.osc_host, args.osc_port,
    )
    logging.info("Gestures available: %s", gestures.list_gestures())

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down")
    finally:
        server.shutdown()
        gestures.stop_runner()
        motors.close()
        arms.stop()
        arm_transport.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
