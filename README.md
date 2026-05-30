# JabloPy - Simple interface for Jablotron alarm systems
This service enables 2-way communication with a Jablotron alarm system without relying on cloud services or reverse-engineered APIs.

It exposes:
- The alarm system itself (supports arming and disarming of sections)
- Sensors (motion sensors, contact sensors, smoke and fire alarm, sirens, ...)
- System flags (arming delay, entry delay, ...)
- System state (armed, disarmed, alarm, ...)

## Requirements
- A JA-121-T interface module must be installed
- A bridge device that can translate the RS-485 bus to tcp (For instance: A Waveshare RS485 to WiFi/Ethernet Module)

## Installing and running
Create a virtual environment and install the project in editable mode:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the interactive CLI:

```powershell
jablopy --host 192.168.1.140 --port 8899 --pin 1234
```

Alternative ways to run the CLI during development:

```powershell
.\.venv\Scripts\python.exe -m jablopy.cli --host 192.168.1.140 --port 8899 --pin 1234
.\.venv\Scripts\python.exe src\jablopy\cli.py --host 192.168.1.140 --port 8899 --pin 1234
```

For a PyCharm run configuration, use either:

- Module name: `jablopy.cli`
- Script path: `src\jablopy\cli.py`

Set the working directory to the project root.

## Library usage

```python
from jablopy import JablotronClient, JablotronProtocol

command = JablotronProtocol.build_arm_partial_command("1234", sections=[1])
client = JablotronClient("192.168.1.140", 8899)
```
## example commands

```
Partially arm system with user 2 and pin 1234
2*1234 SETP 1 

user can be left out if there's only one
1234 SETP 1

Disarming the system
1234 UNSET 1

get flags
FLAGS

get device and sensor states:
PRFSTATE
```