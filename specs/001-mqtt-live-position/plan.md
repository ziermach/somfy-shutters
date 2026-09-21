# Implementation Plan: Live position and movement

**Branch**: `main` (single-developer repository, no feature branches) | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-mqtt-live-position/spec.md`

## Summary

Give the house a control surface: every shutter with its position, commands that move
them, and a graphic that travels at the real speed rather than snapping. Underneath,
carry the honesty the constitution demands — every position states whether it is
certain, estimated, or unknown.

The backend owns all state. It talks to Pi-Somfy over MQTT only, and to clients over a
WebSocket for state plus REST for commands. Clients never touch the bus. The whole
Pi-Somfy side sits behind one port with two adapters, so the same system runs against a
simulated house when no hardware is reachable — which is most of development, since the
motors are not paired yet.

The one hard problem is [FR-017](./spec.md): a position report from Pi-Somfy is itself a
dead-reckoning estimate, not a reading, so it cannot simply overwrite ours.
[research.md](./research.md) settles that with a precedence rule based on who knows more
about what caused the movement.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5 (frontend)

**Primary Dependencies**: FastAPI · aiomqtt 2.5.x · Pydantic v2 · Svelte 5 + Vite. No
HTTP client library — the backend calls nothing outward.

**Storage**: SQLite, one file, for shutter state and its confidence. Which shutters
exist and their travel times live in a TOML config file, editable by hand.

**Testing**: pytest with `httpx` ASGI transport against the simulator adapter; Vitest
for frontend logic. One integration test against a real Mosquitto.

**Target Platform**: Raspberry Pi OS (bookworm, arm64), served to phone browsers on the
home network. Installable as a PWA.

**Project Type**: Web application — Python service plus a static frontend it serves.

**Performance Goals**: Command to first movement on screen under 200 ms (SC-001).
Animation at 60 fps on a mid-range phone. Movement visible on other clients within 1 s
(SC-003).

**Constraints**: Fully functional with no internet — no CDN, no external fonts, no cloud
API anywhere in the path. Runs alongside Pi-Somfy and Mosquitto on one Pi, so the
backend should idle well under 100 MB.

**Scale/Scope**: About 10 shutters, a handful of clients, one household. Roughly four
screens.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design.*

| Principle | Gate | Verdict |
|---|---|---|
| **I. Pi-Somfy owns the radio** | No SPI, no CC1101, no RTS framing, no rolling-code storage anywhere in this feature | **Pass.** The only outbound path is an MQTT publish. Nothing in the design has a radio concept. |
| **II. MQTT is the only integration point** | No calls to Pi-Somfy's Flask routes, no reading its files, no scraping | **Pass.** Two topics, published and subscribed. Pi-Somfy's `operateShutters.conf` is deliberately *not* read; addresses are configured here instead ([research.md §5](./research.md)). |
| **III. Honest position state** | Every position carries confidence; estimates never shown as readings; resync offered | **Pass.** Confidence is part of the entity, not a UI afterthought — a position cannot be serialised without it ([data-model.md](./data-model.md)). |
| **IV. Local-first operation** | Entire path works offline; sun times computed locally | **Pass, with one action.** No external service is called. The mock's Google Fonts link must not survive into the real frontend — fonts get self-hosted. Tracked as a task. |
| **V. Single-Pi simplicity** | No extra hardware, no orchestrator, no database server | **Pass.** One Python process, one SQLite file, static assets served by the same process. |

Interface rules from the constitution, each with a home in the design:

- Animation starts on send and runs the configured travel time — client-side, never
  waiting for `set_state` ([contracts/websocket.md](./contracts/websocket.md)).
- Clients never speak MQTT — enforced structurally: the bus is only reachable from the
  adapter, which is not exposed.
- Measured physical values live in configuration — `shutters.toml`, not code
  ([data-model.md](./data-model.md)).

**Post-Phase-1 re-check**: no change. The design adds a port/adapter seam and a
simulator, both examined in Complexity Tracking below and neither reaching production
behaviour.

## Project Structure

### Documentation (this feature)

```text
specs/001-mqtt-live-position/
├── plan.md              # This file
├── research.md          # Phase 0: the five decisions
├── data-model.md        # Phase 1: entities, storage, config
├── quickstart.md        # Phase 1: how to run and prove it works
├── contracts/           # Phase 1
│   ├── rest.md          #   commands and queries
│   ├── websocket.md     #   the state push
│   └── mqtt.md          #   the Pi-Somfy boundary (external, not ours to change)
└── tasks.md             # Phase 2, created by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/somfy_shutters/
│   ├── main.py              # FastAPI app, lifespan wiring, static mount
│   ├── config.py            # shutters.toml + settings, validation
│   ├── models.py            # Pydantic: Shutter, PositionEstimate, Movement, Command
│   ├── store.py             # SQLite persistence of state
│   ├── tracker.py           # the core: estimates, confidence, FR-017 reconciliation
│   ├── bridge/
│   │   ├── base.py          #   ShutterBridge port
│   │   ├── mqtt.py          #   real adapter (aiomqtt)
│   │   └── sim.py           #   simulated house: dead time, travel curve, loss rate
│   ├── api/
│   │   ├── rest.py          #   POST commands, GET state
│   │   └── ws.py            #   connection registry, snapshot on connect, broadcast
│   └── events.py            # internal pub/sub between tracker and api
└── tests/
    ├── unit/                # tracker rules, confidence transitions, config
    ├── integration/         # app + simulator through the real API surface
    └── contract/            # payload shapes match contracts/

frontend/
├── src/
│   ├── lib/
│   │   ├── connection.ts    # WebSocket with backoff, snapshot handling
│   │   ├── store.ts         # shutter state, one source for all views
│   │   └── animate.ts       # local time-based interpolation, the 60 fps part
│   ├── components/          # ShutterCard, WindowGraphic, ConfidenceBadge …
│   └── routes/              # overview, detail
├── static/fonts/            # self-hosted, no external origin (Principle IV)
└── tests/

config/
└── shutters.example.toml
```

**Structure Decision**: Backend and frontend split, because they are different languages
with different toolchains, and the frontend builds to static files the backend serves —
one process in production, two during development. Inside the backend, `tracker.py` is
deliberately free of I/O: it takes commands and reports, returns state and events, and
is therefore testable without a bus, a socket, or a clock.

## Complexity Tracking

Two additions go beyond the simplest thing that could work, so both are justified here.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Port/adapter seam around Pi-Somfy instead of calling aiomqtt directly | The shutters are not paired yet, so nearly all development happens without hardware; the seam is also what makes Principle II's swappability real rather than aspirational | Calling the MQTT client directly would make every test need a broker, and every hard case (drift, lost command, restart mid-travel) unreachable |
| A simulator that models dead time and a non-linear travel curve | Those are precisely the behaviours the app must cope with and cannot observe; a simulator that moved linearly would let wrong code pass | A trivial fake returning fixed positions proves the plumbing and nothing about the behaviour the feature exists for |

Neither ships into the production path: the simulator is selected only by configuration,
and the port is one small module.
