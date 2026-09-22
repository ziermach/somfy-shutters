"""`somfy-shutters` on the Pi (specs/008-api-auth-audit/contracts/cli.md).

Recovery and the first run after upgrading are the same thing: somebody with a
shell on the machine asks for a way in. This opens the database directly and never
talks to the running service over the network, so there is nothing here an
attacker on the network could reach (FR-026).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .auth.audit import AuditLog
from .auth.models import ALL_ABILITIES, RECOVERY, ordered
from .auth.store import AuthStore
from .auth.tokens import format_code
from .config import ConfigError, load_settings

RECOVERY_MINUTES = 15


def _paths() -> tuple[Path, Path]:
    from .main import DEFAULT_CONFIG, DEFAULT_DB

    return (
        Path(os.environ.get("SHUTTERS_CONFIG", DEFAULT_CONFIG)),
        Path(os.environ.get("SHUTTERS_DB", DEFAULT_DB)),
    )


def recover(name: str, token: bool) -> int:
    config_path, db_path = _paths()
    try:
        settings = load_settings(config_path)
    except ConfigError as exc:
        print(f"Konfiguration nicht lesbar: {exc}", file=sys.stderr)
        return 2
    if not db_path.parent.is_dir():
        print(f"Datenbank nicht gefunden: {db_path}", file=sys.stderr)
        return 2
    tz = settings.general.tz
    store = AuthStore(db_path)
    audit = AuditLog(db_path)
    try:
        if token:
            credential, value = store.issue(name, ALL_ABILITIES, origin="recovery")
            audit.record(
                RECOVERY,
                "recovery",
                "accepted",
                target=credential.id,
                detail={"kind": "token", "name": name},
            )
            print(f"Zugang „{name}“: {value}")
            print("Wird nur jetzt angezeigt. Als Bearer-Token verwenden.")
        else:
            record, code = store.mint(ALL_ABILITIES, None, RECOVERY_MINUTES)
            audit.record(
                RECOVERY,
                "recovery",
                "accepted",
                target=record.id,
                detail={"kind": "pairing_code", "abilities": ordered(record.abilities)},
            )
            until = record.expires_at.astimezone(tz).strftime("%H:%M")
            print(f"Kopplungscode: {format_code(code)}  (gültig bis {until})")
            print("Im Browser öffnen: http://<pi>:8000 — Code eingeben, Gerät benennen.")
    finally:
        store.close()
        audit.close()
    return 0


def list_credentials() -> int:
    _, db_path = _paths()
    if not db_path.is_file():
        print(f"Datenbank nicht gefunden: {db_path}", file=sys.stderr)
        return 2
    store = AuthStore(db_path)
    try:
        now = store.clock()
        for c in store.list():
            used = c.last_used_at.strftime("%Y-%m-%d %H:%M") if c.last_used_at else "nie"
            abilities = ",".join(ordered(c.abilities))
            print(f"{c.id}  {c.name:<24} {c.state(now):<8} {abilities:<40} {used}")
    finally:
        store.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="somfy-shutters")
    groups = parser.add_subparsers(dest="group", required=True)
    auth = groups.add_parser("auth", help="Zugänge")
    commands = auth.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("recover", help="Einen Weg zurück in die App erzeugen")
    rec.add_argument("--name", default="Wiederherstellung")
    rec.add_argument("--token", action="store_true", help="Zugang statt Kopplungscode ausgeben")
    commands.add_parser("list", help="Zugänge anzeigen, ohne Geheimnisse")
    args = parser.parse_args(argv)
    if args.command == "recover":
        return recover(args.name, args.token)
    return list_credentials()


if __name__ == "__main__":
    raise SystemExit(main())
