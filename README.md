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

## Commands
### Supported commands
Control commands:

| Command | Description |
| --- | --- |
| `SET` | Arm system fully |
| `SETP` | Arm system partially |
| `UNSET` | Disarm system |

Usage:

```text
<userId>*<pin> <command> <sections>
```

Query commands:

| Command | Description |
| --- | --- |
| `VER` | Get version info from device |
| `HELP` | Get list of valid commands |
| `STATE` | Get current state of each section |
| `FLAGS` | Get active system flags |
| `PRFSTATE` | Get device and sensor states |

Usage:

```text
<command>
```

### Example commands

```text
# Partially arm section 1 with user 2 and pin 1234
2*1234 SETP 1 

# User can be left out if there is only one
1234 SETP 1

# Disarm section 1
1234 UNSET 1

# Get flags
FLAGS

# Get device and sensor states
PRFSTATE
```

## Statuses
### Section statuses

| Status | Description |
| --- | --- |
| `READY` | Normal mode |
| `ARMED_PART` | Partially set |
| `ARMED` | Set |
| `MAINTENANCE` | Maintenance |
| `SERVICE` | Service |
| `BLOCKED` | Blocked after an alarm |
| `OFF` | Section disabled |

### Flags

| Flag | Description |
| --- | --- |
| `INTERNAL_WARNING` | Internal siren active |
| `EXTERNAL_WARNING` | External siren active |
| `FIRE_ALARM` | Fire alarm |
| `INTRUDER_ALARM` | Intruder alarm |
| `PANIC_ALARM` | Panic alarm |
| `ENTRY` | Entrance delay |
| `EXIT` | Exit delay |
