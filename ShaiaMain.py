"""Mini-Shimon main runtime: arm path planning + looping head gestures, driven by OSC.

OSC routes:
  /arm <note> <velocity>          MIDI-style note trigger (vel=0 is dropped)
  /arm_home                       Send the slider homing command to the MCU
  /head <gesture> [bpm]           Start a gesture loop (replaces any current one)
  /head_stop                      Stop the current gesture
"""

import argparse
import logging
import sys

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from defs import (
    DEFAULT_ARM_PORT, DEFAULT_ARM_BAUD,
    DEFAULT_HEAD_PORT, DEFAULT_HEAD_BAUD,
    DEFAULT_OSC_HOST, DEFAULT_OSC_PORT,
    DEFAULT_DANCE_MODES_PATH, DEFAULT_BPM,
    ARM_OSC_ROUTE, ARM_HOME_OSC_ROUTE, HEAD_OSC_ROUTE, HEAD_STOP_OSC_ROUTE,
)
from transport import SerialTransport
from arms import ArmController
from head import HeadMotors, DummyHeadMotors, GestureRunner


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm-port", default=DEFAULT_ARM_PORT)
    p.add_argument("--arm-baud", type=int, default=DEFAULT_ARM_BAUD)
    p.add_argument("--head-port", default=DEFAULT_HEAD_PORT)
    p.add_argument("--head-baud", type=int, default=DEFAULT_HEAD_BAUD)
    p.add_argument("--dance-modes", default=DEFAULT_DANCE_MODES_PATH)
    p.add_argument("--osc-host", default=DEFAULT_OSC_HOST)
    p.add_argument("--osc-port", type=int, default=DEFAULT_OSC_PORT)
    p.add_argument("--no-head", action="store_true", help="use dummy head motors (no dynamixel)")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(threadName)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    arm_transport = SerialTransport(args.arm_port, args.arm_baud)
    arms = ArmController(arm_transport)
    arms.start()

    motors = DummyHeadMotors() if args.no_head else HeadMotors(args.head_port, args.head_baud)
    gestures = GestureRunner(args.dance_modes, motors)
    gestures.start()

    def on_arm(_addr, *osc_args):
        if len(osc_args) < 2:
            logging.warning("Ignoring /arm with %d args", len(osc_args))
            return
        arms.handle_note(int(osc_args[0]), int(osc_args[1]))

    def on_arm_home(_addr, *_osc_args):
        logging.info("Homing sliders")
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
        "Listening on %s:%d  arm=%s@%d  head=%s",
        args.osc_host, args.osc_port, args.arm_port, args.arm_baud,
        "dummy" if args.no_head else f"{args.head_port}@{args.head_baud}",
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
