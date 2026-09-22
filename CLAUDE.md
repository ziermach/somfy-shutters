# somfy-shutters

App for controlling SIMU/Somfy RTS roller shutters through Pi-Somfy: live animated
state, plus user-defined automations. Features 001–004 are implemented against a simulated
house; nothing has run on real hardware yet.
Development is driven by [GitHub Spec Kit](https://github.com/github/spec-kit):
specification first, then plan, then tasks, then implementation.

## Spec-driven workflow

Do not write feature code before a spec exists. The pipeline, in order:

| Step | Skill | Produces |
|------|-------|----------|
| 1 | `/speckit-constitution` | `.specify/memory/constitution.md` — project principles |
| 2 | `/speckit-specify` | `specs/<nnn>-<slug>/spec.md` — what & why, no tech choices |
| 3 | `/speckit-clarify` *(optional)* | resolves ambiguities in the spec before planning |
| 4 | `/speckit-plan` | `plan.md` + design docs — how, incl. tech choices |
| 5 | `/speckit-tasks` | `tasks.md` — ordered, actionable work items |
| 6 | `/speckit-analyze` *(optional)* | cross-artifact consistency report |
| 7 | `/speckit-implement` | the actual code, task by task |

`/speckit-checklist` generates quality checklists after planning.
`/speckit-converge` assesses existing code and appends remaining work as tasks.

Each feature gets its own `specs/<nnn>-<slug>/` directory. Let the skills create it —
don't hand-create spec directories.

## Repository layout

```
.specify/
  memory/constitution.md   project principles — read before planning
  templates/               spec, plan, tasks, checklist templates
  scripts/bash/            helper scripts invoked by the skills
.claude/skills/speckit-*/  the spec-kit skills themselves
specs/<nnn>-<slug>/        one directory per feature (created on demand)
```

Treat `.specify/templates/` and `.specify/scripts/` as vendored: change them only
deliberately, since `specify init` overwrites them on upgrade.

## Conventions

- **Single-developer repository: commit straight to `main`, no feature branches.**
- Specs describe user-visible behavior and requirements; technology decisions
  belong in `plan.md`, not in `spec.md`.
- Keep the constitution current — the planning and analysis skills check against it.

## Stack

Fixed by the [constitution](.specify/memory/constitution.md) — deviations need an amendment,
not just a plan.

| Layer | Choice | Notes |
|-------|--------|-------|
| Radio bridge | Pi-Somfy + CC1101 (E07-M1101D-SMA) over SPI | third-party; owns rolling codes |
| Message bus | Mosquitto on the Pi | |
| Backend | Python + FastAPI | REST + WebSocket in one process |
| Scheduling | APScheduler (time), `astral` (sun) | `astral` computes offline, no API |
| Storage | SQLite | automation rules + history |
| Frontend | React or Svelte web app, installable as PWA | pick in the first plan |
| Animation | SVG or Canvas, time-interpolated in JS | |

Backend, broker and Pi-Somfy all run on the same Raspberry Pi. No extra hardware, no container
orchestrator, no DB server.

### Build, test, run

```bash
# backend (Python 3.11; system python may be older — uv fetches it)
cd backend && uv venv --python 3.11 .venv && uv pip install -e ".[dev]"
.venv/bin/uvicorn somfy_shutters.main:app --reload --host 0.0.0.0
.venv/bin/python -m pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .

# frontend
cd frontend && npm install
npm run dev            # proxies /api to localhost:8000
npm run build          # backend serves frontend/dist in production
npx svelte-check --tsconfig ./tsconfig.json
```

`config/shutters.toml` (gitignored) decides which shutters exist. With
`bridge.kind = "sim"` everything runs without a broker or hardware.
`general.timezone` (default `Europe/Berlin`) is the wall clock automations follow; an
optional `[location]` seeds the house coordinates once — after that the app's value wins.
In the simulator, `POST /api/sim/clock {"reliable": false}` exercises the held path.
Groups (feature 004) live in the app database and are edited in the app, never in
`shutters.toml`; memberships of shutters no longer configured are pruned at startup.

## Non-negotiables

These come straight from the constitution; read it before planning.

- **Never drive the CC1101 or send RTS frames.** Pi-Somfy is the only transmitter and the only
  holder of rolling-code counters. A second transmitter desyncs the motors and forces physical
  re-pairing at every window.
- **MQTT is the only integration point.** Publish to `somfy/<id>/command` (OPEN/CLOSE/STOP) and
  `somfy/<id>/set_position`; subscribe to `somfy/<id>/position`, `somfy/<id>/state` and
  `somfy/bridge/availability` (Pi-Somfy v3.1+; the old `level/cmd` topics are gone). Stop is
  always the explicit STOP — a position equal to the bridge's belief does nothing. Do not scrape
  or call Pi-Somfy's Flask UI. `<id>` is the RTS address from `operateShutters.conf` — read it,
  never invent it.
- **Positions are estimates, not feedback.** RTS is one-way; only the end stops are reliable.
  Never render an estimate as confirmed state. Animate from the configured travel time on send —
  do not wait for a position report, it arrives sparsely. Retained reports on connect are old
  news: they fill unknown positions, never count as movement.
- **Offline by default.** The whole path must work with no internet.
- **Clients never speak MQTT.** The backend subscribes and relays over WebSocket.
- **Measured physical values** (travel times, addresses, direction) go in config, never
  hardcoded in logic.

## Open hardware questions

Blocking — measure on real hardware before any feature depends on them:

1. ~~Direction~~ — answered by Pi-Somfy itself: 100 = open, 0 = closed. `invert_level` is ignored.
2. Per-window travel times, up and down separately.
3. Radio range to the furthest window (antenna attached).
4. Whether CC1101 receive mode gets enabled (tracks physical remotes, improves accuracy).
5. Rolling-code pairing per window; addresses recorded in `operateShutters.conf`.

CC1101 power: 3.3V only (Pi pin 1 or 17). 5V destroys the module.
