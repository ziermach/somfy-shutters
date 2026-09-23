# Implementation Plan: Setting up shutters directly in the app

**Branch**: `009-direct-shutter-setup` (separate branch at the owner's request; `main` stays as
it is for testing) | **Date**: 2026-09-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-direct-shutter-setup/spec.md`

## Summary

The app becomes the interface for the whole life of a shutter, and the bridge becomes our own
fork. Pi-Somfy offers creating, programming, renaming and deleting only through its web
interface; the fork offers them on the message channel the app already speaks, and announces a
new shutter the moment it exists instead of at the next restart. The app gains a guided flow in
the style of the mock — name and travel time, PROG on the old remote, "PROG senden", "Hat
gewackelt?", or the power-cycle sequence with a stopwatch — and keeps every rule it had: it
never transmits, never invents an address, sends one programming frame per press. A
created-but-unpaired shutter stays out of the household until "Hat gewackelt". Against an
unforked bridge everything falls back to feature 005's guide.

## Technical Context

**Language/Version**: Python 3.11, TypeScript/Svelte 5 — unchanged. The fork is Pi-Somfy's own
Python 2/3-compatible code.

**Primary Dependencies**: none new, in the app or in the fork

**Storage**: existing `household_shutter` gains `pairing` and `estimate_seconds`; `state` gains
`deleted` ([data-model.md](./data-model.md))

**Testing**: pytest — the management request/response of
[contracts/mqtt-manage.md](./contracts/mqtt-manage.md) asserted without a broker (as feature 006
does), setup service and REST against the simulator's management side; vitest for the
power-cycle timing and the flow's wording; quickstart B against the fork and a local Mosquitto;
in the fork, a script that exercises the channel end to end

**Target Platform**: Raspberry Pi running the fork, Mosquitto and this app

**Project Type**: web application — backend, frontend, plus a fork of the bridge

**Performance Goals**: a new shutter drivable right after "Hat gewackelt"; a management answer
within 5 s or it counts as unavailable

**Constraints**: the app never transmits; never invents an address; one `program` per press,
never retried; every setup route needs `configure`; nothing published under `homeassistant/#`
by the app; management requests carry no secret

**Scale/Scope**: ≤ 20 shutters; one setup at a time per shutter

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. Pi-Somfy owns the radio** | Untouched. The bridge — forked or not — transmits every frame, holds every rolling code and assigns every address. No radio code in the app. |
| **II. MQTT is the only integration boundary** | Held, and *extended*: two more topics in the same `somfy/` namespace, `somfy/bridge/manage/request` outbound and `.../response` inbound. → **Amendment 1.3.0 → 1.4.0 (MINOR)**: name them, and state that management exists only on a bridge that offers it, with a fallback when it does not. Flask routes, HTML, database and config files remain forbidden, so the rationale is unchanged — this is the opposite of the `/cmd/` route first considered (research §1). |
| **III. Honest position state** | A new shutter starts unknown; an unpaired one reads "nicht angelernt" and is not drivable. A successful `program` means the bridge transmitted, never that the motor learned — the person answers that. |
| **IV. Local-first** | Broker and bridge on the same Pi. |
| **V. Single-Pi simplicity** | No new component, no new dependency. The fork replaces two patch files, so the deploy gets simpler rather than larger. |
| **Interface rule "addresses … never invented"** | The bridge returns the address; the app validates and stores it. |
| **Measured values in configuration** | The estimate typed at creation is stored per shutter and ranks below measurements (research §5). |

**Result**: pass, conditional on the amendment, which is the first task. Re-checked after Phase
1: the contracts add topics only; driving and state are untouched.

## Project Structure

### Documentation (this feature)

```text
specs/009-direct-shutter-setup/
├── plan.md
├── research.md              # why a fork, what it adds, pairing = unpairing, security
├── data-model.md            # pairing, estimate, deleted tombstone, setup session
├── quickstart.md            # simulator, the fork on a desk, the motor
├── contracts/
│   ├── rest.md              # /api/setup…, removal and rename with the bridge
│   └── mqtt-manage.md       # the management channel, and what the fork changes
└── tasks.md
```

### Source Code

```text
The fork — ziermach/Pi-Somfy, branch `somfy-shutters`, one commit per upstreamable change:
  1. announceShutter / withdrawShutter, called from add, rename, delete (no restart needed)
  2. the management channel on somfy/bridge/manage/{request,response}, idempotent by request_id
  3. sendMQTT(topic, msg, retain=True) — responses must not be retained
  4. the Pi 5 detection fix (today deploy/pi-somfy-pi5-detection.patch)

This repository:
.specify/memory/constitution.md           # principle II: the management topics (1.4.0)
deploy/README.md                          # clone the fork; the patch file retires
deploy/pi-somfy-pi5-detection.patch       # removed once the fork carries it

backend/src/somfy_shutters/
├── bridge/base.py          # the management port: add, program, rename, delete, available
├── bridge/mqtt.py          # request/response over the channel, 5 s, correlation by request_id
├── bridge/sim.py           # paired / learning per window, programs log, management side
├── setup.py                # NEW — SetupService: add, program, paired, delete; sessions; bridge names
├── roster.py               # unpaired rows, deleted tombstone, removal and rename with the bridge
├── roster_store.py         # pairing, estimate_seconds, state 'deleted' (migration)
├── calibration_store.py    # the estimate layer in the precedence
├── auth/gate.py            # CHANGES: /api/setup → shutter_setup
├── api/setup_routes.py     # NEW — contracts/rest.md, every route require(configure)
├── api/roster_routes.py    # removal ?bridge=true, preview bridge_managed, roster additions
├── api/rest.py             # rename follows the bridge; sim endpoints (learn, manage, programs)
└── main.py                 # wire the setup service

frontend/src/
├── lib/setup.ts                    # NEW — flow steps, power-cycle windows and judging (pure, tested)
├── lib/setup.svelte.ts             # NEW — setup store
├── routes/SetupShutter.svelte      # NEW — name + travel time → pairing → question → done
├── components/PowerCycle.svelte    # NEW — the stopwatch sequence
├── routes/Shutters.svelte          # "Nicht angelernt" section; add → setup or the 005 guide
├── components/RemoveShutter.svelte # bridge delete and unpair options, partial-failure answer
└── App.svelte                      # route
```

**Structure Decision**: existing layout. Management rides the existing MQTT adapter rather than
a second port, because it is the same boundary — one file still holds every topic name. The
setup flow is its own service: it owns sessions and touches manager, roster and audit.

## Design notes

- **Order**: amendment → the fork's four commits (each usable alone) → the app's management port
  and its tests → simulator → migration → setup service → routes → frontend flow → power cycle →
  removal and rename with the bridge → deploy docs → quickstarts.
- **The fork is built first** because everything else is tested against the simulator anyway, and
  because commit 1 alone already improves feature 005 (no restart after adding in Pi-Somfy's own
  interface).
- **No retries on `program`** (research §3): a repeated PROG during one learning mode undoes the
  pairing. QoS 1 may deliver twice, so the bridge deduplicates by `request_id`.
- **Fallback is silence**: an unforked bridge never answers; after 5 s the app says so and shows
  feature 005's guide (FR-018).
- **Upstream**: each fork commit is written to stand alone as a pull request to
  `Nickduino/Pi-Somfy`; commit 1 is the one most likely to be wanted there.

## Complexity Tracking

None. The fork removes a patch file instead of adding one, and no new component or dependency
appears on the Pi.

## Risks

- **Maintaining the fork.** Upstream keeps moving; the fork must be rebased now and then. Kept
  small, one concern per commit, and offered upstream to shrink it.
- **A stray PROG pairs the wrong motor** if two are in learning mode. Warnings before every send,
  `configure` only, audited.
- **Whoever may publish on `somfy/#` may now also manage shutters.** That is the broker's
  account, as for driving; the deploy guide already sets user and password.
- **Hardware**: the power-cycle windows and the pairing behaviour are unconfirmed on real motors
  (quickstart C).
