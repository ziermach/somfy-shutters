"""T043: lockouts and command buckets on a clock the test controls."""

from __future__ import annotations

from somfy_shutters.auth.throttle import Throttle


class Mono:
    def __init__(self) -> None:
        self.t = 5000.0

    def __call__(self) -> float:
        return self.t


def throttle(mono: Mono) -> Throttle:
    return Throttle(monotonic=mono)


def test_ten_failures_in_five_minutes_lock_the_source_for_fifteen() -> None:
    mono = Mono()
    t = throttle(mono)
    for _ in range(9):
        t.fail("10.0.0.5")
    assert t.locked("10.0.0.5") is None
    t.fail("10.0.0.5")
    assert t.locked("10.0.0.5") == 900
    mono.t += 899
    assert t.locked("10.0.0.5") is not None
    mono.t += 2
    assert t.locked("10.0.0.5") is None


def test_the_window_slides() -> None:
    mono = Mono()
    t = throttle(mono)
    for _ in range(9):
        t.fail("a")
        mono.t += 40  # nine failures spread over six minutes
    t.fail("a")
    assert t.locked("a") is None  # the oldest have left the five-minute window


def test_sources_are_independent() -> None:
    t = throttle(Mono())
    for _ in range(10):
        t.fail("a")
    assert t.locked("a") is not None and t.locked("b") is None


def test_bucket_burst_then_refill() -> None:
    mono = Mono()
    t = throttle(mono)
    assert [t.take("c_1") for _ in range(10)] == [None] * 10
    wait = t.take("c_1")
    assert wait is not None and 0 < wait <= 1
    assert t.take("c_2") is None  # another credential has its own bucket
    mono.t += 1
    assert t.take("c_1") is None
    assert t.take("c_1") is not None


def test_a_bucket_never_holds_more_than_its_burst() -> None:
    mono = Mono()
    t = throttle(mono)
    t.take("c")
    mono.t += 3600
    assert sum(t.take("c") is None for _ in range(20)) == 10
