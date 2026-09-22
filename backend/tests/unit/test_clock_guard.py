"""T010: automations are held while the time cannot be trusted."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from somfy_shutters.automation.clock import ClockGuard, kernel_synchronised

NOW = datetime(2026, 9, 22, 6, 0, tzinfo=UTC)


def test_synchronised_and_moving_forward_is_reliable() -> None:
    assert ClockGuard(lambda: True).check(NOW, NOW - timedelta(minutes=1)).reliable


def test_an_unsynchronised_kernel_holds_everything() -> None:
    verdict = ClockGuard(lambda: False).check(NOW, None)
    assert not verdict.reliable and verdict.reason == "not_synchronised"


def test_a_clock_behind_the_last_heartbeat_went_backwards() -> None:
    """What fake-hwclock does after a power cut: restores the last shutdown time."""
    verdict = ClockGuard(lambda: True).check(NOW - timedelta(days=2), NOW)
    assert not verdict.reliable and verdict.reason == "went_backwards"


def test_a_little_jitter_behind_the_heartbeat_is_tolerated() -> None:
    assert ClockGuard(lambda: True).check(NOW - timedelta(seconds=30), NOW).reliable


def test_the_simulator_override_wins_both_ways() -> None:
    guard = ClockGuard(lambda: True)
    guard.override = False
    assert not guard.check(NOW, None).reliable
    guard = ClockGuard(lambda: False)
    guard.override = True
    assert guard.check(NOW, None).reliable


def test_the_real_kernel_check_answers_without_raising() -> None:
    assert kernel_synchronised() in (True, False)
