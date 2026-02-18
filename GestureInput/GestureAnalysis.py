import json
import numpy as np
import matplotlib.pyplot as plt
from GestureInput.Shaiahead import RECORD_DT, save_path
import numpy as np

def infer_bpm_from_positions(
    x,                      # position array
    t,                      # time array
    position_eps=10.0,      # ticks; below this = noise
    min_nods=1,             # nods needed before BPM estimate
    bpm_change_ratio=0.2    # 20% change triggers new segment
):
    """
    Infer BPM from motor position using turning points.

    Returns:
        times: list of times (seconds)
        bpms: list of BPM values (0 during inactivity)
    """

    direction = 0  # -1 down, +1 up, 0 unknown
    last_dir = 0

    peak_times = []
    bpm_times = []
    bpm_values = []

    current_bpm = None

    for i in range(1, len(x)):
        dx = x[i] - x[i - 1]

        # Determine direction
        if dx > position_eps:
            direction = 1
        elif dx < -position_eps:
            direction = -1
        else:
            direction = 0

        # Detect peak: up/inactive -> down
        if last_dir >= 0 and direction == -1:
            peak_time = t[i]
            peak_times.append(peak_time)

            # Need enough peaks to estimate tempo
            if len(peak_times) >= min_nods + 1:
                # Compute periods between last few peaks
                periods = np.diff(peak_times[-(min_nods + 1):])
                avg_period = np.mean(periods)

                bpm = 60.0 / avg_period

                if current_bpm is None:
                    current_bpm = bpm
                    bpm_times.append(peak_times[-(min_nods + 1)])
                    bpm_values.append(bpm)
                else:
                    change = abs(bpm - current_bpm) / current_bpm
                    if change > bpm_change_ratio:
                        current_bpm = bpm
                        bpm_times.append(peak_times[-(min_nods + 1)])
                        bpm_values.append(bpm)

        last_dir = direction

    return np.array(bpm_times), np.array(bpm_values)

# -----------------------------
# Parameters
# -----------------------------
fs = 1 / RECORD_DT
motor_id = "11"  # HeadTilt

# -----------------------------
# Recorded data
# -----------------------------
with open(save_path, "r") as f:
    recorded_frames = json.load(f)

# Extract head tilt position
x = np.array([frame[motor_id] for frame in recorded_frames], dtype=float) # position array
t = np.array([f["t"] for f in recorded_frames])
t = t - t[0]   # normalize to start at 0

bpm_times, bpm_values = infer_bpm_from_positions(x, t)
print(f"Detected the following BPMs from the corresponding seconds:\n{bpm_values}\n{bpm_times}")

# -----------------------------------------------------------
# Visualization (plot position trajectory and inferred BPM)
# -----------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 4))

# Plot head position
ax.plot(t, x, color="black", linewidth=1)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Position (ticks)")
fig.suptitle(f"Position and Inferred BPM (Motor {motor_id})")
colors = plt.cm.Set2.colors

for i in range(len(bpm_times)):
    start_t = bpm_times[i]
    end_t = bpm_times[i + 1] if i + 1 < len(bpm_times) else t[-1]
    bpm = bpm_values[i]

    color = colors[i % len(colors)]

    # Colored region
    ax.axvspan(
        start_t,
        end_t,
        color=color,
        alpha=0.25
    )

    # BPM text
    ax.text(
        (start_t + end_t) / 2,
        np.max(x),
        f"{bpm:.1f} BPM",
        ha="center",
        va="top",
        fontsize=10,
        color=color
    )

plt.show()
