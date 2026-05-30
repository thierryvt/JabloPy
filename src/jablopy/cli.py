from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jablopy.client import JablotronClient
from jablopy.models import (
    FlagEvent,
    HeartbeatEvent,
    JablotronEvent,
    PrfStateEvent,
    SectionStateEvent,
    UnknownLineEvent,
)
from jablopy.protocol import JablotronProtocol


DEFAULT_HOST = "192.168.1.140"
DEFAULT_PORT = 8899
CONTROL_COMMANDS = {"set", "setp", "unset"}


@dataclass(frozen=True)
class CliCommand:
    command: str
    should_exit: bool = False


def parse_sections(parts: list[str]) -> list[int] | None:
    if not parts:
        return None

    return [int(part) for part in parts]


def build_cli_command(line: str, pin: str | None) -> CliCommand | None:
    line = line.strip()

    if not line:
        return None

    parts = line.split()
    verb = parts[0].lower()
    args = parts[1:]

    if verb in {"quit", "exit"}:
        return CliCommand(command="", should_exit=True)

    if verb in {"help", "?"}:
        print_help()
        return None

    if verb == "raw":
        if not args:
            raise ValueError("raw requires a command")

        return CliCommand(command=" ".join(args))

    if verb == "state":
        return CliCommand(
            command=JablotronProtocol.build_state_command(parse_sections(args))
        )

    if verb == "flags":
        return CliCommand(
            command=JablotronProtocol.build_flags_command(parse_sections(args))
        )

    if verb == "prfstate":
        if args:
            raise ValueError("prfstate does not accept sections")

        return CliCommand(command=JablotronProtocol.build_prfstate_command())

    if verb in CONTROL_COMMANDS:
        if not pin:
            raise ValueError(f"{verb} requires --pin or use raw <full command>")

        sections = parse_sections(args) or (1,)
        command = JablotronProtocol.build_command(
            verb,
            pin=pin,
            sections=sections,
        )

        return CliCommand(command=command)

    return CliCommand(command=line)


def format_event(event: JablotronEvent) -> str:
    if isinstance(event, HeartbeatEvent):
        return f"[heartbeat] {event.received_at.isoformat()}"

    if isinstance(event, SectionStateEvent):
        previous = (
            f" previous={event.previous_state}"
            if event.previous_state is not None
            else ""
        )
        return f"[section] {event.section} {event.state}{previous}"

    if isinstance(event, FlagEvent):
        state = "ON" if event.active else "OFF"
        active_sections = " ".join(
            str(section) for section in sorted(event.active_sections)
        )
        active = f" active_sections={active_sections}" if active_sections else ""
        return f"[flag] {event.flag} section={event.section} {state}{active}"

    if isinstance(event, PrfStateEvent):
        active_devices = " ".join(
            str(device) for device in sorted(event.active_devices)
        )
        changed_devices = " ".join(
            f"{device}={'ON' if active else 'OFF'}"
            for device, active in sorted(event.changed_devices.items())
        )

        active = active_devices or "none"
        changed = f" changed={changed_devices}" if changed_devices else ""

        return f"[prfstate] active={active}{changed}"

    if isinstance(event, UnknownLineEvent):
        reason = f" ({event.reason})" if event.reason else ""
        return f"[unknown] {event.raw}{reason}"

    return f"[event] {event}"


def print_help() -> None:
    print(
        "Commands:\n"
        "  state [sections...]       Query section state, e.g. state 1\n"
        "  flags [sections...]       Query active flags, e.g. flags 1 2\n"
        "  prfstate                  Query device/sensor state\n"
        "  set [sections...]         Arm sections, defaults to section 1\n"
        "  setp [sections...]        Partially arm sections, defaults to section 1\n"
        "  unset [sections...]       Disarm sections, defaults to section 1\n"
        "  raw <command>             Send a raw command line unchanged\n"
        "  help                      Show this help\n"
        "  exit                      Quit"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive Jablotron RS485-over-TCP debug CLI"
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pin", help="Access code for set/setp/unset helpers")
    parser.add_argument(
        "--show-heartbeat",
        action="store_true",
        help="Print OK heartbeat events",
    )

    return parser.parse_args()


async def prompt_loop(client: JablotronClient, pin: str | None) -> None:
    loop = asyncio.get_running_loop()

    while True:
        try:
            line = await loop.run_in_executor(None, input, "> ")
            cli_command = build_cli_command(line, pin)

            if cli_command is None:
                continue

            if cli_command.should_exit:
                return

            await client.send_command(cli_command.command)
            print(f"[tx] {cli_command.command}")

        except EOFError:
            return
        except KeyboardInterrupt:
            return
        except Exception as ex:
            print(f"[error] {ex}")


async def wait_until_connected(client: JablotronClient) -> None:
    while not client.connected:
        await asyncio.sleep(0.1)


async def main() -> None:
    args = parse_args()
    client = JablotronClient(args.host, args.port)

    def listener(event: JablotronEvent) -> None:
        if isinstance(event, HeartbeatEvent) and not args.show_heartbeat:
            return

        print(format_event(event))

    client.add_listener(listener)

    print(f"Connecting to {args.host}:{args.port}...")
    await client.start()
    await wait_until_connected(client)
    print("Connected. Type help for commands.")

    try:
        await prompt_loop(client, args.pin)
    finally:
        await client.stop()


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
