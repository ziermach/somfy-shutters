"""Whether the time can be trusted enough to open a window by it (FR-013).

The Pi has no battery-backed clock. Raspberry Pi OS restores the last shutdown
time at boot and corrects it once NTP answers; until then it may be hours or days
behind. Two checks, either one enough to hold automations
(specs/003-shutter-automations/research.md §5):

1. the kernel does not consider the clock synchronised (Linux `adjtimex`);
2. the time is earlier than the last heartbeat written while it *was* reliable.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

TIME_ERROR = 5
"""adjtimex(2) return value: the clock is not synchronised."""

BACKWARDS_SLACK = timedelta(seconds=60)


@dataclass(frozen=True)
class ClockVerdict:
    reliable: bool
    reason: str | None = None
    """not_synchronised | went_backwards"""


def kernel_synchronised() -> bool:
    """Linux only. Anywhere else there is no cheap answer, so it counts as yes."""
    if not sys.platform.startswith("linux"):
        return True
    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        return True
    libc = ctypes.CDLL(libc_name, use_errno=True)
    # struct timex is ~200 bytes on 64-bit; a zeroed buffer with modes = 0 only reads.
    buffer = ctypes.create_string_buffer(512)
    state = libc.adjtimex(buffer)
    return state != TIME_ERROR and state != -1


class ClockGuard:
    def __init__(self, kernel_check: Callable[[], bool] = kernel_synchronised) -> None:
        self._kernel_check = kernel_check
        self.override: bool | None = None
        """Set by the simulator's /api/sim/clock; None means the real checks decide."""

    def check(self, now: datetime, last_heartbeat: datetime | None) -> ClockVerdict:
        if self.override is not None:
            return ClockVerdict(self.override, None if self.override else "not_synchronised")
        if not self._kernel_check():
            return ClockVerdict(False, "not_synchronised")
        if last_heartbeat is not None and now < last_heartbeat - BACKWARDS_SLACK:
            return ClockVerdict(False, "went_backwards")
        return ClockVerdict(True)
