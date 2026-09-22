"""T008: manual beats measured beats default, and the app never rewrites the human's file."""

from __future__ import annotations

import pytest

from somfy_shutters.calibration_store import CalibrationService, CalibrationStore
from somfy_shutters.config import Settings
from somfy_shutters.models import Direction, MeasurementRun, RunKind, utcnow

CONFIG = {
    "general": {"default_travel_seconds": 20},
    "bridge": {"kind": "sim"},
    "shutter": [
        # a hand-typed value, in one direction only
        {
            "id": "wohnzimmer",
            "name": "Wohnzimmer",
            "address": "0x279621",
            "travel_up_seconds": 25.0,
        },
        {"id": "kueche", "name": "Küche", "address": "0x279622"},
    ],
}


@pytest.fixture
def service(tmp_path):
    settings = Settings.model_validate(CONFIG)
    store = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    yield CalibrationService(settings, store)
    store.close()


def measure(service, shutter_id, direction, total, count=3):
    for _ in range(count):
        service.record(
            MeasurementRun(
                shutter_id=shutter_id,
                direction=direction,
                dead_seconds=0.7,
                total_seconds=total,
                kind=RunKind.GUIDED,
                recorded_at=utcnow(),
            )
        )


def test_default_when_nothing_is_known(service) -> None:
    value = service.effective("kueche", Direction.UP)
    assert value.travel_seconds == 20
    assert value.source == "default"


def test_measured_beats_the_default(service) -> None:
    measure(service, "kueche", Direction.UP, 12.4)
    value = service.effective("kueche", Direction.UP)
    assert value.travel_seconds == 12.4
    assert value.source == "measured"
    assert value.runs == 3


def test_manual_beats_measured(service) -> None:
    measure(service, "wohnzimmer", Direction.UP, 18.2)
    value = service.effective("wohnzimmer", Direction.UP)
    assert value.travel_seconds == 25.0, "a value a person typed must win"
    assert value.source == "manual"


def test_the_overridden_measurement_is_not_discarded(service) -> None:
    """Overriding hides a measurement; it must not delete it."""
    measure(service, "wohnzimmer", Direction.UP, 18.2)
    assert service.effective("wohnzimmer", Direction.UP).runs == 3
    assert len(service.runs_for("wohnzimmer")) == 3


def test_directions_are_independent(service) -> None:
    """FR-014: a value measured one way is never applied to the other."""
    measure(service, "kueche", Direction.UP, 12.4)
    assert service.effective("kueche", Direction.UP).travel_seconds == 12.4
    assert service.effective("kueche", Direction.DOWN).source == "default"


def test_manual_in_one_direction_does_not_leak(service) -> None:
    assert service.effective("wohnzimmer", Direction.UP).source == "manual"
    assert service.effective("wohnzimmer", Direction.DOWN).source == "default"


def test_clearing_reverts_to_the_default(service, tmp_path) -> None:
    measure(service, "kueche", Direction.UP, 12.4)
    service.clear("kueche")
    assert service.effective("kueche", Direction.UP).source == "default"
    assert service.runs_for("kueche") == []
    # the human's file was never a write target in the first place
    assert not (tmp_path / "shutters.toml").exists()


def test_measurements_survive_a_restart_through_the_toml(tmp_path) -> None:
    settings = Settings.model_validate(CONFIG)
    store = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    service = CalibrationService(settings, store)
    measure(service, "kueche", Direction.UP, 12.4)
    store.close()

    store2 = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    revived = CalibrationService(settings, store2)
    value = revived.effective("kueche", Direction.UP)
    store2.close()

    assert value.travel_seconds == 12.4
    assert value.source == "measured"


def test_the_written_file_is_readable_by_a_person(service, tmp_path) -> None:
    measure(service, "kueche", Direction.UP, 12.4)
    text = (tmp_path / "calibration.toml").read_text()
    assert "[kueche.up]" in text
    assert "travel_seconds = 12.4" in text
    assert "shutters.toml" in text, "the file should say how to override it"
