# Implementation Plan: Speaking the radio bridge's current interface

**Branch**: `main` (single-developer repository, no feature branches) | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-pisomfy-mqtt-topics/spec.md`

## Summary

Move the one file that speaks MQTT — `bridge/mqtt.py` — from Pi-Somfy's removed
`level/cmd`/`level/set_state` topics to its current ones: explicit `command`
(OPEN/CLOSE/STOP), `set_position`, retained `position` and `state` reports, and the bridge's
own `availability`. The port gains one verb, `send_stop`, because on the current bridge a
position equal to its belief is a no-op and the old way of stopping would let a shutter run
on. Reports carry their kind and whether they are retained, so the burst the broker replays
on connect fills unknown positions without faking movement, and a live `opening`/`closing`
the app did not cause is recognised as a physical remote at once. The simulator speaks the
same, constitution principle II is amended to name the current topics, and existing setups
keep working untouched.

## Technical Context

**Language/Version**: Python 3.11, TypeScript/Svelte 5 — unchanged

**Primary Dependencies**: aiomqtt 2.5 (exposes the retain flag on received messages) —
unchanged; no new dependencies

**Storage**: none changed

**Testing**: pytest; the MQTT adapter is tested without a broker by feeding its pure
handling and publish-planning functions the exact topic/payload shapes (research §8);
optional walk against a local Mosquitto in the quickstart

**Target Platform**: Raspberry Pi OS next to current Pi-Somfy (v3.1+); macOS for development

**Project Type**: web application — backend change only, frontend untouched

**Performance Goals**: bridge-offline shown within 5 s (SC-003); no measurable cost

**Constraints**: nothing above the port may learn a topic name (principle II); stop must
never be a position request; retained reports must never count as movement; old configs
must validate and behave correctly without edits

**Scale/Scope**: one adapter, the simulator, two stop call sites, the tracker's report
handling, one constitution amendment, docs

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. Pi-Somfy owns the radio** | Still only publishes requests to Pi-Somfy; no RTS, no SPI, no counters. `STOP` is a request like any other. |
| **II. MQTT is the only integration boundary** | Still MQTT only; Pi-Somfy's Flask routes and files untouched. **The principle names `level/cmd` and `level/set_state`, which no longer exist** — this plan includes the amendment (FR-015): same rule, same rationale, current topic names. Version 1.0.0 → 1.1.0 with a Sync Impact Report. |
| **III. Honest position state** | Improves: a stop that stops, a bridge that is really there before commands count as sent, and retained old news never presented as fresh movement. |
| **IV. Local-first** | Unchanged — broker and bridge on the Pi. |
| **V. Single-Pi simplicity** | No new component, no new dependency. |
| **Stack table** | Unchanged. |
| **Command path verified on hardware** | The command path changes; verification joins the pending hardware tasks (quickstart C). Until then, correctness rests on the adapter's topic-level tests and the local-Mosquitto walk. |
| **Measured values in config** | The only physical question this touches — direction — is now declared by the bridge; `invert_level` is retired, not replaced by a constant. |

**Result**: pass, conditional on the amendment being made as part of this feature (it is
task-listed first). No complexity to justify.

## Project Structure

### Documentation (this feature)

```text
specs/006-pisomfy-mqtt-topics/
├── plan.md              # this file
├── research.md          # what the bridge does, and the decisions
├── data-model.md        # extended Report, port, tracker reactions
├── quickstart.md        # simulator, local Mosquitto, Pi
├── contracts/
│   └── mqtt.md          # supersedes 001's MQTT contract
└── tasks.md             # /speckit-tasks
```

### Source Code

```text
.specify/memory/constitution.md          # principle II amendment, v1.1.0

backend/src/somfy_shutters/
├── bridge/base.py        # Report(kind, state, retained); ShutterBridge.send_stop
├── bridge/mqtt.py        # new topics, availability, retain flag, id spelling, OPEN/CLOSE/STOP
├── bridge/sim.py         # new report kinds, retained burst, availability, send_stop
├── tracker.py            # retained fill-only; live movement → external movement
├── commands.py           # stop → send_stop
├── api/calibration_routes.py  # abort → send_stop
├── api/rest.py           # POST /api/sim/movement (simulator only)
├── config.py             # invert_level: accepted, ignored, warned
└── main.py               # pump passes the whole Report to the tracker

backend/tests/
├── unit/test_mqtt_adapter.py       # topics/payloads in and out, retain, availability, case
├── unit/test_level_translation.py  # becomes: inversion is gone, warning on true
├── unit/test_reconciliation.py     # retained fill-only; live opening → external
├── integration/…                   # every 001–004 scenario, against the updated simulator
└── contract/test_sim_movement.py

specs/001-mqtt-live-position/contracts/mqtt.md   # marked superseded, link to 006
CLAUDE.md, README.md                             # topic names, stop, invert_level
```

**Structure Decision**: the existing layout. The whole integration change stays inside
`bridge/`, with two call sites and the tracker's report handling as the only reach beyond
it — the port-and-adapter seam of feature 001 doing its job.

## Design notes

- **Order**: amendment → port and `Report` → simulator (so the suite keeps running) →
  tracker handling → stop call sites → MQTT adapter → config warning → docs.
- **The tracker's `handle_report`** takes the `Report` rather than `(address, level)`;
  `main.on_report` and the simulator's injected reports adapt. The calibration run's
  disturbance check (FR-029 of 002) listens to live position reports only.
- **Movement during our own travel** is recognised by the existing movement and bridge-run
  window of feature 001; no new bookkeeping.
- **Availability in the simulator** replaces the direct `set_connected` toggle's meaning:
  offline now means "the bridge announced offline", which is what a real crash looks like.

## Complexity Tracking

None.

## Risks

- **Identity spelling on real hardware.** Mitigated by case-insensitive matching and
  learning the spelling from the retained burst; verified on the Pi.
- **Brokers configured with MQTT 5 "retain as published"** would mark live messages as
  retained and make every report "old news". Mosquitto's default and MQTT 3.1.1 (which the
  adapter uses) do not; noted in the contract.
- **Physical remotes without the bridge's receiver** send no `opening`/`closing`; the old
  two-report heuristic remains as the fallback.
- **A live `open`/`closed` state without a position report** would be ignored; the bridge
  always publishes the position first (its `set_state`), so this is theoretical.
