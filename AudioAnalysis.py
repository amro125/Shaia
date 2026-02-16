import librosa
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

# ===========================
#    Structure Detections
# ===========================

def detect_structural_boundaries(audio, sr, kernel_size=32, percentile=95,
                                 hop_length=512, min_section_s=8, verbose=False):
    """
    Detect musical section boundaries using chroma-based novelty detection.
    Returns sorted boundary times in seconds.
    
    Parameters:
        audio : np.ndarray
            Audio signal.
        sr : int
            Sample rate.
        kernel_size : int
            Size of Gaussian smoothing kernel.
        percentile : float
            Peaks above this percentile of novelty are selected.
        hop_length : int
            Hop length used in chroma frames.
        min_section_s : float
            Minimum section duration in seconds.
        verbose : bool
            If True, plot novelty and detected peaks.
    """
    # 1. Harmonic component & chroma
    y_harm = librosa.effects.harmonic(audio)
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop_length)

    # 2. Self-similarity (recurrence) matrix
    R = librosa.segment.recurrence_matrix(chroma, mode='affinity', sym=True)

    # 3. Compute novelty: compare each frame to previous + global median
    novelty = np.zeros(R.shape[0])
    R_median = np.median(R, axis=0)  # global reference
    for i in range(1, R.shape[0]-1):
        local_diff = np.sum(np.abs(R[i,:] - R[i-1,:]))
        global_diff = np.sum(np.abs(R[i,:] - R_median))
        novelty[i] = 0.5 * local_diff + 0.5 * global_diff  # balance local/global

    # 4. Smooth novelty
    novelty = gaussian_filter1d(novelty, sigma=kernel_size)

    # 5. Select threshold based on percentile of novelty
    print(f"Selecting novelty peaks above {percentile}%")
    threshold = np.percentile(novelty, percentile)

    # 6. Peak picking with minimum section duration
    distance_frames = int(min_section_s * sr / hop_length)
    peaks, _ = find_peaks(novelty, height=threshold, distance=distance_frames)

    times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop_length)

    # Optional plot for debugging
    if verbose:
        times_sec = librosa.frames_to_time(np.arange(len(novelty)), sr=sr, hop_length=hop_length)
        peak_times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop_length)

        plt.figure(figsize=(12,4))
        plt.plot(times_sec, novelty, label="Novelty")
        plt.plot(peak_times, novelty[peaks], "rx", label="Detected peaks")
        plt.title("Structural Novelty and Peaks")
        plt.xlabel("Time (s)")
        plt.ylabel("Novelty")
        plt.legend()
        plt.savefig("novelty_plot.png", dpi=300, bbox_inches="tight")
        print(f"Saved novelty plot to novelty_plot.png")

    return np.unique(times).tolist()

# ===========================
#     Tempo Detections
# ===========================

def estimate_local_bpm(audio, sr, start_s, end_s):
    """
    Estimate BPM for a specific time segment.
    Returns None if BPM cannot be estimated.
    """
    start_sample = int(start_s * sr)
    end_sample = int(end_s * sr)

    segment = audio[start_sample:end_sample]
    if len(segment) < sr * 4:
        return None

    tempo, _ = librosa.beat.beat_track(y=segment, sr=sr)
    
    return float(tempo) if tempo > 0 else None


def compute_tempo_curve(audio, sr, hop_s=0.5, win_s=8.0):
    tempos = []
    times = []

    hop = int(hop_s * sr)
    win = int(win_s * sr)

    for start in range(0, len(audio) - win, hop):
        segment = audio[start:start + win]
        tempo, _ = librosa.beat.beat_track(y=segment, sr=sr)
        tempos.append(float(tempo) if tempo > 0 else np.nan)
        times.append((start + win / 2) / sr)

    return np.array(times), np.array(tempos)


def detect_tempo_change_boundaries(times, tempos, bpm_change_thresh, verbose=False):
    valid = ~np.isnan(tempos)
    tempos = tempos[valid]
    times = times[valid]
    if verbose:
        print(f"tempos: {tempos}")
        print(f"times: {times}")

    if len(tempos) < 2:
        return []

    dtempo = np.abs(np.diff(tempos))
    change_idxs = np.where(dtempo >= bpm_change_thresh)[0]

    # print("Detected tempo changes at:")
    # for idx in change_idxs:
    #     print(f"  Time {times[idx + 1]:.2f}s, ΔBPM {dtempo[idx]:.1f}")

    return times[change_idxs + 1].tolist()


# ================================
#  NOT USED: Compute Energy Score
#  Hard to map audio features to dance energy
# ================================
def compute_section_energy(y_section, sr, bpm):
    """
    Compute normalized energy score (0-1) using RMS + spectral centroid + spectral flux
    """
    # RMS (loudness)
    rms = np.mean(librosa.feature.rms(y=y_section))
    print(f"rms={rms}") 
    # 1. 0.22, 
    # 2. 0.27
    # 3. 0.05, 0.15, 0.2
    # 5. 0.11, 0.17, 0.16, 0.24
    # 7. 0.15, 0.19, 0.2, 0.22, 0.23

    # Spectral flux (activity)
    S = np.abs(librosa.stft(y_section))
    flux = np.mean(np.sqrt(np.sum(np.diff(S, axis=1)**2, axis=0)))
    print(f"flux={flux}")
    # 1. 71, 
    # 2. 65, 82, 71
    # 3. 27, 61, 68
    # 5. 46, 68, 64, 66, 77
    # 7. 49, 73, 75, 80, 84
    
    # Normalize features
    rms_norm = min(rms, 0.3)
    flux_norm = min(flux / 100, 1.0)
    bpm_norm = min(max(bpm / 200, 0), 1.0)
    
    energy_score = 0.2 * rms_norm + 0.1 * flux_norm + 0.7 * bpm_norm
    return min(max(energy_score, 0.0), 1.0)

# ================================
#  Structure + Tempo Segmentation
# ================================

def get_audio_sections(
    audio_filepath,
    novelty_percentile=95,
    bpm_change_thresh=10.0,
    hop_length=512,
    verbose=False):
    """
    - detect structural section changes
    - detect tempo changes
    - combine both structural and tempo novelty
    - estimate BPM per resulting section

    Returns:
      tempo_sections = [(bpm, start_s), ...]
      duration_s
      first_beat_s
    """
    print(f"Loading audio {audio_filepath}...")
    audio, sr = librosa.load(audio_filepath, sr=None)
    duration_s = len(audio) / sr

    if duration_s > 60.0:
        min_section_beats = 16
    else:
        min_section_beats = 8

    global_bpm, beat_frames = librosa.beat.beat_track(y=audio, sr=sr)
    seconds_per_beat = 60.0 / global_bpm
    min_section_s = min_section_beats * seconds_per_beat
    print(f"global BPM = {global_bpm}. Converting min_section_beats={min_section_beats} to min_section_s={min_section_s}.")

    if len(beat_frames) > 0:
        first_beat_s = librosa.frames_to_time(beat_frames[0], sr=sr, hop_length=hop_length)
    else:
        first_beat_s = 0.0

    print("Detecting structural boundaries...")
    structural_bounds = detect_structural_boundaries(
        audio, sr, 
        min_section_s=min_section_s,
        percentile=novelty_percentile,
        hop_length=hop_length, verbose=verbose
    )
    print(f"Structural boundaries start times: {structural_bounds}")

    print("Detecting tempo change boundaries...")
    times, tempos = compute_tempo_curve(
        audio, sr, 
        # tempo detection doesn't seem consistent enough
        win_s=min_section_s*2
    )
    tempo_bounds = detect_tempo_change_boundaries(
        times, tempos, bpm_change_thresh, verbose=verbose
    )
    print(f"Tempo boundaries start times: {tempo_bounds}")

    # Combine all boundaries
    boundaries = np.unique(
        np.concatenate((
            [first_beat_s],
            structural_bounds,
            tempo_bounds,
            [duration_s],
        ))
    ).tolist()

    print(f"Combined boundaries start times: {boundaries}")

    print("Estimating BPM per section...")
    tempo_sections = []
    start_s = boundaries[0]
    for i in range(len(boundaries) - 1):
        end_s = boundaries[i + 1]
        if end_s - start_s < min_section_s:
            print(f" section is too short: {end_s - start_s}")
            continue

        bpm = estimate_local_bpm(audio, sr, start_s, end_s)
        if bpm is not None:
            # y_section = audio[int(start_s*sr):int(end_s*sr)]
            # energy = compute_section_energy(y_section, sr, bpm)
            
            tempo_sections.append({
                "bpm": bpm,
                "start_s": start_s,
                # "energy": energy
            })
            start_s = end_s
        else:
            print(f" failed to estimate BPM for section {i}")

    if not tempo_sections:
        raise RuntimeError("Failed to detect any sections")

    print("Detected tempo sections:")
    for sec in tempo_sections:
        print(f"  BPM {sec["bpm"]:.1f} @ {sec["start_s"]:.2f}s")

    return tempo_sections, duration_s, first_beat_s



# ================================
#  Helper Function for Testing
# ================================
import soundfile as sf

def add_beeps_to_boundaries(audio, sr, boundaries, beep_freq=1000, beep_duration_s=0.1):
    """
    Insert short beeps at each boundary for listening.

    Parameters
    ----------
    audio : np.ndarray
        Original audio waveform
    sr : int
        Sample rate
    boundaries : list of float
        Times in seconds where section boundaries occur
    beep_freq : float
        Frequency of beep in Hz
    beep_duration_s : float
        Duration of each beep in seconds

    Returns
    -------
    new_audio : np.ndarray
        Audio with beeps inserted (overlapped, not concatenated)
    """
    new_audio = audio.copy()
    beep_samples = int(beep_duration_s * sr)
    t = np.arange(beep_samples) / sr
    beep = 0.5 * np.sin(2 * np.pi * beep_freq * t)

    for b in boundaries:
        idx = int(b * sr)
        # Ensure the beep fits in the audio
        if idx + beep_samples > len(new_audio):
            idx = len(new_audio) - beep_samples
            if idx < 0:
                # audio is shorter than beep, skip
                continue
        # Overlay beep
        new_audio[idx:idx + beep_samples] += beep

    # Prevent clipping
    new_audio = np.clip(new_audio, -1.0, 1.0)
    return new_audio

song_list = {
    1: "./data/bedroomTalk_opening.wav",
    2: "./data/janeDoe.wav",
    3: "./data/supernatural_opening.wav",
    4: "./data/tattoo_opening.wav",
    5: "./data/weWillRockYou_opening.wav",
    6: "./data/byeSummer_opening.wav",
    7: "./data/tattoo.wav",
    8: "./data/bedroomTalk.wav",
    9: "./data/weWillRockYou.wav",
}

import time
if __name__ == "__main__":
    songIndex = 5

    # 1 ~ 0.4
    # 2 ~ 0.5-0.6
    # 3 ~ 0.4-0.6
    # 5 ~ 0.3-0.6
    # 7 ~ 0.3-0.5


    start_time = time.time()  # Start timer
    tempo_sections, duration_s, first_beat_s = get_audio_sections(
        song_list[songIndex], 
        novelty_percentile=90,
        verbose=False
    )

    # Extract boundaries from tempo_sections
    boundaries = [sec["start_s"] for sec in tempo_sections]
    end_time = time.time()  # End timer
    print(f"Analysis took {end_time - start_time:.2f} seconds")

    # Load audio again to modify
    audio, sr = librosa.load(song_list[songIndex], sr=None)
    audio_with_beeps = add_beeps_to_boundaries(audio, sr, boundaries)

    # Save the new audio
    sf.write("./data/segmented.wav", audio_with_beeps, sr)
    
    print(f"Saved audio with beeps at section boundaries!")