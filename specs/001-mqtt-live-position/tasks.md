---

description: "Task list for feature 001, live position and movement"
---

# Tasks: Live position and movement

**Input**: Design documents from `/specs/001-mqtt-live-position/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included where the plan named them — contract tests against `contracts/`, and unit tests for `tracker.py`, which holds the FR-017 rules and is pure enough to test without a bus, a socket or a real clock. Not blanket TDD: UI components and wiring are verified by running the app per [quickstart.md](./quickstart.md).

**Organization**: Grouped by user story. Each story is independently shippable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file, no dependency on an unfinished task — safe to do in any order
- **[Story]**: US1, US2, US3 from [spec.md](./spec.md)

## Path Conventions

Web app per [plan.md](./plan.md): `backend/src/somfy_shutters/`, `backend/tests/`, `frontend/src/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: An empty but runnable skeleton in both languages.

- [X] T001 Create the directory tree from plan.md under `backend/` and `frontend/`, with `__init__.py` files where needed
- [X] T002 Write `backend/pyproject.toml`: Python 3.11, dependencies `fastapi`, `uvicorn[standard]`, `aiomqtt>=2.5,<3`, `pydantic>=2`, dev extras `pytest`, `pytest-asyncio`, `httpx`, `ruff`
- [X] T003 [P] Scaffold the frontend in `frontend/` with Vite and Svelte 5 in TypeScript, dev-proxying `/api` to `localhost:8000`
- [X] T004 [P] Configure ruff in `backend/pyproject.toml` and Prettier plus ESLint in `frontend/`
- [X] T005 [P] Download the two fonts into `frontend/static/fonts/` and declare them with `@font-face` in `frontend/src/app.css` — **no external origin may appear anywhere in the frontend** (Constitution IV; the mock's Google Fonts link must not be carried over)
- [X] T006 [P] Write `config/shutters.example.toml` with the four shutters from the mock, `bridge.kind = "sim"`, `stale_after_hours = 12`, `default_travel_seconds = 20`; add `config/shutters.toml` to `.gitignore`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The spine every story stands on — configuration, entities, persistence, the bridge seam, and an app that starts.

**⚠️ No user story can begin before this phase is done.**

- [X] T007 [P] Implement `backend/src/somfy_shutters/config.py`: load TOML into Pydantic settings, validating `id` unique and matching `[a-z0-9_-]`, `address` unique and matching `0x[0-9a-f]{6}`, travel times when present **between 1 and 600 seconds**, and **at least one shutter configured**; fail startup loudly with the offending field named
- [X] T008 [P] Implement `backend/src/somfy_shutters/models.py`: `Shutter`, `PositionEstimate` (`percent` 0–100 **or null only when confidence is `unknown`**, `confidence` one of `certain`/`estimated`/`unknown`, `certain_at`, `source` one of `command`/`report`/`restored`), `Movement` (monotonic `started_at`/`expected_arrival`, `origin` `local`/`external`), `Command` — per [data-model.md](./data-model.md)
- [X] T009 Make a bare position unrepresentable: no model or serialiser may emit `percent` without `confidence` (Constitution III) — enforce in `models.py` and assert it in `backend/tests/unit/test_models.py`
- [X] T010 Implement `backend/src/somfy_shutters/store.py`: SQLite `shutter_state` table with columns `shutter_id`, `percent`, `confidence`, `certain_at`, `source`, `updated_at`, `was_moving`; write on settled changes and on movement start, never per frame
- [X] T011 [P] Implement `backend/src/somfy_shutters/events.py`: a small in-process pub/sub so `tracker.py` can emit without importing the API layer
- [X] T012 Define the port in `backend/src/somfy_shutters/bridge/base.py`: `send_level(address, percent)`, `reports()` async iterator, `connected` state, `on_connection_change` — no MQTT vocabulary in the signature
- [X] T013 Implement `backend/src/somfy_shutters/bridge/sim.py`: a simulated house with, per shutter, a **dead time**, a **non-linear travel curve**, **different speeds up and down**, and a configurable `loss_rate`; it must not expose those internals through the port
- [X] T014 Implement `backend/src/somfy_shutters/bridge/mqtt.py` with aiomqtt: publish `somfy/<address>/level/cmd`, subscribe `somfy/<address>/level/set_state`, and apply `invert_level` **in this file only** — per [contracts/mqtt.md](./contracts/mqtt.md)
- [X] T015 [P] Unit-test the level translation in `backend/tests/unit/test_level_translation.py`: both settings round-trip, and flipping `invert_level` is sufficient to reverse the whole system
- [X] T016 Wire `backend/src/somfy_shutters/main.py`: FastAPI with a `lifespan` that opens the configured bridge, starts the report task, and closes both on shutdown; mount the built frontend as static files
- [X] T017 [P] Configure logging in `backend/src/somfy_shutters/main.py`: structured, one line per command and per accepted correction, an unknown address logged once rather than per message

**Checkpoint**: `uvicorn` starts against the simulator, no endpoints yet.

---

## Phase 3: User Story 1 — Move a shutter and watch it move (Priority: P1) 🎯 MVP

**Goal**: Command every shutter and see a graphic that travels at the real speed.

**Independent Test**: With the simulator running, tap close and confirm the shutter closes and the graphic reaches closed at the same moment, within a second.

### Tests for User Story 1

- [X] T018 [P] [US1] Contract test `backend/tests/contract/test_rest_command.py`: request and response shapes for `POST /api/shutters/{id}/command`, including 404 unknown shutter, 422 malformed, and the `accepted`/`movement` fields — against [contracts/rest.md](./contracts/rest.md)
- [X] T019 [P] [US1] Contract test `backend/tests/contract/test_ws_frames.py`: `snapshot` on connect, then `movement` and `position` frame shapes with a monotonically increasing `seq` — against [contracts/websocket.md](./contracts/websocket.md)
- [X] T020 [P] [US1] Unit test `backend/tests/unit/test_tracker_movement.py`: interpolation between `started_at` and `expected_arrival`, stop freezes at the current position, reverse mid-travel starts from where it is, and a target equal to the current position is a no-op

### Implementation for User Story 1

- [X] T021 [US1] Implement movement in `backend/src/somfy_shutters/tracker.py`: accept a command, compute direction and `expected_arrival` from the configured travel time for that direction, hold the movement in memory, settle on arrival
- [X] T022 [US1] Implement the travel-time lookup in `backend/src/somfy_shutters/tracker.py`: use the configured value, fall back to `general.default_travel_seconds` when absent, and expose `calibrated` as both values present (**FR-015: an uncalibrated shutter still animates**)
- [X] T023 [US1] Implement `POST /api/shutters/{id}/command` in `backend/src/somfy_shutters/api/rest.py` for `open`, `close`, `stop`, `position`, returning the resulting movement
- [X] T024 [US1] Implement `POST /api/shutters/command` in `backend/src/somfy_shutters/api/rest.py`: every shutter commanded independently, **207 on mixed results**, 200 when all succeed
- [X] T025 [US1] Implement `GET /api/shutters` and `GET /api/health` in `backend/src/somfy_shutters/api/rest.py` — note health stays `ok` when the bridge is down, and reports it separately
- [X] T026 [US1] Implement the WebSocket in `backend/src/somfy_shutters/api/ws.py`: connection registry, **full snapshot as the first frame on every connect**, broadcast of `movement` and `position`, `seq` counter
- [X] T027 [P] [US1] Implement `frontend/src/lib/connection.ts`: WebSocket client, snapshot replaces all state, frames applied by type
- [X] T028 [P] [US1] Implement `frontend/src/lib/store.ts`: one Svelte store holding shutters, the single source for every view
- [X] T029 [US1] Implement `frontend/src/lib/animate.ts`: interpolate locally from `started_at` to `expected_arrival` at 60 fps, starting **on send without waiting for any frame** (FR-012), honouring `prefers-reduced-motion`
- [X] T030 [P] [US1] Build `frontend/src/components/WindowGraphic.svelte`: the SVG shutter, slat height bound to the interpolated position
- [X] T031 [US1] Build `frontend/src/components/ShutterCard.svelte` and `frontend/src/routes/overview.svelte`: the list, per-shutter auf/stop/zu, and "Alle auf"/"Alle zu"
- [X] T032 [US1] Build `frontend/src/routes/detail.svelte`: large graphic, position slider, the three buttons
- [X] T033 [US1] Add optimistic animation on command in `frontend/src/lib/store.ts`: start from the REST response, then accept the `movement` frame as authoritative timing without visibly jumping

**Checkpoint**: The house is controllable. Run quickstart scenarios S1.1–S1.6.

---

## Phase 4: User Story 2 — See how much the position can be trusted (Priority: P2)

**Goal**: Every position says whether it is certain, estimated or unknown, and how old that is.

**Independent Test**: Drive to an end stop — certain. Drive to 50 and wait — estimated, with an age. Let it go stale — de-emphasised, resync offered.

### Tests for User Story 2

- [X] T034 [P] [US2] Unit test `backend/tests/unit/test_confidence.py`: every transition from the state diagram in [data-model.md](./data-model.md), including `certain → estimated` on leaving an end stop and `estimated → certain` on reaching one
- [X] T035 [P] [US2] Unit test `backend/tests/unit/test_reconciliation.py`: **all six rows** of the precedence table in [research.md §5](./research.md) — report ignored while travelling, end-stop report becomes certain, ≤ 3 pp ignored, > 3 pp corrected, a report sequence treated as external movement, unknown address dropped
- [X] T036 [P] [US2] Integration test `backend/tests/integration/test_restart.py`: a shutter interrupted mid-travel comes back **unknown**; one settled at an end stop comes back certain (FR-010)

### Implementation for User Story 2

- [X] T037 [US2] Implement the confidence transitions in `backend/src/somfy_shutters/tracker.py`, including setting `certain_at` only when a position actually becomes certain
- [X] T038 [US2] Implement FR-017 reconciliation in `backend/src/somfy_shutters/tracker.py` per the precedence table — **accepting a report must not refresh `certain_at`** except at an end stop or on detected external movement
- [X] T039 [US2] Emit the `correction` frame with `ease_ms` from `backend/src/somfy_shutters/api/ws.py` when a report wins while idle
- [X] T040 [US2] Implement `was_moving` handling in `backend/src/somfy_shutters/store.py` and on startup in `backend/src/somfy_shutters/tracker.py`: set on movement start, cleared on settle, and **`was_moving = 1` on load means confidence becomes `unknown`**
- [X] T041 [US2] Compute the derived values in `backend/src/somfy_shutters/api/rest.py`: `stale` as `estimated` and older than `stale_after_hours`, `age_seconds`, `calibrated`, `eta_seconds` — computed on read, never stored
- [X] T042 [US2] Implement `POST /api/shutters/{id}/resync` in `backend/src/somfy_shutters/api/rest.py`: drive to the nearest end stop, return which one was chosen; when the position is unknown, choose open and say so
- [X] T043 [P] [US2] Build `frontend/src/components/ConfidenceBadge.svelte`: the teal/amber/grey dot with its wording, and the age
- [X] T044 [US2] Apply confidence across every view in `frontend/src/`: dim stale shutters, show the resync button, render `unknown` as "?" rather than a number (**FR-011: no bare number anywhere**)
- [X] T045 [US2] Handle the `correction` frame in `frontend/src/lib/animate.ts`: glide over `ease_ms`, never teleport

**Checkpoint**: Positions are honest. Run S2.1–S2.7.

---

## Phase 5: User Story 3 — Survive the parts that go missing (Priority: P3)

**Goal**: Dropped connections are stated plainly and recover without the user touching anything.

**Independent Test**: Cut the bridge, confirm the app says so and refuses to animate; restore it and confirm recovery is unprompted.

### Tests for User Story 3

- [X] T046 [P] [US3] Integration test `backend/tests/integration/test_bridge_down.py`: a command with the bridge unreachable returns **503 `bridge_unreachable`**, starts no movement, and queues nothing
- [X] T047 [P] [US3] Contract test `backend/tests/contract/test_ws_bridge_frame.py`: the `bridge` frame is sent on every transition and not periodically

### Implementation for User Story 3

- [X] T048 [US3] Implement connection tracking in `backend/src/somfy_shutters/bridge/mqtt.py` with reconnect and backoff, surfacing transitions through the port (FR-023)
- [X] T049 [US3] Return 503 with the shared error shape from `backend/src/somfy_shutters/api/rest.py` when the bridge is down, and broadcast the `bridge` frame from `backend/src/somfy_shutters/api/ws.py`
- [X] T050 [US3] Implement client reconnect in `frontend/src/lib/connection.ts`: backoff 1, 2, 4, 8 seconds capped at 30 with jitter, and a fresh snapshot on every reconnect
- [X] T051 [US3] Implement the disconnected state in `frontend/src/`: mark positions as not current, **stop animating**, keep them visible (FR-022)
- [X] T052 [P] [US3] Build the "Funkbrücke nicht erreichbar" banner in `frontend/src/components/BridgeBanner.svelte`, worded as what cannot be done rather than as a protocol error
- [X] T053 [P] [US3] Add the simulator-only endpoints `POST /api/sim/bridge/offline` and `POST /api/sim/report` in `backend/src/somfy_shutters/api/rest.py`, registered **only when `bridge.kind == "sim"`**, so quickstart S3.1 and the FR-017 table can be exercised by hand

**Checkpoint**: All three stories work independently. Run S3.1–S3.4.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T054 [P] Make the frontend installable as a PWA: manifest and a service worker that caches the shell, in `frontend/static/`
- [X] T055 Verify offline operation per quickstart: `grep -rEn "https?://(?!localhost)" frontend/dist/` returns nothing (Constitution IV)
- [X] T056 [P] Write `backend/README.md` with the run commands, and fill the "Build/test/run commands" gap in root `CLAUDE.md`
- [X] T057 [P] Add a systemd unit in `deploy/somfy-shutters.service` so it starts with the Pi
- [ ] T058 Run the full [quickstart.md](./quickstart.md) against the simulator, every scenario, and fix what it surfaces
- [ ] T059 Measure SC-001 (visible movement under 200 ms) and SC-003 (other clients within 1 s) on a phone over home Wi-Fi, not on the development machine; record the numbers in `specs/001-mqtt-live-position/quickstart.md`
- [ ] T060 Walk every screen under `frontend/src/routes/` for SC-004: no bare number presented as fact anywhere

---

## Hardware bring-up (blocked on pairing)

Not part of the software increment — these need at least one paired shutter and answer the open questions in `CLAUDE.md`.

- [ ] T061 [US1] Determine the direction of `level/cmd` (open question 1) and set `invert_level` in `config/shutters.toml`; confirm **no other change is needed** — the acceptance criterion for [contracts/mqtt.md](./contracts/mqtt.md)
- [ ] T062 [US1] Stopwatch travel times up and down for each window (open question 2), put them in `config/shutters.toml`, and re-run S1.1 to confirm the animation lands within a second
- [ ] T063 [US1] Confirm a level command to the current position actually halts the motor crisply; if not, switch `stop` to the button-press topic in `backend/src/somfy_shutters/bridge/mqtt.py` and **amend [contracts/mqtt.md](./contracts/mqtt.md)**
- [ ] T064 Check radio range to the furthest window with the antenna fitted (open question 3) and note the result in `CLAUDE.md` under the open questions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: needs Setup — **blocks all stories**
- **US1 (Phase 3)**: needs Foundational
- **US2 (Phase 4)**: needs Foundational; reads better after US1 exists but does not depend on its code
- **US3 (Phase 5)**: needs Foundational; independent of US1 and US2
- **Polish (Phase 6)**: needs the stories you intend to ship
- **Hardware**: blocked on pairing, independent of everything above

### Within Each Story

Tests → tracker logic → API → frontend. `tracker.py` before anything that calls it; `store.py` before `tracker.py` persists.

### Parallel Opportunities

Single developer, so `[P]` means "independent file, do these in whatever order suits" rather than "run simultaneously". The genuinely independent clusters:

- **Phase 1**: T003, T004, T005, T006 — different toolchains entirely
- **Phase 2**: T007, T008, T011 touch separate modules; T013 and T014 are two adapters behind one port
- **Phase 3**: the three tests T018–T020; then T027, T028, T030 in the frontend
- **Phase 4**: T034, T035, T036 — three separate test files
- **Phase 5**: T046, T047; T052, T053

---

## Implementation Strategy

### MVP: Phases 1–3

Setup, Foundational, US1. That is a working house control with an honest-speed animation, against the simulator. Stop there and validate with S1.1–S1.6 before going further.

### Incremental delivery

1. Phases 1+2 → the skeleton runs
2. Phase 3 → **MVP**, the house is controllable
3. Phase 4 → positions become trustworthy, which is the point of the project
4. Phase 5 → it survives daily use
5. Phase 6 → installable, documented, measured

### Build order note

Everything through Phase 6 runs against the simulator. Hardware tasks come last on purpose: waiting for pairing before writing software would stall the project, and the simulator exercises cases real hardware makes painful to reach — drift, a lost command, a restart mid-travel.

---

## Notes

- `[P]` = separate file, no unfinished dependency
- Commit per task or per coherent group
- Every checkpoint is a place to stop and validate
- `tracker.py` stays free of I/O — that is what makes T034 and T035 cheap to write
- Where a task quotes a constraint (ranges, regexes, enum values), it is quoted from [data-model.md](./data-model.md) verbatim so it is not re-decided during implementation
