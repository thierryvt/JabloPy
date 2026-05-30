from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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

    def get_section_state(self, section: int) -> str | None:
        return self.sections.get(section)

    def is_flag_active(self, flag: str, section: int) -> bool:
        return section in self.flags.get(flag, set())

    def active_flags_for_section(self, section: int) -> frozenset[str]:
        return frozenset(
            flag for flag, sections in self.flags.items() if section in sections
        )

    def active_devices(self) -> frozenset[int]:
        return frozenset(device for device, active in self.sensors.items() if active)


@dataclass(frozen=True)
class JablotronEvent:
    raw: str


@dataclass(frozen=True)
class ConnectionEvent(JablotronEvent):
    connected: bool


@dataclass(frozen=True)
class CommandErrorEvent(JablotronEvent):
    code: int | None = None
    message: str | None = None


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
