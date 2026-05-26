"""
mini-Shimon runtime: 2 arms + 4 strikers, all on one serial port, driven by an
OSC server on /arm (note, velocity).

Wire format on the shared serial port (11-byte binary frame, little-endian,
matches StrikersOther/Strikers.ino):
  [0]    0xAA      sync
  [1]    uint8     sliderID  (1/2 = slider move; 0xFE = home all; else = no slider)
  [2..5] int32     slider target ticks
  [6..7] int16     slider duration (PDO ticks, 1ms each)
  [8]    uint8     strikerID (>=3 = strike; else ignored)
  [9]    uint8     velocity  (0-127)
  [10]   uint8     action    (0 = single hit, 1 = tremolo)
A single frame can drive both a slider and a striker; this code sends each
independently with the unused half zeroed.
"""

import argparse
import logging
import struct
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Optional

import serial
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

# sync, sliderID, ticks(i32), duration(i16), strikerID, velocity, action
FRAME_FMT = "<BBiHBBB"
SLIDER_MOVE_DURATION_MS = 450

# Slider encoder: 40 mm per full revolution, EC45_ENC_RES_SLIDER = 1024 ticks/rev.
SLIDER_TICKS_PER_REV = 1024
SLIDER_MM_PER_REV = 40
MM_TO_TICKS = SLIDER_TICKS_PER_REV / SLIDER_MM_PER_REV


NUM_ARMS = 2
OCTAVES_TO_TRY = (0, 1, -1)

MIN_NOTE = 53   # F3
MAX_NOTE = 83   # B5

SLIDER_LIMIT = 546   # mm: B5 at 516 mm + 30 mm clearance to arm 1 home
DLY_S = 0.45
STRIKE_TIME_S = 0.050

# Per-arm transform from the shared rail mm coordinate (0..SLIDER_LIMIT) to each
# arm's home-relative mm: arm_mm = SLIDER_W[id] * shared_mm + SLIDER_B[id].
# Arm 0 homes at the lowest note (0 mm) and moves up with positive ticks.
# Arm 1 homes at the highest note (SLIDER_LIMIT) and moves down with positive ticks.
SLIDER_W = (1, -1)
SLIDER_B = (0, SLIDER_LIMIT)

# Lowest note F3 sits 6 mm from arm 0 home. White keys are spaced 30 mm apart
# (18 whites: F3, G3, A3, B3, C4 ... B5, ending at 516 mm). Black keys sit at
# the midpoint between their two adjacent whites. Indexed by (midi - MIN_NOTE).
NOTE_POSITION_TABLE = (
    6,  21,  36,  51,  66,  81,  96, 126, 141, 156,
    171, 186, 216, 231, 246, 261, 276, 291, 306, 336,
    351, 366, 381, 396, 426, 441, 456, 471, 486, 501,
    516,
)

# Per-arm (left_exclusion, right_exclusion) in mm. With 2 arms, only the
# inner sides need clearance from the neighbor.
BOUNDARIES = ((0, 40), (40, 0))
INITIAL_POSITION = (0, SLIDER_LIMIT)

BLACK_KEY_PCS = frozenset({1, 3, 6, 8, 10})


def is_white_key(note: int) -> int:
    return 0 if (note % 12) in BLACK_KEY_PCS else 1


def midi_to_position(note: int) -> int:
    if note < MIN_NOTE or note > MAX_NOTE:
        return -1
    return NOTE_POSITION_TABLE[note - MIN_NOTE]


class SerialTransport:
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


@dataclass
class ArmCommand:
    arm_id: int
    target: int
    midi_note: int
    midi_velocity: int
    msg_time: float = 0.0
    arrival_time: float = 0.0


class Arm:
    def __init__(self, arm_id: int, home: int, transport: SerialTransport):
        self.id = arm_id
        self.position = home
        self._transport = transport
        self._most_recent_target = home
        self._most_recent_arrival = time.monotonic()
        self._q: "Queue[Optional[ArmCommand]]" = Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def left_boundary(self) -> int:
        return self.position - BOUNDARIES[self.id][0]

    def right_boundary(self) -> int:
        return self.position + BOUNDARIES[self.id][1]

    def most_recent_target(self) -> int:
        return self._most_recent_target

    def most_recent_arrival(self) -> float:
        return self._most_recent_arrival

    def submit(self, msg: ArmCommand) -> None:
        self._most_recent_target = msg.target
        self._most_recent_arrival = msg.arrival_time
        self._q.put(msg)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, name=f"arm{self.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._q.put(None)
        if self._thread:
            self._thread.join()

    def _run(self) -> None:
        while self._running:
            try:
                msg = self._q.get(timeout=0.5)
            except Empty:
                continue
            if msg is None:
                break
            wait = msg.msg_time - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._transport.send_slider(self.id, msg.target)
            self.position = msg.target
            logging.info("arm %d -> %d  note=%d", self.id, msg.target, msg.midi_note)


@dataclass
class StrikerCommand:
    striker_id: int
    midi_velocity: int
    mode: str
    strike_time: float


class StrikerScheduler:
    def __init__(self, transport: SerialTransport):
        self._transport = transport
        self._q: "Queue[Optional[StrikerCommand]]" = Queue()
        self._mode = 's'
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def schedule(self, note: int, arm_id: int, midi_velocity: int, strike_time: float) -> None:
        # StrikersOther strikers are sequentially numbered after the sliders:
        # arm 0 -> {black: 3, white: 4}, arm 1 -> {black: 5, white: 6}.
        striker_id = (NUM_ARMS + 1) + (arm_id * 2) + is_white_key(note)
        self._q.put(StrikerCommand(
            striker_id=striker_id,
            midi_velocity=max(0, min(127, midi_velocity)),
            mode=self._mode,
            strike_time=strike_time,
        ))

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, name="striker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._q.put(None)
        if self._thread:
            self._thread.join()

    def _run(self) -> None:
        while self._running:
            try:
                cmd = self._q.get(timeout=0.5)
            except Empty:
                continue
            if cmd is None:
                break
            # Fire STRIKE_TIME_S early so the mechanical impact lands on strike_time.
            wait = (cmd.strike_time - STRIKE_TIME_S) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._transport.send_striker(cmd.striker_id, cmd.midi_velocity, cmd.mode)
            logging.info(
                "strike id=%d vel=%d mode=%s", cmd.striker_id, cmd.midi_velocity, cmd.mode,
            )


def plan_path(arms, note: int, velocity: int):
    now = time.monotonic()

    for octave_shift in OCTAVES_TO_TRY:
        shifted_note = note + octave_shift * 12
        target = midi_to_position(shifted_note)
        if target < 0 or target > SLIDER_LIMIT:
            continue

        candidates = []
        for arm in arms:
            # The arm needs DLY_S to reach the new target. If it's still finishing
            # a previous move, this note can't land on the beat — drop it.
            if arm.most_recent_arrival() > now:
                continue

            mr_target = arm.most_recent_target()
            if target > mr_target:
                direction = 1
            elif target < mr_target:
                direction = -1
            else:
                direction = 0

            if direction > 0 and arm.id + 1 < NUM_ARMS:
                if target >= arms[arm.id + 1].left_boundary():
                    continue
            elif direction < 0 and arm.id - 1 >= 0:
                if target <= arms[arm.id - 1].right_boundary():
                    continue

            candidates.append(ArmCommand(
                arm_id=arm.id,
                target=target,
                midi_note=shifted_note,
                midi_velocity=velocity,
                msg_time=now,
                arrival_time=now + DLY_S,
            ))

        if candidates:
            # Tiebreaker: arm that has to travel the least from its most-recent target.
            return min(candidates, key=lambda m: abs(m.target - arms[m.arm_id].most_recent_target()))

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial-port", default="/dev/tty.usbmodem1101")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--osc-host", default="0.0.0.0")
    parser.add_argument("--osc-port", type=int, default=9000)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(threadName)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    transport = SerialTransport(args.serial_port, args.baudrate)
    arms = [Arm(i, INITIAL_POSITION[i], transport) for i in range(NUM_ARMS)]
    striker = StrikerScheduler(transport)

    for arm in arms:
        arm.start()
    striker.start()

    def handle_arm(_addr, *osc_args):
        if len(osc_args) < 2:
            logging.warning("Ignoring /arm with %d args", len(osc_args))
            return
        note, velocity = int(osc_args[0]), int(osc_args[1])
        if velocity == 0:
            return
        msg = plan_path(arms, note, velocity)
        if msg is None:
            logging.warning("No reachable arm for note %d", note)
            return
        arms[msg.arm_id].submit(msg)
        striker.schedule(msg.midi_note, msg.arm_id, msg.midi_velocity, msg.arrival_time)

    dispatcher = Dispatcher()
    dispatcher.map("/arm", handle_arm)

    server = ThreadingOSCUDPServer((args.osc_host, args.osc_port), dispatcher)
    logging.info("Listening for /arm on %s:%d (serial=%s @ %d)",
                 args.osc_host, args.osc_port, args.serial_port, args.baudrate)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down")
    finally:
        server.shutdown()
        striker.stop()
        for arm in arms:
            arm.stop()
        transport.close()


if __name__ == "__main__":
    main()
