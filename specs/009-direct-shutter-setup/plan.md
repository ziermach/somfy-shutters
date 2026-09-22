# Implementation Plan: Setting up shutters directly in the app

**Branch**: `009-direct-shutter-setup` (separate branch at the owner's request; `main` stays as
it is for testing) | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-direct-shutter-setup/spec.md`

## Summary

The app becomes the interface for the whole life of a shutter. A new `PiSomfyManager` asks the
bridge — through its `/cmd/` command route — to create a shutter (the bridge picks the address),
to send the programming signal, to rename and to delete. The bridge stays the only transmitter.
A guided flow in the style of the mock walks the person through it: name and travel time,
PROG on the old remote, "PROG senden", "Hat gewackelt?"; or the power-cycle sequence with a
stopwatch. A small patch to the bridge, shipped in `deploy/` like the one already there, makes a
new shutter commandable at once and clears a deleted one's announcement; without it the flow
asks for one bridge restart. Created-but-unpaired shutters stay out of the household until
"Hat gewackelt". Feature 005's guide remains the fallback.

## Technical Context

**Language/Version**: Python 3.11, TypeScript/Svelte 5 — unchanged

**Primary Dependencies**: none new. The bridge is called with the standard library
(`urllib.request` in `asyncio.to_thread`): a handful of requests per setup, no reason for an HTTP
client dependency (constitution V).

**Storage**: existing `household_shutter` gains `pairing` and `estimate_seconds`; `state` gains
`deleted` ([data-model.md](./data-model.md))

**Testing**: pytest — manager against a fake HTTP server (every command, error shape and
timeout of [contracts/pisomfy-cmd.md](./contracts/pisomfy-cmd.md)); setup service and REST
against the simulator's management side; vitest for the power-cycle timing and flow wording;
quickstart B against a real Pi-Somfy on a desk

**Target Platform**: Raspberry Pi next to Pi-Somfy v3.1+, web server reachable from the app
(same Pi: loopback)

**Project Type**: web application — backend, frontend, plus a patch file for the bridge

**Performance Goals**: new shutter drivable right after "Hat gewackelt" (patched bridge);
announcement of a new shutter awaited ≤ 5 s

**Constraints**: the app never transmits; never invents an address; one `program` per press,
never retried; the bridge password never leaves the server; every setup route needs
`configure`; nothing published under `homeassistant/#` by the app

**Scale/Scope**: ≤ 20 shutters; one setup at a time per shutter

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. Pi-Somfy owns the radio** | Untouched. The app sends *requests*; Pi-Somfy transmits every frame, holds every rolling code, assigns every address. No radio code in the app. |
| **II. MQTT is the only integration boundary** | **Violated as written** — the principle forbids calling Pi-Somfy's Flask routes. → **Amendment 1.3.0 → 1.4.0 (MINOR)**: MQTT stays the only path for *driving* and *state*; shutter **management** (create, program, rename, delete) may use Pi-Somfy's `/cmd/` command route, confined to one adapter file, with a working fallback when it is unavailable. Rationale kept: the swappable-transmitter goal holds because management sits behind its own port (`bridge/manage.py`), as MQTT does. HTML, database and config files remain off limits. |
| **III. Honest position state** | A new shutter starts unknown; an unpaired one is shown as "nicht angelernt", never as drivable. "PROG senden" succeeding says the bridge sent it, never that the motor learned — the person answers that. |
| **IV. Local-first** | Pi-Somfy runs on the same Pi; loopback. |
| **V. Single-Pi simplicity** | No new component or dependency; the bridge patch is a text file applied once, like the existing one. |
| **Interface rule "addresses … never invented"** | The bridge returns the address; the app validates and stores it, never computes one. |
| **Measured values in configuration** | The estimate typed at creation is stored per shutter and ranks below measurements (research §5). |

**Result**: pass, **conditional on the amendment**, which is the first task. Re-checked after
Phase 1: the contracts keep driving on MQTT and management in one adapter — unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/009-direct-shutter-setup/
├── plan.md
├── research.md            # the bridge's command route, the patch, pairing = unpairing, security
├── data-model.md          # pairing, estimate, deleted tombstone, setup session
├── quickstart.md          # simulator, Pi-Somfy on a desk, motor
├── contracts/
│   ├── rest.md            # /api/setup…, removal and rename with the bridge
│   └── pisomfy-cmd.md     # the bridge's /cmd/ as used, and the patch
└── tasks.md
```

### Source Code

```text
.specify/memory/constitution.md           # principle II: management route (1.4.0)
deploy/pi-somfy-live-shutters.patch       # NEW — announce/subscribe on add, withdraw on delete
deploy/README.md                          # apply the patch; manage_url, loopback binding

backend/src/somfy_shutters/
├── bridge/manage.py        # NEW — PiSomfyManager (urllib), SimManager; errors
├── bridge/sim.py           # paired / learning per window; programs log; patched toggle
├── setup.py                # NEW — SetupService: add, program, paired, delete; sessions; bridge names
├── roster.py               # unpaired rows, deleted tombstone, removal/rename with the bridge
├── roster_store.py         # pairing, estimate_seconds, state 'deleted' (migration)
├── calibration_store.py    # estimate layer in the precedence
├── config.py               # bridge.manage_url, bridge.manage_password
├── auth/gate.py            # CHANGES: /api/setup → shutter_setup
├── api/setup_routes.py     # NEW — contracts/rest.md, all require(configure)
├── api/roster_routes.py    # removal ?bridge=true, preview bridge_managed, roster additions
├── api/rest.py             # rename follows the bridge; sim endpoints
└── main.py                 # build the manager; wire the setup service

frontend/src/
├── lib/setup.ts                    # NEW — flow steps, power-cycle windows and judging (pure, tested)
├── lib/setup.svelte.ts             # NEW — setup store: create, program, paired, delete
├── routes/SetupShutter.svelte      # NEW — name + travel time → pairing → question → done
├── components/PowerCycle.svelte    # NEW — the stopwatch sequence
├── routes/Shutters.svelte          # "Nicht angelernt" section; add → setup or 005 guide
├── components/RemoveShutter.svelte # bridge delete + unpair options, partial-failure answer
└── App.svelte                      # route
```

**Structure Decision**: existing layout. Management gets its own port file beside the MQTT
adapter so the amended principle II stays checkable by looking at one file; the setup flow is a
service of its own because it holds sessions and talks to three parts (manager, roster, audit).

## Design notes

- **Order**: amendment → manager + fake server tests → simulator management side → migration →
  setup service → routes → frontend flow → power cycle → removal/rename with the bridge →
  patch file + deploy docs → quickstarts.
- **No retries on `program`** (research §3): a repeated PROG during one learning mode undoes the
  pairing. A timeout is reported as "unklar, ob gesendet" and the person decides.
- **Patched or not** is learned per `add` from the live announcement, not configured (research §2).
- **Frontend entry**: "+ Rolladen hinzufügen" opens the new flow when `management.available`,
  else feature 005's guide with the reason (FR-018). The mock's screens are the visual reference.

## Complexity Tracking

| Violation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Calling Pi-Somfy's `/cmd/` route (principle II) | Creating, programming, renaming and deleting are not available over MQTT; without them the app cannot be the interface the owner asked for | Way B (adding MQTT commands to the bridge) keeps II intact but means maintaining a larger bridge fork; the owner chose A. Confined to one adapter with a fallback. |

## Risks

- **`/cmd/` is not a documented API** and may change with a bridge update. Mitigation: one
  adapter, contract tests against recorded answers, fallback to feature 005's guide.
- **Unauthenticated management on the bridge's own port** (a property of Pi-Somfy today). The
  deploy guide recommends binding it to loopback once the app is the interface.
- **A stray PROG pairs the wrong motor** if two are in learning mode. Warnings before every send;
  `configure` only; audited.
- **Hardware**: the power-cycle windows and the pairing behaviour are to be confirmed on the
  motors (quickstart C).
