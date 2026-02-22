# osc_bridge.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pythonosc.udp_client import SimpleUDPClient

app = FastAPI()

# Allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

osc_client = SimpleUDPClient("127.0.0.1", 9010)

# Track backend mode for polling
current_mode: str | None = None

@app.post("/record")
def record():
    global current_mode
    osc_client.send_message("/record", [])
    current_mode = "record"
    return {"status": "record sent"}

@app.post("/play")
def play():
    global current_mode
    osc_client.send_message("/play", [])
    current_mode = "play"
    return {"status": "play sent"}

@app.post("/editHead")
def edit_head():
    global current_mode
    osc_client.send_message("/editHead", [])
    current_mode = "editHead"
    return {"status": "editHead sent"}

@app.post("/editNeck")
def edit_neck():
    global current_mode
    osc_client.send_message("/editNeck", [])
    current_mode = "editNeck"
    return {"status": "editNeck sent"}

@app.post("/stop")
def stop():
    global current_mode
    osc_client.send_message("/stop", [])
    current_mode = None
    return {"status": "stop sent"}

@app.post("/stopEdit")
def stop_edit():
    global current_mode
    osc_client.send_message("/stopEdit", [])
    current_mode = "play"
    return {"status": "stop edit sent"}

@app.get("/mode")
def get_mode():
    """Return current mode so frontend can sync with backend if playback/edit stops automatically."""
    return {"mode": current_mode}
