# CLI contract: recovery and first run

One console script, installed with the backend: `somfy-shutters`
(`[project.scripts]` in `backend/pyproject.toml`). It reads the same `SHUTTERS_CONFIG`
and `SHUTTERS_DB` as the service and opens the database directly; it never talks to the
running service over the network (FR-026).

## `somfy-shutters auth recover [--name NAME] [--token]`

Creates a way back in with all five abilities and records a `recovery` entry.

- Default: prints a pairing code valid 15 minutes.

  ```
  $ somfy-shutters auth recover
  Kopplungscode: K7Q-9XM  (gültig bis 14:32)
  Im Browser öffnen: http://<pi>:8000 — Code eingeben, Gerät benennen.
  ```

- `--token`: prints a full credential instead, for a headless client. `--name` names it
  (default "Wiederherstellung").

Exit `0` on success; `2` when the database or config cannot be opened, with the reason.

Works whether or not the service is running (SQLite serialises the writes). Leaves
shutters, calibration, rules, groups and history untouched (FR-025, SC-006).

## `somfy-shutters auth list`

Prints credentials — name, abilities, state, last used — never secrets. Read-only; for
checking after a recovery.

## First run after upgrading

No credential exists. The app shows the pairing screen; the upgrade note in
`deploy/README.md` says to run `somfy-shutters auth recover` once on the Pi.
