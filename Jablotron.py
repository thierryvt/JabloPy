from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable


CONTROL_COMMANDS = {"SET", "SETP", "UNSET"}
QUERY_COMMANDS = {"VER", "HELP", "STATE", "FLAGS", "PRFSTATE"}

_LOGGER = logging.getLogger(__name__)


@dataclass
class JablotronState:
    sections: dict[int, str] = field(default_factory=dict)
    flags: dict[str, set[int]] = field(default_factory=dict)
    sensors: dict[int, bool] = field(default_factory=dict)
    last_heartbeat: datetime | None = None
    connected: bool = False

    @property
    def section_state(self) -> str | None:
        return self.sections.get(1)

    def is_flag_active(self, flag: str, section: int) -> bool:
        return section in self.flags.get(flag, set())


@dataclass(frozen=True)
class JablotronEvent:
    raw: str


@dataclass(frozen=True)
class HeartbeatEvent(JablotronEvent):
    received_at: datetime


@dataclass(frozen=True)
class SectionStateEvent(JablotronEvent):
    section: int
    state: str
    previous_state: str | None


@dataclass(frozen=True)
class FlagEvent(JablotronEvent):
    flag: str
    section: int
    active: bool
    active_sections: frozenset[int]


@dataclass(frozen=True)
class PrfStateEvent(JablotronEvent):
    sensors: dict[int, bool]
    active_devices: frozenset[int]
    changed_devices: dict[int, bool]


@dataclass(frozen=True)
class UnknownLineEvent(JablotronEvent):
    reason: str | None = None


class JablotronProtocol:
    def __init__(self):
        self._state = JablotronState()

    @property
    def state(self) -> JablotronState:
        return self._state

    @classmethod
    def build_command(
        cls,
        command: str,
        pin: str | None = None,
        sections: Iterable[int] | int | None = None,
    ) -> str:
        command = command.strip().upper()

        if command in CONTROL_COMMANDS:
            if not pin:
                raise ValueError(f"{command} requires a PIN")

            parts = [pin, command]

        elif command in QUERY_COMMANDS:
            if pin:
                raise ValueError(f"{command} does not accept a PIN")

            if sections is not None and command not in {"STATE", "FLAGS"}:
                raise ValueError(f"{command} does not accept sections")

            parts = [command]

        else:
            raise ValueError(f"Unsupported command: {command}")

        parts.extend(cls._format_sections(sections))

        return " ".join(parts)

    @classmethod
    def build_arm_command(
        cls,
        pin: str,
        sections: Iterable[int] | int | None = (1,),
    ) -> str:
        return cls.build_command("SET", pin=pin, sections=sections)

    @classmethod
    def build_arm_partial_command(
        cls,
        pin: str,
        sections: Iterable[int] | int | None = (1,),
    ) -> str:
        return cls.build_command("SETP", pin=pin, sections=sections)

    @classmethod
    def build_disarm_command(
        cls,
        pin: str,
        sections: Iterable[int] | int | None = (1,),
    ) -> str:
        return cls.build_command("UNSET", pin=pin, sections=sections)

    @classmethod
    def build_state_command(
        cls,
        sections: Iterable[int] | int | None = None,
    ) -> str:
        return cls.build_command("STATE", sections=sections)

    @classmethod
    def build_flags_command(
        cls,
        sections: Iterable[int] | int | None = None,
    ) -> str:
        return cls.build_command("FLAGS", sections=sections)

    @classmethod
    def build_prfstate_command(cls) -> str:
        return cls.build_command("PRFSTATE")

    @staticmethod
    def _format_sections(sections: Iterable[int] | int | None) -> list[str]:
        if sections is None:
            return []

        if isinstance(sections, int):
            sections = (sections,)

        formatted = []

        for section in sections:
            section = int(section)

            if section <= 0:
                raise ValueError("Section numbers must be positive")

            formatted.append(str(section))

        return formatted

    def handle_line(self, line: str) -> JablotronEvent | None:
        line = line.strip()

        if not line:
            return None

        if line == "OK":
            received_at = datetime.now(timezone.utc)
            self._state.last_heartbeat = received_at
            return HeartbeatEvent(raw=line, received_at=received_at)

        if line.startswith("STATE "):
            return self._parse_state(line)

        if line.startswith("PRFSTATE "):
            return self._parse_prfstate(line)

        return self._parse_flag(line)

    def _parse_state(self, line: str) -> JablotronEvent:
        parts = line.split()

        if len(parts) < 3:
            return UnknownLineEvent(raw=line)

        try:
            section = int(parts[1])
        except ValueError:
            return UnknownLineEvent(raw=line, reason="Invalid section number")

        state = parts[2]
        previous_state = self._state.sections.get(section)
        self._state.sections[section] = state

        return SectionStateEvent(
            raw=line,
            section=section,
            state=state,
            previous_state=previous_state,
        )

    def _parse_flag(self, line: str) -> JablotronEvent:
        parts = line.split()

        if len(parts) != 3:
            return UnknownLineEvent(raw=line)

        flag_name = parts[0]

        try:
            section = int(parts[1])
        except ValueError:
            return UnknownLineEvent(raw=line, reason="Invalid section number")

        if parts[2] == "ON":
            self._state.flags.setdefault(flag_name, set()).add(section)
            return FlagEvent(
                raw=line,
                flag=flag_name,
                section=section,
                active=True,
                active_sections=frozenset(self._state.flags[flag_name]),
            )

        if parts[2] == "OFF":
            if flag_name in self._state.flags:
                self._state.flags[flag_name].discard(section)

                if not self._state.flags[flag_name]:
                    del self._state.flags[flag_name]

            return FlagEvent(
                raw=line,
                flag=flag_name,
                section=section,
                active=False,
                active_sections=frozenset(self._state.flags.get(flag_name, set())),
            )

        return UnknownLineEvent(raw=line, reason="Invalid flag state")

    def _parse_prfstate(self, line: str) -> JablotronEvent:
        parts = line.split()

        if len(parts) != 2:
            return UnknownLineEvent(raw=line)

        try:
            sensors = self.decode_prfstate(parts[1])
        except ValueError:
            return UnknownLineEvent(raw=line, reason="Invalid PRFSTATE value")

        previous_sensors = self._state.sensors
        self._state.sensors = sensors

        if previous_sensors:
            changed_devices = {
                device: active
                for device, active in sensors.items()
                if previous_sensors.get(device) != active
            }
        else:
            changed_devices = {}

        active_devices = frozenset(
            device for device, active in sensors.items() if active
        )

        return PrfStateEvent(
            raw=line,
            sensors=sensors,
            active_devices=active_devices,
            changed_devices=changed_devices,
        )

    @staticmethod
    def decode_prfstate(hex_string: str) -> dict[int, bool]:
        if len(hex_string) % 2:
            raise ValueError("PRFSTATE value must contain whole bytes")

        sensors = {}

        raw = bytes.fromhex(hex_string)

        device_index = 0

        for byte in raw:
            for bit in range(8):
                sensors[device_index] = bool(byte & (1 << bit))
                device_index += 1

        return sensors


class JablotronClient:
    def __init__(
        self,
        host: str = "192.168.1.140",
        port: int = 8899,
        reconnect_delay: float = 5,
        protocol: JablotronProtocol | None = None,
    ):
        self._host = host
        self._port = port
        self._reconnect_delay = reconnect_delay

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

        self._task: asyncio.Task | None = None
        self._running = False

        self._protocol = protocol or JablotronProtocol()

        self._listeners: list[Callable[[JablotronEvent], None]] = []

    @property
    def state(self) -> JablotronState:
        return self._protocol.state

    @property
    def connected(self) -> bool:
        return self._protocol.state.connected

    def add_listener(self, listener: Callable[[JablotronEvent], None]):
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[JablotronEvent], None]):
        self._listeners.remove(listener)

    async def start(self):
        if self._task and not self._task.done():
            return

        self._running = True
        self._task = asyncio.create_task(self._reader_loop())

    async def stop(self):
        self._running = False

        await self._close_connection()

        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

            self._task = None

    async def arm(self, pin: str, sections: Iterable[int] | int | None = (1,)):
        await self.send_command(
            self._protocol.build_arm_command(pin, sections=sections)
        )

    async def arm_partial(self, pin: str, sections: Iterable[int] | int | None = (1,)):
        await self.send_command(
            self._protocol.build_arm_partial_command(pin, sections=sections)
        )

    async def disarm(self, pin: str, sections: Iterable[int] | int | None = (1,)):
        await self.send_command(
            self._protocol.build_disarm_command(pin, sections=sections)
        )

    async def request_state(self, sections: Iterable[int] | int | None = None):
        await self.send_command(
            self._protocol.build_state_command(sections=sections)
        )

    async def request_flags(self, sections: Iterable[int] | int | None = None):
        await self.send_command(
            self._protocol.build_flags_command(sections=sections)
        )

    async def request_prfstate(self):
        await self.send_command(self._protocol.build_prfstate_command())

    async def send_command(self, command: str):
        if not self._writer:
            raise RuntimeError("Not connected")

        self._writer.write((command + "\r\n").encode("ascii"))
        await self._writer.drain()

    async def _reader_loop(self):
        try:
            while self._running:
                try:
                    await self._connect()
                    await self._initial_sync()
                    await self._read_lines()
                except Exception as ex:
                    _LOGGER.warning("Jablotron disconnected: %s", ex)
                finally:
                    await self._close_connection()

                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
        finally:
            await self._close_connection()

    async def _connect(self):
        self._reader, self._writer = await asyncio.open_connection(
            self._host,
            self._port,
        )

        self._protocol.state.connected = True

    async def _close_connection(self):
        writer = self._writer

        self._reader = None
        self._writer = None
        self._protocol.state.connected = False

        if writer:
            writer.close()

            with suppress(ConnectionError, OSError):
                await writer.wait_closed()

    async def _initial_sync(self):
        await self.request_state()
        await self.request_flags()
        await self.request_prfstate()

    async def _read_lines(self):
        if not self._reader:
            raise RuntimeError("Not connected")

        while self._running:
            line = await self._reader.readline()

            if not line:
                raise ConnectionError("Connection closed")

            self._dispatch_line(line.decode("ascii", errors="ignore"))

    def _dispatch_line(self, line: str) -> JablotronEvent | None:
        _LOGGER.debug("Jablotron RX: %s", line.rstrip())

        event = self._protocol.handle_line(line)

        if event:
            self._notify(event)

        return event

    def _notify(self, event: JablotronEvent):
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                _LOGGER.exception("Jablotron listener failed")
