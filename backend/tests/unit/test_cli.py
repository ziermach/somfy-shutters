"""T019, T040: `somfy-shutters auth recover|list` (contracts/cli.md)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from somfy_shutters import cli
from somfy_shutters.auth.audit import AuditLog
from somfy_shutters.auth.models import ALL_ABILITIES
from somfy_shutters.auth.store import AuthStore

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "shutters.example.toml"


@pytest.fixture
def pi(tmp_path, monkeypatch):
    config = tmp_path / "shutters.toml"
    config.write_text(
        EXAMPLE.read_text(encoding="utf-8").replace('# mode = "required"', 'mode = "required"'),
        encoding="utf-8",
    )
    db = tmp_path / "state.db"
    monkeypatch.setenv("SHUTTERS_CONFIG", str(config))
    monkeypatch.setenv("SHUTTERS_DB", str(db))
    return db


def test_recover_prints_a_code_that_pairs_with_every_ability(pi, capsys) -> None:
    service = AuthStore(pi)  # the running service holds the same file open
    assert cli.main(["auth", "recover"]) == 0
    out = capsys.readouterr().out
    code = re.search(r"Kopplungscode: (\w{3}-\w{3})", out).group(1)
    assert "gültig bis" in out
    _, credential, _ = service.redeem(code, "Laptop")
    assert credential.abilities == ALL_ABILITIES and credential.origin == "recovery"
    service.close()


def test_recover_is_recorded(pi) -> None:
    cli.main(["auth", "recover"])
    audit = AuditLog(pi)
    [entry] = audit.query()
    assert (entry.action, entry.actor.kind, entry.outcome) == ("recovery", "recovery", "accepted")
    audit.close()


def test_recover_with_token_prints_a_working_credential(pi, capsys) -> None:
    assert cli.main(["auth", "recover", "--token", "--name", "Kopf"]) == 0
    token = re.search(r"(sst_\w+)", capsys.readouterr().out).group(1)
    store = AuthStore(pi)
    assert store.resolve(token).name == "Kopf"
    store.close()


def test_list_prints_no_secret(pi, capsys) -> None:
    cli.main(["auth", "recover", "--token"])
    token = re.search(r"(sst_\w+)", capsys.readouterr().out).group(1)
    assert cli.main(["auth", "list"]) == 0
    out = capsys.readouterr().out
    assert "Wiederherstellung" in out and token not in out and "sst_" not in out


def test_unreadable_config_exits_2(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SHUTTERS_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("SHUTTERS_DB", str(tmp_path / "state.db"))
    assert cli.main(["auth", "recover"]) == 2
    assert "Konfiguration nicht lesbar" in capsys.readouterr().err
