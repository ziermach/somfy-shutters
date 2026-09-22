---

description: "Task list for feature 006, speaking Pi-Somfy's current MQTT interface"
---

# Tasks: Speaking the radio bridge's current interface

**Input**: Design documents from `/specs/006-pisomfy-mqtt-topics/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/mqtt.md](./contracts/mqtt.md)

**Tests**: Included. The adapter is the one place that can silently break everything, and it cannot be exercised against a real bridge here — so every topic, payload and flag in [contracts/mqtt.md](./contracts/mqtt.md) is asserted without a broker, and every existing feature 001–004 scenario must still pass against the updated simulator (SC-006).

**Organization**: Grouped by user story. Stories 1–3 are all P1 and share the new port; they are independently testable once Phase 2 is done.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Separate file, no unfinished dependency — order does not matter
- **[Story]**: US1–US5 from [spec.md](./spec.md)

## Path Conventions

Existing layout: `backend/src/somfy_shutters/`, `backend/tests/`. Frontend untouched.

---

## Phase 1: Setup — governance first

- [X] T001 Amend `.specify/memory/constitution.md` principle II: replace `somfy/<address>/level/cmd` outbound and `somfy/<address>/level/set_state` inbound with `somfy/<id>/command` and `somfy/<id>/set_position` outbound, `somfy/<id>/position`, `somfy/<id>/state` and `somfy/bridge/availability` inbound; keep the rule ("the only integration boundary; Flask routes, HTML, database and config files MUST NOT be scraped, called, or written") and the rationale verbatim; bump **1.0.0 → 1.1.0**, set Last Amended to 2026-09-22, prepend a Sync Impact Report naming feature 006 and the dependent files (CLAUDE.md, README.md, specs/001 contract)
- [X] T002 [P] Mark `specs/001-mqtt-live-position/contracts/mqtt.md` as superseded at the top, linking to [contracts/mqtt.md](./contracts/mqtt.md), without deleting its reasoning

---

## Phase 2: Foundational — the port and the simulator

**Purpose**: the new port shape and a simulator that speaks it, so the whole suite keeps running while the adapter is rewritten.

**⚠️ No story work before this phase is done.**

- [X] T003 Extend `Report` in `backend/src/somfy_shutters/bridge/base.py`: fields `address`, `kind: "position" | "movement"` (default `"position"`), `percent: int | None` (**0–100 for position, None for movement**), `state: "opening" | "closing" | "open" | "closed" | "stopped" | None`, `retained: bool = False`; existing `Report(address, percent)` calls must keep meaning a live position report. Add abstract `send_stop(address)` to `ShutterBridge` with a docstring: success means handed over, never that the motor stopped
- [X] T004 Update `backend/src/somfy_shutters/bridge/sim.py` per research §7: implement `send_stop` (halt the motor where it is, bridge belief = current); emit a live movement report `opening`/`closing` when a travel starts and `open`/`closed`/`stopped` when it ends; on `start()` put one **retained** position and one retained state report per shutter on the queue; model availability — `connected` is broker-up and announced-online, `set_connected(False)` means the bridge announced `offline`
- [X] T005 Change `backend/src/somfy_shutters/main.py` `on_report` to take the whole `Report`: pass position reports to the calibration run's disturbance check **only when live**, and hand every report to the tracker
- [X] T006 Add `Tracker.handle(report)` in `backend/src/somfy_shutters/tracker.py` as the entry point for every `Report`, keeping `handle_report(address, level)` for live positions so feature 001's tests stay as they are; a live position report behaves exactly as before; retained and movement reports are accepted but do nothing yet (filled in by US3). Adapt `/api/sim/report` in `backend/src/somfy_shutters/api/rest.py` and every test that calls `handle_report(address, level)`
- [X] T007 Run the full backend suite; every test of features 001–004 must pass against the updated simulator before continuing

**Checkpoint**: the new port exists, the simulator speaks it, nothing regressed.

---

## Phase 3: User Story 1 — Shutters move again (Priority: P1) 🎯 MVP

**Goal**: every command reaches a current bridge in the form it acts on.

**Independent Test**: feed the adapter each port call and assert the exact topic and payload of [contracts/mqtt.md](./contracts/mqtt.md) "Outbound"; drive every command source against the simulator.

### Tests for User Story 1

- [X] T008 [P] [US1] Create `backend/tests/unit/test_mqtt_adapter.py` with a fake client that records publishes: `send_level(a, 100)` → `somfy/<id>/command OPEN`, `send_level(a, 0)` → `command CLOSE`, `send_level(a, 37)` → `somfy/<id>/set_position 37`; **not retained, QoS 0**; `BridgeUnreachable` when the broker is down **or** no `online` availability has been seen; nothing queued

### Implementation for User Story 1

- [X] T009 [US1] Rewrite outbound in `backend/src/somfy_shutters/bridge/mqtt.py`: remove `CMD_TOPIC`/`STATE_TOPIC`; add `COMMAND_TOPIC = "somfy/{id}/command"`, `POSITION_REQUEST_TOPIC = "somfy/{id}/set_position"`; a pure `_publish_plan(address, verb, value) -> (topic, payload)` used by `send_level` and `send_stop`; delete `_to_wire`/`_from_wire`
- [X] T010 [US1] Identity spelling per research §5 in `backend/src/somfy_shutters/bridge/mqtt.py`: remember the last inbound spelling per address (lower-cased key), publish with it, fall back to the configured address; unit-test in `backend/tests/unit/test_mqtt_adapter.py` that `somfy/0X279621/position` makes the next command go to `somfy/0X279621/command`

**Checkpoint**: MVP — a current bridge receives every command.

---

## Phase 4: User Story 2 — Stop actually stops (Priority: P1)

**Goal**: stop is the bridge's explicit STOP everywhere.

**Independent Test**: stop during travel → the adapter publishes `command STOP` and never a `set_position`; the simulator's motor halts.

### Tests for User Story 2

- [X] T011 [P] [US2] In `backend/tests/unit/test_mqtt_adapter.py`: `send_stop(a)` → `somfy/<id>/command STOP`, and no `set_position` is published for any stop
- [X] T012 [P] [US2] In `backend/tests/integration/test_stop.py`: against the simulator, stop halfway through a close → the simulated motor stops advancing (`truth` unchanged over 2 s) and the tracker settles as an estimate; aborting a calibration run halts the same way

### Implementation for User Story 2

- [X] T013 [US2] `backend/src/somfy_shutters/commands.py`: the stop branch calls `bridge.send_stop(address)` instead of `send_level(address, tracker.halt_level(...))`, then `tracker.stop()` as before
- [X] T014 [US2] `backend/src/somfy_shutters/api/calibration_routes.py` `abort_run`: halt with `send_stop`; keep `tracker.halt_level()` only where the bridge counter must be recorded
- [X] T015 [US2] Implement `send_stop` in `backend/src/somfy_shutters/bridge/mqtt.py` via `_publish_plan`

**Checkpoint**: stop stops.

---

## Phase 5: User Story 3 — Reports are understood (Priority: P1)

**Goal**: position and movement reports reconcile as features 001 and 002 describe; the reconnect burst is old news.

**Independent Test**: the rows of [data-model.md](./data-model.md) "Tracker reaction to reports", each as a test.

### Tests for User Story 3

- [X] T016 [P] [US3] In `backend/tests/unit/test_mqtt_adapter.py`: `somfy/<id>/position` payload `48` → `Report(kind="position", percent=48)`; `somfy/<id>/state` `closing` → `Report(kind="movement", state="closing")`; the message's **retain flag becomes `retained`**; non-numeric, out-of-range and unknown state words are dropped and logged; wrong topic shapes ignored; `homeassistant/...` never subscribed
- [X] T017 [P] [US3] In `backend/tests/unit/test_reconciliation.py`: retained position with a known position → **no event**, bridge counter recorded; retained position with an unknown position → filled **as an estimate, never certain, even at 0/100**; retained movement → ignored; live `opening` while idle and not ours → external movement, `certain_at` refreshed, the next position report is a correction without the two-report window; live `opening` during our travel or the bridge run → ignored; live `stopped` ends external movement
- [X] T018 [P] [US3] In `backend/tests/integration/test_reconnect_burst.py`: restart the app against a simulator whose positions the app already knows → zero `correction` frames and zero external movements (SC-004)

### Implementation for User Story 3

- [X] T019 [US3] Inbound in `backend/src/somfy_shutters/bridge/mqtt.py`: subscribe `somfy/+/position`, `somfy/+/state`, `somfy/bridge/availability`; pure `_handle(topic, payload, retain)` producing `Report`s per the contract; case-insensitive id matching
- [X] T020 [US3] Tracker in `backend/src/somfy_shutters/tracker.py`: retained position = fill-only plus bridge counter; retained movement ignored; live `opening`/`closing` outside our movement and bridge-run window marks the shutter externally moving (transient, not persisted) and refreshes `certain_at`; position reports while externally moving are accepted as corrections; `open`/`closed`/`stopped` clear the flag; the two-report heuristic stays as fallback
- [X] T021 [US3] `POST /api/sim/movement {"shutter_id", "state"}` in `backend/src/somfy_shutters/api/rest.py` (simulator router only; **state one of opening, closing, open, closed, stopped**, 422 otherwise), with `backend/tests/contract/test_sim_movement.py`

**Checkpoint**: the bridge's reports mean what features 001 and 002 expect.

---

## Phase 6: User Story 4 — The bridge itself down (Priority: P2)

**Goal**: "bridge reachable" is broker **and** bridge availability.

**Independent Test**: availability `offline` with the broker up → unreachable within 5 s, commands refused; `online` → back.

### Tests for User Story 4

- [X] T022 [P] [US4] In `backend/tests/unit/test_mqtt_adapter.py`: broker up, no availability yet → not connected; `online` → connected and callbacks fire once; `offline` → not connected and callbacks fire; broker loss → not connected regardless of the last availability

### Implementation for User Story 4

- [X] T023 [US4] Availability in `backend/src/somfy_shutters/bridge/mqtt.py`: track the last payload on `somfy/bridge/availability`; `connected` and the connection callbacks use the combined value; reset to unknown on every broker reconnect until the retained payload arrives

**Checkpoint**: a crashed bridge is shown as one.

---

## Phase 7: User Story 5 — Nothing to reconfigure (Priority: P2)

**Goal**: old setups keep working without edits.

**Independent Test**: start with a configuration from before this feature (including `invert_level = true`) and a pre-existing database; everything works and one warning is logged.

### Tests for User Story 5

- [X] T024 [P] [US5] Replace `backend/tests/unit/test_level_translation.py` with tests that `invert_level = true` still validates, changes nothing about topics or payloads, and logs **one** warning at start; and that no source file outside `config.py` mentions `invert_level`

### Implementation for User Story 5

- [X] T025 [US5] `backend/src/somfy_shutters/config.py` and `backend/src/somfy_shutters/main.py`: keep `invert_level` in `BridgeConfig` with a docstring saying it is ignored since Pi-Somfy v3.1 declares 100 = open; log a warning once at startup when it is true
- [X] T026 [US5] Update `config/shutters.example.toml`: remove the direction explanation, note that the bridge defines 100 = open and that `invert_level` is ignored

**Checkpoint**: an update needs no edits.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T027 [P] Update `CLAUDE.md` non-negotiables and open hardware question 1 (answered by the bridge: 100 = open), and the MQTT line, to the current topics
- [X] T028 [P] Update `README.md`: architecture paragraph (topics), "What works today", the `stop` open question (now an explicit STOP; hardware verification pending), the bugs-found paragraph
- [X] T029 Run [quickstart.md](./quickstart.md) A1–A5 against the simulator in the browser
- [ ] T030 Run quickstart B1–B5 against a local Mosquitto impersonating Pi-Somfy with `mosquitto_pub`/`mosquitto_sub`, if Mosquitto can be installed on the development machine; otherwise record that it was skipped — **not run yet (2026-09-22): Mosquitto is not installed on the development machine; waiting for the owner's go-ahead to `brew install mosquitto`.**
- [X] T031 Full backend suite, ruff, frontend checks; every feature 001–004 scenario green (SC-006)
- [ ] T032 On the Pi with current Pi-Somfy: quickstart C — one shutter, commands, stop, a physical remote press with the receiver enabled (joins the pending hardware tasks)

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1** (amendment) before any code: the constitution must allow what the code does.
- **Phase 2** before any story: the port and the simulator.
- **US1** → **US2** share `_publish_plan` (T009 before T015).
- **US3** needs T019 (inbound) before T016 can pass; T020 is independent of the adapter.
- **US4** needs T019's subscription.
- **US5** is independent after Phase 2.
- **Polish** last; T032 needs hardware.

### Parallel opportunities

- Phase 1: T001 ∥ T002.
- US1: T008 ∥ T009 once the fake client exists.
- US2: T011 ∥ T012.
- US3: T016 ∥ T017 ∥ T018, and T020 ∥ T019.
- US5: T024 ∥ T025 ∥ T026.
- Polish: T027 ∥ T028.

---

## Implementation Strategy

### MVP first

1. Phase 1 + 2: governance and a simulator on the new port — suite green.
2. US1 + US2 together: commands and a stop that stops. **This alone makes the app usable against a current bridge.**

### Incremental delivery

3. US3 — reports, reconnect burst, physical remotes.
4. US4 — bridge availability.
5. US5 — migration polish.
6. Polish; T032 when a motor is paired.

### Task counts

| Phase | Tasks |
|---|---|
| Setup | 2 |
| Foundational | 5 |
| US1 | 3 |
| US2 | 5 |
| US3 | 6 |
| US4 | 2 |
| US5 | 3 |
| Polish | 6 |
| **Total** | **32** |
