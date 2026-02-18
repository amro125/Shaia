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