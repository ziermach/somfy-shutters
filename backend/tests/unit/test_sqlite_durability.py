"""Every store commits without waiting for the disk (WAL + synchronous=NORMAL).

On the Pi's USB stick a single FULL commit took 18 s, and the event loop waited with
it: commands between shutters, a STOP, every request. All stores share one file, so
one connection left on FULL is enough to bring that back.
"""

from pathlib import Path

import pytest

from somfy_shutters.auth.audit import AuditLog
from somfy_shutters.auth.store import AuthStore
from somfy_shutters.automation.store import AutomationStore
from somfy_shutters.calibration_store import CalibrationStore
from somfy_shutters.groups import GroupStore
from somfy_shutters.roster_store import RosterStore
from somfy_shutters.store import Store

NORMAL = 1

OPENERS = {
    "Store": lambda db, tmp: Store(db),
    "AuditLog": lambda db, tmp: AuditLog(db),
    "AuthStore": lambda db, tmp: AuthStore(db),
    "AutomationStore": lambda db, tmp: AutomationStore(db),
    "CalibrationStore": lambda db, tmp: CalibrationStore(db, tmp / "calibration.toml"),
    "GroupStore": lambda db, tmp: GroupStore(db),
    "RosterStore": lambda db, tmp: RosterStore(db),
}


@pytest.mark.parametrize("name", sorted(OPENERS))
def test_store_commits_without_waiting_for_the_disk(name: str, tmp_path: Path) -> None:
    # Opened alone, so a store cannot rely on another one having switched the file.
    store = OPENERS[name](tmp_path / "state.db", tmp_path)
    try:
        conn = store._conn
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == NORMAL
    finally:
        store.close()
