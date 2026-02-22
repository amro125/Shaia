import React, { useState, useEffect, act } from "react";
import "./App.css";

const OSC_SERVER = "http://127.0.0.1:8000";

type Mode = "record" | "play" | "editHead" | "editNeck" | null;

async function sendCommand(endpoint: string) {
  try {
    await fetch(`${OSC_SERVER}/${endpoint}`, { method: "POST" });
  } catch (err) {
    console.error("Command failed:", err);
  }
}

async function getBackendMode(): Promise<Mode> {
  try {
    const res = await fetch(`${OSC_SERVER}/mode`);
    const data = await res.json();
    return data.mode as Mode;
  } catch {
    return null;
  }
}

export default function App() {
  const [activeMode, setActiveMode] = useState<Mode>(null);

  // Poll backend to catch auto-stop
  useEffect(() => {
    const interval = setInterval(async () => {
      const backendMode = await getBackendMode();
      // console.log("Backend mode:", backendMode, "Active mode:", activeMode);
      if (backendMode !== activeMode) {
        setActiveMode(backendMode);
      }
    }, 250);
    return () => clearInterval(interval);
  }, [activeMode]);

  const handleToggle = async (mode: Mode) => {
    // If clicking the active button → stop it
    if (activeMode === mode) {
      if (mode === "record" || mode === "play") {
        await sendCommand("stop")
        setActiveMode(null);
      }
      else if (mode === "editHead" || mode === "editNeck") {
        await sendCommand("stopEdit");
        // edit stops but playback continues
        setActiveMode("play");
      }
      return;
    }

    // If another mode is active
    if (activeMode !== null) {
      // allow edits if playback is active
      if ((mode === "editHead" || mode === "editNeck") && activeMode === "play") {
        // fall through to activate edit
      } else {
        return; // ignore all other cases
      }
    }

    // Activate selected mode
    if (mode === "record") await sendCommand("record");
    if (mode === "play") await sendCommand("play");
    if (mode === "editHead") await sendCommand("editHead");
    if (mode === "editNeck") await sendCommand("editNeck");

    setActiveMode(mode);
  };

  // Button disabling rules
  const isDisabled = (mode: Mode) => {
    switch (activeMode) {
      case "play":
        return !(mode === "editHead" || mode === "editNeck" || mode === "play"); // only play and edits enabled
      case "editHead":
      case "editNeck":
        return mode !== activeMode; // only the current edit enabled
      case "record":
        return mode !== "record"; // only record enabled
      default:
        // nothing active
        return mode === "editHead" || mode === "editNeck"; // edits disabled initially
    }
  };


  return (
    <div className="container">

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
  );
}
