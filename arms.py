"""Arm/slider path planning + striker scheduling.

ArmController owns NUM_ARMS slider workers and one striker worker. handle_note()
runs the planner: tries OCTAVES_TO_TRY transpositions, picks the arm with the
shortest travel that doesn't collide with the neighbor. If no arm is free in
time (most_recent_arrival > now) for any octave, the note is dropped.
"""

import logging
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Optional, List

from defs import (
    NUM_ARMS, OCTAVES_TO_TRY, SLIDER_LIMIT, DLY_S, STRIKE_TIME_S,
    BOUNDARIES, INITIAL_POSITION,
)
from transport import is_white_key, midi_to_position, SerialTransport


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


def plan_path(arms: List[Arm], note: int, velocity: int) -> Optional[ArmCommand]:
    now = time.monotonic()

    for octave_shift in OCTAVES_TO_TRY:
        shifted_note = note + octave_shift * 12
        target = midi_to_position(shifted_note)
        if target < 0 or target > SLIDER_LIMIT:
            continue

        candidates = []
        for arm in arms:
            # Drop the note if the arm can't be there in time (still moving).
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
            return min(candidates, key=lambda m: abs(m.target - arms[m.arm_id].most_recent_target()))

    return None


class ArmController:
    """Bundles arms + striker + planner so ShaiaMain can manage them as one unit."""

    def __init__(self, transport: SerialTransport):
        self._transport = transport
        self._arms = [Arm(i, INITIAL_POSITION[i], transport) for i in range(NUM_ARMS)]
        self._striker = StrikerScheduler(transport)

    def start(self) -> None:
        for arm in self._arms:
            arm.start()
        self._striker.start()

    def stop(self) -> None:
        self._striker.stop()
        for arm in self._arms:
            arm.stop()

    def home(self) -> None:
        self._transport.send_home()

    def handle_note(self, note: int, velocity: int) -> None:
        if velocity == 0:
            return
        msg = plan_path(self._arms, note, velocity)
        if msg is None:
            logging.warning("No reachable arm for note %d", note)
            return
        self._arms[msg.arm_id].submit(msg)
        self._striker.schedule(msg.midi_note, msg.arm_id, msg.midi_velocity, msg.arrival_time)
