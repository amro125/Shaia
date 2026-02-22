import React, { useState, useEffect, useRef } from "react";
import "./App.css";
import * as Tone from "tone";

const OSC_SERVER = "http://127.0.0.1:8000";

type Mode = "record" | "play" | "editHead" | "editNeck" | null;

async function sendCommand(endpoint: string) {
  try { await fetch(`${OSC_SERVER}/${endpoint}`, { method: "POST" }); }
  catch (err) { console.error("Command failed:", err); }
}

async function getBackendMode(): Promise<Mode> {
  try {
    const res = await fetch(`${OSC_SERVER}/mode`);
    const data = await res.json();
    return data.mode as Mode;
  } catch { return null; }
}

export default function App() {
  const [activeMode, setActiveMode] = useState<Mode>(null);

  // Poll backend to catch auto-stop
  useEffect(() => {
    const interval = setInterval(async () => {
      const backendMode = await getBackendMode();
      if (backendMode !== activeMode) setActiveMode(backendMode);
    }, 250);
    return () => clearInterval(interval);
  }, [activeMode]);

  // ---------------- METRONOME ----------------
  const [bpm, setBpm] = useState(120);
  const [bpmInput, setBpmInput] = useState(bpm.toString());
  const [beatsPerBar, setBeatsPerBar] = useState(4);
  const [beatsInput, setBeatsInput] = useState(beatsPerBar.toString());
  const [metroPlaying, setMetroPlaying] = useState(false);
  const [currentBeat, setCurrentBeat] = useState(0);
  const beatCounterRef = useRef(0);
  const synthRef = useRef<Tone.MembraneSynth | null>(null);

  const scheduleMetronome = () => {
    // clear old events
    Tone.Transport.cancel();

    // reset counter
    beatCounterRef.current = 0;
    setCurrentBeat(1);

    // create synth if needed
    if (!synthRef.current) {
      synthRef.current = new Tone.MembraneSynth({
        pitchDecay: 0.01,
        octaves: 1,
        oscillator: { type: "square" },
        envelope: { attack: 0.001, decay: 0.05, sustain: 0.01, release: 0.05 }
      }).toDestination();
    }

    // schedule repeating loop from current Transport position
    Tone.Transport.scheduleRepeat((time) => {
      const beat = beatCounterRef.current;

      // downbeat = first beat of bar
      const isDownbeat = beat === 0;
      synthRef.current?.triggerAttackRelease(isDownbeat ? "C5" : "C4", "16n", time);

      // increment counter
      beatCounterRef.current = (beat + 1) % beatsPerBar;

      // update UI
      setCurrentBeat(beat + 1);
    }, "4n", 0); // start immediately at current Transport position
  };

  const toggleMetronome = async () => {
    await Tone.start();
    if (metroPlaying) {
      Tone.Transport.stop();
      setMetroPlaying(false);
      setCurrentBeat(0);
      return;
    }

    Tone.Transport.bpm.value = bpm;
    scheduleMetronome();
    Tone.Transport.start();
    setMetroPlaying(true);
  };

  // Update BPM on the fly
  useEffect(() => {
    if (metroPlaying) {
      Tone.Transport.bpm.value = bpm;
    }
  }, [bpm, metroPlaying]);

  // Update time signature dynamically
  useEffect(() => {
    if (metroPlaying) {
      scheduleMetronome(); // cancel old schedule & reschedule
    }
  }, [beatsPerBar, metroPlaying]);

  // ---------------- AUDIO PLAYER ----------------
  const [audioFile, setAudioFile] = useState<File | null>(null);

  // ---------------- ROBOT CONTROL ----------------
  const handleToggle = async (mode: Mode) => {
    if (activeMode === mode) {
      if (mode === "record" || mode === "play") { await sendCommand("stop"); setActiveMode(null); }
      else if (mode === "editHead" || mode === "editNeck") { await sendCommand("stopEdit"); setActiveMode("play"); }
      return;
    }
    if (activeMode !== null && !((mode === "editHead" || mode === "editNeck") && activeMode === "play")) return;

    if (mode === "record") await sendCommand("record");
    if (mode === "play") await sendCommand("play");
    if (mode === "editHead") await sendCommand("editHead");
    if (mode === "editNeck") await sendCommand("editNeck");
    setActiveMode(mode);
  };

  const isDisabled = (mode: Mode) => {
    switch (activeMode) {
      case "play": return !(mode === "editHead" || mode === "editNeck" || mode === "play");
      case "editHead":
      case "editNeck": return mode !== activeMode;
      case "record": return mode !== "record";
      default: return mode === "editHead" || mode === "editNeck";
    }
  };

  return (
    <div className="container-horizontal">
      {/* LEFT SIDE PANEL */}
      <div className="left-panel">

        {/* METRONOME */}
        <div className="region metronome">
          <h3>Metronome</h3>
          <div className="sub-controls">
            <div className="input-group">
              <label htmlFor="bpm-input">BPM</label>
              <input
                id="bpm-input"
                type="number"
                value={bpmInput}
                min={20}
                max={120}
                onChange={(e) => setBpmInput(e.target.value)}
                onBlur={() => {
                  // parse, clamp, update state
                  let val = Number(bpmInput);
                  if (isNaN(val)) val = 120; // fallback default
                  if (val < 20) val = 20;
                  if (val > 120) val = 120;
                  setBpm(val);
                  setBpmInput(val.toString());
                }}
              />
            </div>

            <div className="input-group">
              <label htmlFor="ts-input">Time Sig.</label>
              <input
                type="number"
                value={beatsInput}
                min={1}
                max={8}
                onChange={(e) => setBeatsInput(e.target.value)}
                onBlur={() => {
                  let val = Number(beatsInput);
                  if (isNaN(val)) val = 4;
                  if (val < 1) val = 1;
                  if (val > 8) val = 8;
                  setBeatsPerBar(val);
                  setBeatsInput(val.toString());
                }}
              />
            </div>
          </div>

          <button className="small-button" onClick={toggleMetronome}>
            {metroPlaying ? "Stop Metronome" : "Start Metronome"}
          </button>

          <div className="beat-indicator">
            {Array.from({ length: beatsPerBar }).map((_, i) => (
              <div
                key={i}
                className={`beat ${currentBeat - 1 === i ? "active" : ""}`}
              />
            ))}
          </div>
        </div>

        {/* AUDIO PLAYER */}
        <div
          className="region audio-player"
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith("audio/")) setAudioFile(file);
          }}
          onDragOver={(e) => e.preventDefault()}
        >
          <h3>Audio Player</h3>
          <div
            className="drop-box"
            onClick={() => {
              const input = document.getElementById("audio-input") as HTMLInputElement;
              input?.click(); // trigger hidden file input
            }}
          >
            {audioFile ? (
              <span>🎵 {audioFile.name}</span>
            ) : (
              <span>Drag & drop audio file here</span>
            )}
          </div>

          <input
            type="file"
            accept="audio/*"
            id="audio-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file && file.type.startsWith("audio/")) setAudioFile(file);
            }}
            hidden
          />

          {audioFile && <audio controls src={URL.createObjectURL(audioFile)} />}
        </div>

      </div>

      {/* RIGHT MAIN CONTROLS */}
      <div className="right-panel">

        {/* RECORD REGION */}
        <div className="region record">
          <button
            className={`big-button ${activeMode === "record" ? "active" : ""}`}
            onClick={() => handleToggle("record")}
            disabled={isDisabled("record")}
          >
            {activeMode === "record" ? "STOP RECORD" : "Record All"}
          </button>
          <p>Recording all joints will overwrite anything you recorded before.</p>
        </div>

        {/* PLAYBACK + EDIT REGION */}
        <div className="region playback">
          <button
            className={`big-button ${activeMode === "play" ? "active" : ""}`}
            onClick={() => handleToggle("play")}
            disabled={isDisabled("play")}
          >
            {(activeMode === "play" || activeMode?.startsWith("edit")) ? "STOP PLAYBACK" : "Playback"}
          </button>

          <div className="sub-controls">
            <button
              className={`small-button ${activeMode === "editHead" ? "active" : ""}`}
              onClick={() => handleToggle("editHead")}
              disabled={isDisabled("editHead")}
            >
              {activeMode === "editHead" ? "STOP EDIT HEAD" : "Edit Head"}
            </button>

            <button
              className={`small-button ${activeMode === "editNeck" ? "active" : ""}`}
              onClick={() => handleToggle("editNeck")}
              disabled={isDisabled("editNeck")}
            >
              {activeMode === "editNeck" ? "STOP EDIT NECK" : "Edit Neck"}
            </button>
          </div>

          <p>You can edit one joint while the other keeps dancing to your recorded moves.</p>
        </div>
      </div>
    </div>
  );
}