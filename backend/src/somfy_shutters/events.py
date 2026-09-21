"""A tiny in-process pub/sub.

Exists so tracker.py can announce what happened without importing the API layer.
That keeps the tracker free of I/O, which is what makes its rules cheap to test.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

Listener = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def publish(self, event: dict[str, Any]) -> None:
        if not self._listeners:
            return
        # Gathered so one slow client cannot hold up the others; exceptions are
        # returned rather than raised, since a broken listener must not break a
        # shutter command.
        await asyncio.gather(
            *(listener(event) for listener in list(self._listeners)),
            return_exceptions=True,
        )
