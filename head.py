"""Head dynamixel motors + looping gesture runner.

GestureRunner runs ONE gesture at a time on a worker thread. play(name, bpm)
atomically swaps to a new gesture (cancelling whatever was playing). stop()
clears the current gesture. A generation counter wakes the worker so the
switch is immediate rather than waiting for the next loop period.
"""

import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from defs import (
    HEAD_MOTORS, GESTURE_TICK_S, GESTURE_TRIGGER_WINDOW_S, DEFAULT_BPM,
)


def _add_shaia_utils_to_path():
    """Add Shaia/utils/ to sys.path so we can pick up Dynamixelutils without
    colliding with this repo's top-level utils.py."""
    here = os.path.dirname(os.path.abspath(__file__))
    shaia_utils = os.path.abspath(os.path.join(here, "..", "Shaia", "utils"))
    if shaia_utils not in sys.path:
        sys.path.insert(0, shaia_utils)


class HeadMotors:
    """Owns the dynamixel port + per-motor configs.

    move(name, normalized_pos, velocity) — normalized_pos is [0,1] and maps to
    the per-motor [min,max] range from HEAD_MOTORS.
    """

    def __init__(self, port: str, baudrate: int):
        _add_shaia_utils_to_path()
        from dynamixel_sdk import PacketHandler, PortHandler   # noqa: WPS433
        from Dynamixelutils import dynamixel                   # noqa: WPS433

        self._packet = PacketHandler(2.0)
        self._port = PortHandler(port)
        if not self._port.openPort():
            raise RuntimeError(f"failed to open dynamixel port {port}")
        if not self._port.setBaudRate(baudrate):
            raise RuntimeError(f"failed to set baudrate {baudrate} on {port}")

        self._motors: Dict[str, Any] = {}
        for name, cfg in HEAD_MOTORS.items():
            m = dynamixel(cfg["id"], self._port, self._packet, BAUD=baudrate)
            m.enable_torque()
            self._motors[name] = m
        logging.info("head motors online (%s @ %d)", port, baudrate)

    def move(self, name: str, normalized_pos: float, velocity: float) -> None:
        if name not in HEAD_MOTORS:
            logging.warning("Unknown head motor %s", name)
            return
        cfg = HEAD_MOTORS[name]
        normalized_pos = max(0.0, min(1.0, normalized_pos))
        goal = normalized_pos * (cfg["max"] - cfg["min"]) + cfg["min"]
        self._motors[name].moveto(goal, wait=False, velocity=velocity)

    def close(self) -> None:
        for m in self._motors.values():
            try:
                m.disable_torque()
            except Exception as ex:
                logging.warning("disable_torque failed: %s", ex)
        try:
            self._port.closePort()
        except Exception as ex:
            logging.warning("closePort failed: %s", ex)


class DummyHeadMotors:
    """Stand-in for testing without the dynamixel rig — just logs."""

    def move(self, name: str, normalized_pos: float, velocity: float) -> None:
        logging.info("[head-dummy] %s -> %.3f @ v=%.3f", name, normalized_pos, velocity)

    def close(self) -> None:
        pass


@dataclass
class _GestureEvent:
    motor: str
    offset_s: float
    period_s: float
    position: float
    velocity: float


class GestureRunner:
    def __init__(self, dance_modes_path: str, motors):
        with open(dance_modes_path) as f:
            self._dance_modes = json.load(f)
        self._motors = motors

        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._current_name: Optional[str] = None
        self._current_events: List[_GestureEvent] = []
        self._current_start: float = 0.0
        self._generation = 0

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def list_gestures(self) -> List[str]:
        return list(self._dance_modes.keys())

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, name="head", daemon=True)
        self._thread.start()

    def stop_runner(self) -> None:
        with self._cv:
            self._running = False
            self._cv.notify_all()
        if self._thread:
            self._thread.join()

    def play(self, name: str, bpm: float = DEFAULT_BPM) -> None:
        if name not in self._dance_modes:
            logging.warning(
                "Unknown gesture: %s (available: %s)", name, self.list_gestures(),
            )
            return
        if bpm <= 0:
            logging.warning("Bad BPM %.2f, falling back to %.2f", bpm, DEFAULT_BPM)
            bpm = DEFAULT_BPM
        beat_to_sec = 60.0 / bpm

        events = [
            _GestureEvent(
                motor=e["motor"],
                offset_s=e["startBeat"] * beat_to_sec,
                period_s=e["periodBeat"] * beat_to_sec,
                position=e["position"],
                velocity=e["velocity"],
            )
            for e in self._dance_modes[name]["moves"]
        ]

        with self._cv:
            self._current_name = name
            self._current_events = events
            self._current_start = time.monotonic()
            self._generation += 1
            self._cv.notify_all()
        logging.info("Playing gesture %s @ %.1f BPM (%d events)", name, bpm, len(events))

    def stop(self) -> None:
        with self._cv:
            if self._current_name is None:
                return
            logging.info("Stopping gesture %s", self._current_name)
            self._current_name = None
            self._current_events = []
            self._generation += 1
            self._cv.notify_all()

    def _run(self) -> None:
        last_fired: Dict[int, float] = {}
        gen_seen = -1

        while True:
            with self._cv:
                if not self._running:
                    return
                if self._current_name is None:
                    # Idle — block until a play() or stop_runner() arrives.
                    self._cv.wait()
                    if not self._running:
                        return
                name = self._current_name
                events = self._current_events
                start = self._current_start
                generation = self._generation

            if generation != gen_seen:
                last_fired.clear()
                gen_seen = generation

            if name is None:
                continue

            t = time.monotonic() - start
            for idx, e in enumerate(events):
                if t < e.offset_s:
                    continue
                n = int((t - e.offset_s) / e.period_s)
                next_trigger = e.offset_s + n * e.period_s
                if 0 <= t - next_trigger < GESTURE_TRIGGER_WINDOW_S:
                    if last_fired.get(idx) == next_trigger:
                        continue
                    last_fired[idx] = next_trigger
                    try:
                        self._motors.move(e.motor, e.position, e.velocity)
                    except Exception as ex:
                        logging.error("head move %s failed: %s", e.motor, ex)

            # Sleep on the condition so play()/stop() can wake us instantly.
            with self._cv:
                if self._running and self._current_name is not None and generation == self._generation:
                    self._cv.wait(timeout=GESTURE_TICK_S)
