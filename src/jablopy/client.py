from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Callable, Iterable

from .models import JablotronEvent, JablotronState
from .protocol import JablotronProtocol


_LOGGER = logging.getLogger(__name__)


class JablotronClient:
    def __init__(
        self,
        host: str = "192.168.1.140",
        port: int = 8899,
        reconnect_delay: float = 5,
        protocol: JablotronProtocol | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._reconnect_delay = reconnect_delay

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

        self._task: asyncio.Task[None] | None = None
        self._running = False

        self._protocol = protocol or JablotronProtocol()

        self._listeners: list[Callable[[JablotronEvent], None]] = []

    @property
    def state(self) -> JablotronState:
        return self._protocol.state

    @property
    def connected(self) -> bool:
        return self._protocol.state.connected

    def add_listener(self, listener: Callable[[JablotronEvent], None]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[JablotronEvent], None]) -> None:
        self._listeners.remove(listener)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        self._running = True
        self._task = asyncio.create_task(self._reader_loop())

    async def stop(self) -> None:
        self._running = False

        await self._close_connection()

        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

            self._task = None

    async def arm(self, pin: str, sections: Iterable[int] | int | None = (1,)) -> None:
        await self.send_command(self._protocol.build_arm_command(pin, sections=sections))

    async def arm_partial(
        self,
        pin: str,
        sections: Iterable[int] | int | None = (1,),
    ) -> None:
        await self.send_command(
            self._protocol.build_arm_partial_command(pin, sections=sections)
        )

    async def disarm(
        self,
        pin: str,
        sections: Iterable[int] | int | None = (1,),
    ) -> None:
        await self.send_command(
            self._protocol.build_disarm_command(pin, sections=sections)
        )

    async def request_state(self, sections: Iterable[int] | int | None = None) -> None:
        await self.send_command(self._protocol.build_state_command(sections=sections))

    async def request_flags(self, sections: Iterable[int] | int | None = None) -> None:
        await self.send_command(self._protocol.build_flags_command(sections=sections))

    async def request_prfstate(self) -> None:
        await self.send_command(self._protocol.build_prfstate_command())

    async def send_command(self, command: str) -> None:
        if not self._writer:
            raise RuntimeError("Not connected")

        self._writer.write((command + "\r\n").encode("ascii"))
        await self._writer.drain()

    async def _reader_loop(self) -> None:
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

    async def _connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(
            self._host,
            self._port,
        )

        self._protocol.state.connected = True

    async def _close_connection(self) -> None:
        writer = self._writer

        self._reader = None
        self._writer = None
        self._protocol.state.connected = False

        if writer:
            writer.close()

            with suppress(ConnectionError, OSError):
                await writer.wait_closed()

    async def _initial_sync(self) -> None:
        await self.request_state()
        await self.request_flags()
        await self.request_prfstate()

    async def _read_lines(self) -> None:
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

    def _notify(self, event: JablotronEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                _LOGGER.exception("Jablotron listener failed")
