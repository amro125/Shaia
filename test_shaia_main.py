"""Smoke-test ShaiaMain.py with a fake slider+striker serial port and dummy head."""

import os
import pty
import subprocess
import sys
import threading
import time

from pythonosc.udp_client import SimpleUDPClient

STRIKER_MODES = {ord(c) for c in "sftpcr"}
SCRIPT = os.path.join(os.path.dirname(__file__), "ShaiaMain.py")
OSC_PORT = 19010


def decode(buf):
    out, i = [], 0
    while i < len(buf):
        b = buf[i]
        if b == ord('m') and i + 5 <= len(buf):
            arm_id = buf[i + 1]
            pos = (buf[i + 2] << 8) | buf[i + 3]
            out.append(("slider", arm_id, pos))
            i += 5
        elif b in STRIKER_MODES and i + 4 <= len(buf):
            out.append(("striker", chr(b), buf[i + 1], buf[i + 2]))
            i += 4
        else:
            if b == ord('m') or b in STRIKER_MODES:
                break
            i += 1
    return out, buf[i:]


def main():
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)

    t0 = [None]
    leftover = bytearray()

    def reader():
        while True:
            try:
                chunk = os.read(master_fd, 256)
            except OSError:
                return
            if not chunk:
                continue
            leftover.extend(chunk)
            frames, rest = decode(bytes(leftover))
            leftover[:] = rest
            for f in frames:
                dt = (time.monotonic() - t0[0]) * 1000 if t0[0] else 0
                if f[0] == "slider":
                    print(f"[+{dt:7.1f}ms] SLIDER  arm={f[1]} pos={f[2]:>4} mm", flush=True)
                else:
                    print(f"[+{dt:7.1f}ms] STRIKER mode={f[1]} id=0x{f[2]:02x} vel={f[3]}", flush=True)

    threading.Thread(target=reader, daemon=True).start()

    proc = subprocess.Popen(
        [sys.executable, "-u", SCRIPT,
         "--arm-port", slave_name,
         "--no-head",
         "--osc-port", str(OSC_PORT),
         "--osc-host", "127.0.0.1"],
        stdout=sys.stderr, stderr=sys.stderr,
    )
    time.sleep(1.0)
    if proc.poll() is not None:
        print("ShaiaMain.py exited early", file=sys.stderr)
        return 1

    client = SimpleUDPClient("127.0.0.1", OSC_PORT)

    def banner(label):
        if t0[0] is None:
            t0[0] = time.monotonic()
        elapsed = (time.monotonic() - t0[0]) * 1000
        print(f"\n--- t=+{elapsed:7.1f}ms  {label}", flush=True)

    try:
        banner("send /arm 60 100 (C4)")
        client.send_message("/arm", [60, 100])
        time.sleep(0.6)

        banner("send /head nod_sway 60  (start gesture)")
        client.send_message("/head", ["nod_sway", 60.0])
        time.sleep(1.5)  # let nod_sway loop a couple times

        banner("send /head ar_sway 90  (REPLACE with new gesture)")
        client.send_message("/head", ["ar_sway", 90.0])
        time.sleep(1.0)

        banner("send /arm 67 100 in parallel with gesture")
        client.send_message("/arm", [67, 100])
        time.sleep(0.6)

        banner("send /head_stop")
        client.send_message("/head_stop", [])
        time.sleep(0.5)

        banner("send /head ballet_nod (no bpm => default 60)")
        client.send_message("/head", ["ballet_nod"])
        time.sleep(1.0)

        banner("send /head_stop  (final)")
        client.send_message("/head_stop", [])
        time.sleep(0.3)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.close(master_fd)
        os.close(slave_fd)

    return 0


if __name__ == "__main__":
    sys.exit(main())
