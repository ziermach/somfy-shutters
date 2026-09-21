# HomeControll

App for controlling SIMU/Somfy RTS roller shutters through Pi-Somfy: live animated
state, plus user-defined automations. **Greenfield** — no application code exists yet.
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

Each feature gets its own git branch and its own `specs/<nnn>-<slug>/` directory,
both created by `.specify/scripts/bash/create-new-feature.sh`. Let the skills call
the scripts — don't hand-create spec directories.

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

- Branch per feature, named after the spec directory (e.g. `001-device-registry`).
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

Build/test/run commands: none yet — add them here with the first feature.

## Non-negotiables

These come straight from the constitution; read it before planning.

- **Never drive the CC1101 or send RTS frames.** Pi-Somfy is the only transmitter and the only
  holder of rolling-code counters. A second transmitter desyncs the motors and forces physical
  re-pairing at every window.
- **MQTT is the only integration point.** Publish to `somfy/<address>/level/cmd`, subscribe to
  `somfy/<address>/level/set_state`. Do not scrape or call Pi-Somfy's Flask UI. `<address>` is
  the RTS address from `operateShutters.conf` — read it, never invent it.
- **Positions are estimates, not feedback.** RTS is one-way; only the end stops are reliable.
  Never render an estimate as confirmed state. Animate from the configured travel time on send —
  do not wait for `set_state`, it arrives sparsely.
- **Offline by default.** The whole path must work with no internet.
- **Clients never speak MQTT.** The backend subscribes and relays over WebSocket.
- **Measured physical values** (travel times, addresses, direction) go in config, never
  hardcoded in logic.

## Open hardware questions

Blocking — measure on real hardware before any feature depends on them:

1. Direction of `level/cmd`: is 0 fully open or fully closed?
2. Per-window travel times, up and down separately.
3. Radio range to the furthest window (antenna attached).
4. Whether CC1101 receive mode gets enabled (tracks physical remotes, improves accuracy).
5. Rolling-code pairing per window; addresses recorded in `operateShutters.conf`.

CC1101 power: 3.3V only (Pi pin 1 or 17). 5V destroys the module.
