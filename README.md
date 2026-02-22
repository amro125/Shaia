# Shaia
MINI SHIMON. This is a repo for all the code for Shaia: a xylophone and drumming robot 

## Dev Setup
### Using Virtual Environment

One-time set up: Create the virtual environment (one-time setup)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Activate the environment before each development session (this ensures all required dependencies are available):
```
source venv/bin/activate
```

After installing new dependencies, update `requirements.txt` so other developers can stay in sync:
```
pip freeze > requirements.txt
```

### Run a module
```
python -m Dance.dance
```

## Dev Setup for Gesture Input with UI Control
In the future, we may switch to use physical buttons to control gesture recording and editing, but for now we test with UI. 
This is how we set up the development environment to test the full stack.

```
React UI (browser)
        ↓ HTTP
FastAPI Bridge (8000)
        ↓ OSC UDP
Python Server (9010)
        ↓
Dynamixel Motors
```

1. Run OSC bridge
```
cd Shaia/GestureInput/
uvicorn osc_bridge:app --reload --port 8000
```
2. Run Frontend and visit the local host
```
cd Shaia/GestureInput/ui
npm run dev
```
3. Run the python code for recording and editing gestures
```
cd Shaia
python -m GestureInput.RecordEditGestures
```

