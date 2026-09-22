<!--
Sync Impact Report
Version change: 1.2.0 → 1.3.0 (MINOR — materially expanded guidance, no principle removed or redefined)
Modified principles:
  - II. MQTT Is the Only Integration Boundary: the bridge's discovery announcements
    (`homeassistant/cover/+/config`) join the inbound topics; publishing under
    `homeassistant/#` is ruled out explicitly. Rule and rationale unchanged.
  - Interface rules: learning RTS addresses from those announcements counts as referencing
    them, never inventing them.
Added sections: none. Removed sections: none.
Driven by: specs/005-shutter-add-remove.
Templates requiring updates: none.
Follow-up updates: CLAUDE.md (non-negotiables), README.md,
  specs/006-pisomfy-mqtt-topics/contracts/mqtt.md (superseded in part).

Previous amendment:
Version change: 1.1.0 → 1.2.0 (MINOR — hardware rule materially changed, no principle touched)
Modified sections:
  - Technology and Hardware Constraints → hardware rules: the fixed CC1101 wiring moves from
    GPIO 21/20/19/16/26 to hardware SPI0 (GPIO 11/10/9/8) with GDO0 on GPIO4. The old pins
    are what Pi-Somfy documents for its optional *receiver* module over bit-banged SPI; its
    CC1101 *transmitter* backend (RFBackend = cc1101, written for the E07-M1101D-SMA) defaults
    to SPI0 bus 0 device 0 with the waveform on TXGPIO = 4. Wired the old way, the transmitter
    would not work with Pi-Somfy's defaults, and the receiver pins could never be used.
    Adds: SPI0 must be enabled (dtparam=spi=on).
Added sections: none. Removed sections: none.
Driven by: bring-up research on Pi-Somfy master (2026-08-28), before any module was wired.
Templates requiring updates: none.
Follow-up updates: deploy/README.md (wiring table, header sketch, SPI note; the Cirkit
  diagram shows the old wiring and is withdrawn until redrawn).

Previous amendment:
Version change: 1.0.0 → 1.1.0 (MINOR — materially updated guidance, no principle removed or redefined)
Modified principles:
  - II. MQTT Is the Only Integration Boundary: topic names updated to Pi-Somfy's current
    interface (v3.1, 2026-03-27). The removed `level/cmd` / `level/set_state` topics are
    replaced by `command`, `set_position`, `position`, `state` and `bridge/availability`.
    Rule and rationale unchanged.
  - Interface rules: "subscribes to set_state" → position, state and availability topics;
    "must not wait for a set_state message" → a position report.
Added sections: none. Removed sections: none.
Driven by: specs/006-pisomfy-mqtt-topics.
Templates requiring updates: none (.specify/templates/* do not name topics).
Follow-up updates: CLAUDE.md (non-negotiables, open question 1), README.md (architecture),
  specs/001-mqtt-live-position/contracts/mqtt.md (marked superseded by specs/006 contract).
-->

# somfy-shutters Constitution

somfy-shutters is a self-hosted app that controls SIMU/Somfy RTS roller shutters through
Pi-Somfy, displays their state as a live animation, and runs user-defined automations.

## Core Principles

### I. Pi-Somfy Owns the Radio (NON-NEGOTIABLE)

Pi-Somfy MUST remain the single process that holds RTS rolling-code state and transmits on
433.42 MHz. No component of this project may drive the CC1101 over SPI, send RTS frames, or
persist rolling counters. All shutter movement MUST be requested by publishing to the MQTT
command topic.

Rationale: rolling codes are the replay-protection mechanism of RTS. A second transmitter with
its own counter desynchronizes the motors and requires physical re-pairing at every window.

### II. MQTT Is the Only Integration Boundary

This project MUST talk to the shutter layer exclusively over MQTT topics — `somfy/<id>/command`
and `somfy/<id>/set_position` outbound; `somfy/<id>/position`, `somfy/<id>/state`,
`somfy/bridge/availability` and the bridge's discovery announcements
`homeassistant/cover/+/config` inbound. Nothing is ever published under `homeassistant/#`:
those topics belong to the bridge. Pi-Somfy's Flask routes, its HTML, its database, and its
config files MUST NOT be scraped, called, or written by this project.

Rationale: MQTT is Pi-Somfy's documented, supported interface; the web UI is not. Holding this
boundary keeps the transmitter swappable — moving to ESPSomfy-RTS changes an endpoint, not the app.

### III. Honest Position State (NON-NEGOTIABLE)

RTS is one-way: the motors report nothing. Only the two mechanical end stops are reliable; every
intermediate percentage is a time-based estimate and MUST be treated as such. The UI MUST NOT
present an estimate as confirmed feedback. It MUST expose the estimate's age or confidence when
drift is plausible, and MUST offer a resync that drives to a known end stop.

Rationale: a shutter graphic that silently lies is worse than no graphic — users act on it
(leaving for the day, closing up at night) and cannot tell when it has drifted.

### IV. Local-First Operation

The full control path — UI, backend, broker, Pi-Somfy — MUST work on the home network with no
internet connection. Sun-based triggers MUST be computed offline from coordinates. No cloud
service may sit in the path between a user action and a shutter moving.

Rationale: a shutter that will not close because an external API is down is a failed product;
this is house infrastructure, not an online service.

### V. Single-Pi Simplicity

The system MUST run alongside Pi-Somfy on one Raspberry Pi and MUST NOT require additional
hardware, a container orchestrator, or a standalone database server. New dependencies and new
moving parts MUST be justified against the alternative of doing without them.

Rationale: the deployment target is one small board maintained by one person; every added
component is something that breaks unattended.

## Technology and Hardware Constraints

Stack decisions are fixed at the constitution level; deviations require an amendment:

| Layer | Choice |
|-------|--------|
| Radio bridge | Pi-Somfy with CC1101 (E07-M1101D-SMA) over SPI |
| Message bus | Mosquitto on the Pi |
| Backend | Python + FastAPI (REST + WebSocket) |
| Scheduling | APScheduler for time triggers, `astral` for sun triggers (offline) |
| Storage | SQLite |
| Frontend | Web app (React or Svelte), installable as a PWA |
| Animation | SVG or Canvas, time-interpolated in JS |

Hardware rules:

- The CC1101 MUST be powered from 3.3V (Pi pin 1 or 17). 5V destroys the module (max ≈3.6V).
- The antenna MUST be attached before transmitting.
- Wiring is fixed as (hardware SPI0, Pi-Somfy's CC1101 transmitter default):
  VCC→pin 17/3.3V, MOSI→pin 19/GPIO10, MISO→pin 21/GPIO9, SCK→pin 23/GPIO11,
  CSN→pin 24/GPIO8 (CE0), GND→pin 25, GDO0→pin 7/GPIO4 (Pi-Somfy `TXGPIO`). GDO2 is not
  connected. SPI0 MUST be enabled (`dtparam=spi=on`).
- GPIO 21/20/19/16/26 (pins 40/38/35/36/37) stay free: they are Pi-Somfy's pins for an
  optional second CC1101 used as a receiver (open hardware question 4).

Interface rules:

- RTS addresses live in `operateShutters.conf` and are referenced by the app, never invented.
  Learning them from the bridge's discovery announcements is how they are referenced; a
  hand-written entry in the app's configuration is the other.
- The backend subscribes to the position, state and availability topics for all shutters and pushes changes to clients over
  WebSocket; clients MUST NOT connect to MQTT directly.
- Command animation starts on send and runs for the configured travel time; it MUST NOT wait
  for a position report, which arrives sparsely.

## Development Workflow

- Work is spec-driven: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` →
  `/speckit-implement`. Feature code MUST NOT be written before its spec exists.
- Specs describe behavior; technology choices belong in `plan.md` and must not contradict the
  stack table above.
- Physical unknowns MUST be resolved by live measurement before any feature depends on them.
  Open at ratification: the direction of `level/cmd` (whether 0 is open or closed), per-window
  travel times up and down, radio range to the furthest window, whether CC1101 receive mode is
  enabled, and per-window rolling-code pairing.
- A measured physical value (travel time, address, direction) MUST be recorded in configuration
  or documentation, never hardcoded in application logic.
- Changes touching the command path MUST be verified against real hardware, not only tests.

## Governance

This constitution supersedes other conventions in the repository. Where a plan, task, or review
conflicts with it, the constitution wins.

- Amendments are made by editing this file in a dedicated commit that states what changed and
  why, and bumping the version below.
- Versioning is semantic: MAJOR for removing or redefining a principle in a
  backward-incompatible way, MINOR for a new principle or materially expanded guidance, PATCH
  for clarifications and wording.
- `/speckit-plan` and `/speckit-analyze` check artifacts against this file; violations are either
  fixed or recorded with an explicit justification in the plan's complexity tracking.
- Runtime development guidance lives in `CLAUDE.md` and must stay consistent with this document.

**Version**: 1.3.0 | **Ratified**: 2026-09-21 | **Last Amended**: 2026-09-22
