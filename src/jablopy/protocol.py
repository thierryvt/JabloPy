from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from .constants import CONTROL_COMMANDS, QUERY_COMMANDS
from .models import (
    CommandErrorEvent,
    FlagEvent,
    HeartbeatEvent,
    JablotronEvent,
    JablotronState,
    PrfStateEvent,
    SectionStateEvent,
    UnknownLineEvent,
)


class JablotronProtocol:
    def __init__(self) -> None:
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

        received_at = datetime.now(UTC)
        self._state.last_received = received_at

        if line == "OK":
            self._state.last_heartbeat = received_at
            return HeartbeatEvent(raw=line, received_at=received_at)

        if line == "ERROR" or line.startswith("ERROR:"):
            return self._parse_error(line)

        if line.startswith("STATE "):
            return self._parse_state(line)

        if line.startswith("PRFSTATE "):
            return self._parse_prfstate(line)

        return self._parse_flag(line)

    def _parse_error(self, line: str) -> CommandErrorEvent:
        if line == "ERROR":
            return CommandErrorEvent(raw=line)

        details = line.removeprefix("ERROR:").strip()
        code_text, separator, message = details.partition(" ")

        try:
            code = int(code_text)
        except ValueError:
            return CommandErrorEvent(raw=line, message=details or None)

        return CommandErrorEvent(
            raw=line,
            code=code,
            message=message.strip() if separator else None,
        )

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
