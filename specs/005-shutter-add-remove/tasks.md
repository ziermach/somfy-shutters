---

description: "Task list for feature 005, adding and removing shutters"
---

# Tasks: Adding and removing shutters

**Input**: Design documents from `/specs/005-shutter-add-remove/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/rest.md](./contracts/rest.md), [contracts/mqtt.md](./contracts/mqtt.md), [quickstart.md](./quickstart.md)

**Tests**: Included, as in features 001–006. Announcement parsing cannot be tried against a real bridge here, the roster mutates a list 36 call sites read, and removal cascades through four features' stores — each of those is asserted without a broker, and the whole suite must stay green after every phase.

**Organization**: Grouped by user story. US1 and US2 (both P1) share the roster and the confirm endpoint; US3 and US4 (P2) build on it independently of each other; US5 (P3) changes one step of US2's guide.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Separate file, no unfinished dependency — order does not matter
- **[Story]**: US1–US5 from [spec.md](./spec.md)

## Path Conventions

Existing layout: `backend/src/somfy_shutters/`, `backend/tests/{unit,contract,integration}/`, `frontend/src/{lib,routes,components}/`.

---

## Phase 1: Setup — governance first

- [X] T001 Amend `.specify/memory/constitution.md` principle II: add the bridge's discovery announcements `homeassistant/cover/+/config` to the **inbound** topic list; state that nothing is ever published under `homeassistant/#`; keep the rule and the rationale verbatim; add to the interface rule on RTS addresses that learning them from the bridge's announcements is how they are referenced, never invented; bump **1.2.0 → 1.3.0** (1.2.0 was taken by the SPI0 wiring amendment), set Last Amended to the day of the change, prepend a Sync Impact Report naming feature 005 and the dependent files (CLAUDE.md, README.md, `specs/006-pisomfy-mqtt-topics/contracts/mqtt.md`)
- [X] T002 [P] Add a "Superseded in part" note at the top of `specs/006-pisomfy-mqtt-topics/contracts/mqtt.md` pointing to [contracts/mqtt.md](./contracts/mqtt.md) for the discovery topic 006 excluded

---

## Phase 2: Foundational — announcements, a roster that can change, and an app that can start empty

**Purpose**: the adapter and simulator deliver announcements; the household's shutters can be built from config + table at start and changed at runtime. No UI yet.

**⚠️ No story work before this phase is done.**

### Tests for Phase 2

- [X] T003 [P] In `backend/tests/unit/test_mqtt_adapter.py`: `homeassistant/cover/pisomfy_0x279630/config` with `{"name":"Bad","command_topic":"somfy/0X279630/command","device":{"configuration_url":"http://pi-somfy.local/"}}` → `Report(kind="announcement", address="0x279630", name="Bad", web_url="http://pi-somfy.local/", retained=<flag>)`; the address comes from `command_topic`, **not** the topic segment; a payload that is not JSON, or whose `command_topic` is missing or not `somfy/<id>/command`, yields nothing; an **empty** payload yields an announcement with `name=None` (withdrawal) for the address last parsed from that topic, and nothing if that topic was never seen; the inbound id spelling is remembered as in feature 006; nothing is ever published under `homeassistant/`
- [X] T004 [P] Create `backend/tests/unit/test_roster_store.py`: `household_shutter` round trip; `id` matches `^[a-z0-9_-]+$` and never changes; `address` unique, stored lower-case; `name` "1–40 chars, trimmed, unique among household shutters"; `state` only `active` | `set_aside`; `created_at`/`updated_at` UTC
- [X] T005 [P] Create `backend/tests/unit/test_roster.py` (no broker, fake clock): announcements build `new` = announced − active − set aside; a configured address is never new; confirming appends to `settings.shutter` and `settings.by_address()` finds it; start builds `settings.shutter` from `shutters.toml` + active rows, and a row whose address is also in the file is ignored with a warning (file wins); slug from name transliterates umlauts (`Gästezimmer` → `gaestezimmer`) and suffixes on collision with config or table ids (`bad`, `bad-2`)

### Implementation for Phase 2

- [X] T006 Extend `Report` in `backend/src/somfy_shutters/bridge/base.py` with kind `"announcement"` and fields `name: str | None` (None = withdrawn) and `web_url: str | None`; document that an announcement says what the bridge knows, never that a motor responds
- [X] T007 Subscribe to `homeassistant/cover/+/config` and parse announcements per [contracts/mqtt.md](./contracts/mqtt.md) in `backend/src/somfy_shutters/bridge/mqtt.py`: add it to `SUBSCRIPTIONS`; a pure `_parse_announcement(topic, payload, retain)`; remember topic → address so an empty payload can be turned into a withdrawal; still publish nothing but `command`/`set_position` (makes T003 pass)
- [X] T008 Model the bridge's roster in `backend/src/somfy_shutters/bridge/sim.py` per research §8: a bridge-side list of `(address, name, enabled)` seeded from the configured shutters; on `start()` one **retained** announcement per enabled shutter; on `set_connected(True)` one **live** announcement per enabled shutter; `bridge_add(name) -> address` (next free address after the highest known, **not announced until a restart**, not commandable until then), `bridge_delete(address)` (disabled in the bridge, its retained announcement is replayed unchanged on the next `start()`), `bridge_restart()` (`set_connected(False)`, `set_connected(True)`)
- [X] T009 Relax `Settings.shutter` in `backend/src/somfy_shutters/config.py` from `Field(min_length=1)` to allow an empty list, keep the unique-id/unique-address validator, and add optional `bridge.web_url: str | None`; add a short comment that the list is now mutated at runtime by the roster
- [X] T010 [P] Create `backend/src/somfy_shutters/roster_store.py`: `household_shutter` table in the existing SQLite database exactly as in [data-model.md](./data-model.md) — `id` text PK "slug of the confirmed name, `^[a-z0-9_-]+$`, unique across config and table; never changes", `address` text unique "lower-case, as parsed from the announcement", `name` text "1–40 chars, trimmed, unique among household shutters", `state` text "`active` | `set_aside`", `created_at`/`updated_at` text UTC; methods `all()`, `get(id)`, `by_address(address)`, `insert`, `rename`, `set_state`, `delete` (makes T004 pass)
- [X] T011 Create `backend/src/somfy_shutters/roster.py` with `Roster` per research §3–§5 and [data-model.md](./data-model.md) "Roster state": `announced: dict[address, Announcement]`, `new()`, `set_aside()`, `active()` (each entry with `origin: "config" | "bridge"`), `handle(report)` for announcements, `slug(name)`, `unique_name(name)` ("Küche" → "Küche 2"), `build(settings)` at start; a change listener list so the API can push frames; **no** forgotten logic yet (US4) (makes T005 pass)
- [X] T012 Add `Tracker.add_shutter(shutter)` and `Tracker.remove_shutter(shutter_id)` in `backend/src/somfy_shutters/tracker.py`: add starts `unknown`; remove drops position, movement, bridge counter, bridge run and external-moving flag
- [X] T013 Wire the roster in `backend/src/somfy_shutters/main.py`: build `settings.shutter` from config + active rows before the tracker, store and simulator are created; route `kind == "announcement"` reports to the roster, all others to the tracker as before; keep the app starting with zero shutters (the overview simply shows none)
- [X] T014 Run the full backend suite; every feature 001–004 and 006 test must pass unchanged

**Checkpoint**: announcements arrive and are held as `new`; the household's shutters can come from config, table, or both.

---

## Phase 3: User Story 1 — Take over the shutters the bridge already knows (Priority: P1) 🎯 MVP

**Goal**: shutters the bridge announces show up as new, are confirmed with a name, and then behave like any other shutter.

**Independent Test**: start with one hand-configured shutter and a simulator announcing three; `GET /api/roster` lists three as new and the hand-configured one as active `origin: "config"`; confirm each → on the overview, drivable, "Laufzeit nicht gemessen"; restart the app → nothing duplicated, names kept.

### Tests for User Story 1

- [X] T015 [P] [US1] Create `backend/tests/contract/test_roster_rest.py`: `GET /api/roster` shape exactly as [contracts/rest.md](./contracts/rest.md) (`active`, `new`, `set_aside`, `bridge.announcements_seen`, `bridge.web_url`); `POST /api/roster/new/{address}` → 201 with the feature 001 shutter shape and the new `id`, 409 `name_taken` for a duplicate name, 404 `not_announced` for an address not currently new, 422 for a name outside 1–40 chars after trimming; `PATCH /api/shutters/{id}` renames, id unchanged, 409 `name_taken`, 409 `configured_by_hand` for an `origin: "config"` shutter
- [X] T016 [P] [US1] Create `backend/tests/integration/test_roster_takeover.py` (quickstart A1, spec US1 scenarios 1–3, SC-002): new shutters are absent from `GET /api/shutters`, from group membership choices and from a rule targeting all shutters until confirmed (FR-002); after confirming they are drivable, `calibrated: false`; a configured address announced by the bridge appears once, keeps its configured name, travel times, groups and rules (FR-003); restart the app and the simulator → no duplicate, no new prompt for known shutters, a renamed shutter keeps the person's name

### Implementation for User Story 1

- [X] T017 [US1] Implement `Roster.confirm(address, name)` and `Roster.rename(id, name)` in `backend/src/somfy_shutters/roster.py`: confirm validates the name, derives the slug, inserts an `active` row, appends a `ShutterConfig` without travel times to `settings.shutter`, calls `tracker.add_shutter` and (sim) places the simulated shutter, notifies listeners; rename refuses config shutters and never changes the id
- [X] T018 [US1] Create `backend/src/somfy_shutters/api/roster_routes.py` with `GET /api/roster` and `POST /api/roster/new/{address}` per [contracts/rest.md](./contracts/rest.md); `web_url` = `bridge.web_url` from config if set, else the latest announced `configuration_url`, else `null`; register the router in `backend/src/somfy_shutters/main.py`
- [X] T019 [US1] Add `PATCH /api/shutters/{id}` (rename) to `backend/src/somfy_shutters/api/rest.py`
- [X] T020 [US1] Add `origin` and `forgotten` (always `false` until US4) to each shutter in `backend/src/somfy_shutters/api/serialize.py`
- [X] T021 [US1] In `backend/src/somfy_shutters/api/ws.py`: a `broadcast_snapshot()` that sends a fresh `snapshot` to every connected client, and a `roster` frame `{ "type": "roster", "new": <count>, "forgotten": [<ids>] }`; subscribe both to roster changes (research §9)
- [X] T022 [P] [US1] Add `forgotten: boolean` and `origin: 'config' | 'bridge'` to `Shutter`, and the roster types (`Roster`, `NewShutter`, `SetAsideShutter`, `RosterFrame`) to `frontend/src/lib/types.ts`
- [X] T023 [P] [US1] Create `frontend/src/lib/roster.svelte.ts`: store holding `GET /api/roster`, re-fetched on every `roster` frame and after confirm/rename; `confirm(address, name)`, `rename(id, name)`; handle the `roster` frame in the existing WebSocket dispatch in `frontend/src/lib/shutters.svelte.ts`
- [X] T024 [US1] Create `frontend/src/routes/Shutters.svelte` ("Rolladen verwalten"): active list with origin ("von Hand eingetragen" / "aus der Funkbrücke"), a naming form per new shutter prefilled with a unique name, rename for bridge shutters; add the route and a navigation entry in `frontend/src/App.svelte`
- [X] T025 [US1] Show "Neuer Rolladen gefunden" with a link to the management screen on `frontend/src/routes/Overview.svelte` whenever the roster's `new` count is above zero (spec US2 scenario 5)

**Checkpoint**: MVP — a household set up without typing a single address (SC-006 for existing bridge shutters).

---

## Phase 4: User Story 2 — Add a new shutter, guided (Priority: P1)

**Goal**: a guide walks through the bridge, notices the new shutter by itself, names it and offers measurement.

**Independent Test**: quickstart A2 — open the guide, `POST /api/sim/bridge/shutters {"name":"Bad"}` (nothing appears), `POST /api/sim/bridge/restart` → within 5 s the guide shows "Neuer Rolladen gefunden: Bad"; name it, finish → on the overview and offered for measurement.

### Tests for User Story 2

- [ ] T026 [P] [US2] Create `backend/tests/contract/test_sim_bridge_rest.py`: `POST /api/sim/bridge/shutters {"name"}` → 201 with the new address and **no** announcement until restart; `DELETE /api/sim/bridge/shutters/{address}` → 204, retained announcement unchanged; `POST /api/sim/bridge/restart` → offline, online, live announcements; all three 404 when `bridge.kind` is not `sim`
- [ ] T027 [P] [US2] Create `backend/tests/integration/test_add_guided.py` (FR-008, SC-003): a `roster` frame with `new: 1` reaches a WebSocket client within 5 s of the restart; two shutters added before one restart yield two new entries, neither lost; the confirmed shutter accepts a command only after the restart (the simulator models the bridge refusing unannounced shutters)
- [ ] T028 [P] [US2] Create `frontend/src/lib/roster.test.ts`: the guide's steps each say what, where (App, Funkbrücke, Fernbedienung, Fenster) and how to tell it worked; the restart step is present and comes after "Program"; the timeout hints after 10 minutes name, in this order, bridge not restarted, PROG not held long enough, learning mode timed out, announcements switched off; the `announcements_seen: false` hint; the stale-announcement hint

### Implementation for User Story 2

- [ ] T029 [US2] Add the sim-only endpoints `POST /api/sim/bridge/shutters`, `DELETE /api/sim/bridge/shutters/{address}` and `POST /api/sim/bridge/restart` to `backend/src/somfy_shutters/api/rest.py`, next to the existing sim endpoints, calling T008's simulator methods
- [ ] T030 [P] [US2] Create `frontend/src/lib/roster.ts`: pure guide model — steps for the remote route (create in Pi-Somfy "Add shutter", hold PROG until the shutter jogs, press "Program", restart Pi-Somfy, wait), the waiting state, the 10-minute timeout hints (FR-010), and `uniqueName`; all German wording lives here (makes T028 pass)
- [ ] T031 [US2] Create `frontend/src/routes/AddShutter.svelte`: shows the steps from `lib/roster.ts`, a "Pi-Somfy öffnen" link (`target="_blank"`, only when `bridge.web_url` is known; otherwise text only), waits on the roster store and moves on by itself to "Neuer Rolladen gefunden: …" with a name field; after 10 minutes shows the hints with "weiter warten" / "abbrechen"; on finish links to calibration of the new shutter; entry "Rolladen hinzufügen" on `frontend/src/routes/Shutters.svelte` and the route in `frontend/src/App.svelte`

**Checkpoint**: a new window end to end without a text editor (SC-001 in the simulator).

---

## Phase 5: User Story 3 — Remove a shutter (Priority: P2)

**Goal**: removal names its consequences, cascades everywhere, sends nothing, and keeps a still-announced shutter aside and restorable.

**Independent Test**: quickstart A4 — a bridge shutter in a group, targeted by two rules, calibrated; `GET /api/shutters/{id}/removal` names group and rules; `DELETE` → gone from overview, group and both rules, a rule without targets says "kein Rolladen mehr", the simulator received nothing; it is listed under set aside and can be restored.

### Tests for User Story 3

- [ ] T032 [P] [US3] Add to `backend/tests/unit/test_automation_store.py`: `remove_shutter(id)` removes it from every rule's `targets.shutters`, leaves groups in targets alone, returns the ids of rules left with no targets
- [ ] T033 [P] [US3] Add to `backend/tests/contract/test_roster_rest.py`: `GET /api/shutters/{id}/removal` shape per [contracts/rest.md](./contracts/rest.md) incl. `left_without_target`; `removable: false` with `reason` `configured_by_hand` or `measurement_in_progress`; `DELETE /api/shutters/{id}` → 200 `{ "removed", "set_aside" }`, 409 for both reasons, 404 unknown; `POST /api/roster/set-aside/{address}/restore` → back in `new`, 404 unknown
- [ ] T034 [P] [US3] Create `backend/tests/integration/test_remove_shutter.py` (FR-012–FR-016, SC-004): the full cascade of [data-model.md](./data-model.md) "Removal cascade" — `settings.shutter`, tracker, `shutter_state` row, calibration values and runs, group membership (an emptied group stays), rule targets (a rule left empty reports `no_targets`), firing history kept, `household_shutter` set aside or deleted; the simulator's publish log is unchanged by the removal; a shutter removed while travelling is removed and no stop is sent; a still-announced removed shutter does not come back as new after a bridge restart; restore then confirm brings it back with a fresh id and no old calibration

### Implementation for User Story 3

- [ ] T035 [P] [US3] Add `AutomationStore.remove_shutter(shutter_id) -> list[str]` in `backend/src/somfy_shutters/automation/store.py`, mirroring feature 004's group removal (makes T032 pass)
- [ ] T036 [P] [US3] Add `Store.delete(shutter_id)` for the `shutter_state` row in `backend/src/somfy_shutters/store.py`
- [ ] T037 [US3] Implement `Roster.removal_preview(id)`, `Roster.remove(id)` and `Roster.restore(address)` in `backend/src/somfy_shutters/roster.py`: refuse `configured_by_hand` and `measurement_in_progress` (an active calibration run on that shutter); cascade in the order of the data model — `GroupStore.prune` with the remaining ids, `AutomationStore.remove_shutter`, `CalibrationService.clear`, `Store.delete`, `tracker.remove_shutter`, remove from `settings.shutter` — then set the row `set_aside` if still announced, else delete it; send nothing to the bridge; notify listeners
- [ ] T038 [US3] Add `GET /api/shutters/{id}/removal` and `DELETE /api/shutters/{id}` to `backend/src/somfy_shutters/api/rest.py` and `POST /api/roster/set-aside/{address}/restore` to `backend/src/somfy_shutters/api/roster_routes.py`
- [ ] T039 [US3] Make the rule serialisation in `backend/src/somfy_shutters/api/automation_routes.py` report `no_targets` for a rule whose targets are empty, and show "kein Rolladen mehr" for it in `frontend/src/components/RuleCard.svelte` (skip if feature 004 already does both — check first)
- [ ] T040 [US3] Create `frontend/src/components/RemoveShutter.svelte`: loads the preview, lists groups and rules by name and "Messwerte werden gelöscht", one confirm; afterwards, when `set_aside`, explains how to delete the shutter in Pi-Somfy and, optionally, how to make the motor forget it (FR-015); shows the refusal reason instead of the button when not removable; entry "Rolladen entfernen" in `frontend/src/routes/Detail.svelte`
- [ ] T041 [US3] Add the "Beiseitegelegt" section with "wieder aufnehmen" to `frontend/src/routes/Shutters.svelte`; hand-configured shutters show where to remove them (`config/shutters.toml`) instead of a remove button

**Checkpoint**: the list can shrink as well as grow.

---

## Phase 6: User Story 4 — The bridge forgets a shutter (Priority: P2)

**Goal**: a bridge shutter missing from the live announcements after a bridge restart is marked forgotten, refused commands, skipped by automations, and returns intact when announced again.

**Independent Test**: quickstart A5 — `DELETE /api/sim/bridge/shutters/<addr>`, `POST /api/sim/bridge/restart` → within 60 s the shutter reads "Funkbrücke kennt diesen Rolladen nicht mehr", buttons disabled, settings kept; a command via the API is 409 `forgotten`.

### Tests for User Story 4

- [ ] T042 [P] [US4] Add to `backend/tests/unit/test_roster.py` (fake clock): each bridge `online` opens a 30 s window; active `origin=bridge` shutters not announced **live** inside it are forgotten when it ends; retained announcements do not count; a later live announcement clears it; `origin=config` shutters are never forgotten; `offline` alone forgets nothing (FR-018); an app that starts while the bridge is already online forgets nothing until an `online` transition it witnesses after a live announcement burst
- [ ] T043 [P] [US4] Create `backend/tests/integration/test_bridge_forgets.py` (FR-017, SC-005, spec US4 scenarios 1–3): forgotten within 60 s of the restart; `POST /api/shutters/{id}/command` → 409 `forgotten` with the German message; a rule targeting it records `skipped` with reason `forgotten`; calibration, groups and rules kept; bridge re-adds the address and restarts → normal again; bridge merely unreachable → 503 as in feature 001, nothing forgotten

### Implementation for User Story 4

- [ ] T044 [US4] Track bridge availability transitions and the live window in `backend/src/somfy_shutters/roster.py`: `live_since_online`, `window_ends`, `forgotten: set[shutter_id]`, a scheduled check at window end (asyncio `call_later`, injectable clock for tests); feed it the availability changes the MQTT adapter and simulator already expose (feature 006) from `backend/src/somfy_shutters/main.py`; notify listeners on every change of the forgotten set (makes T042 pass)
- [ ] T045 [US4] Add `ShutterForgotten` to `backend/src/somfy_shutters/commands.py`, raised by `apply` before anything is sent; map it to **409 `forgotten`**, "Die Funkbrücke kennt diesen Rolladen nicht mehr." in `backend/src/somfy_shutters/api/rest.py` and `apply_many`'s error string
- [ ] T046 [US4] Record `skipped` with reason `forgotten` in `backend/src/somfy_shutters/automation/engine.py` `_command`, next to `measurement_in_progress`
- [ ] T047 [US4] Serialise `forgotten` from the roster in `backend/src/somfy_shutters/api/serialize.py` (replacing T020's constant)
- [ ] T048 [US4] Frontend: `frontend/src/components/ShutterCard.svelte` and `frontend/src/routes/Detail.svelte` show "Funkbrücke kennt diesen Rolladen nicht mehr", disable open/close/stop (extend `canOpen`/`canClose`/`canStop` in `frontend/src/lib/shutters.svelte.ts` and its test), offer "Rolladen entfernen"; list forgotten shutters in their own section on `frontend/src/routes/Shutters.svelte`; show reason `forgotten` in `frontend/src/components/FiringHistory.svelte`

**Checkpoint**: nothing the bridge no longer knows looks drivable.

---

## Phase 7: User Story 5 — Adding without a working remote (Priority: P3)

**Goal**: the guide offers the power-cycle route with the shared-circuit warning.

**Independent Test**: quickstart A6 — choose "keine Fernbedienung mehr": power-cycle steps with timing and the prominent warning appear before the programming step; the flow continues to detection as in US2.

- [ ] T049 [P] [US5] Add to `frontend/src/lib/roster.test.ts`: the power-cycle route replaces only the PROG step, gives the timing (power off at least 5 s, back on, then "Program" within about two minutes), and carries the warning that every motor on the same circuit enters learning mode and would learn the same sender
- [ ] T050 [US5] Add the route choice and the power-cycle steps to `frontend/src/lib/roster.ts`, and the choice plus a prominent warning box to `frontend/src/routes/AddShutter.svelte` (makes T049 pass)

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T051 [P] Update `CLAUDE.md`: shutters come from the bridge's announcements (hand configuration still possible), the discovery topic is inbound only, and open hardware question 5's addresses no longer need copying
- [ ] T052 [P] Update `README.md`: adding and removing shutters, the bridge-restart step, what "vergessen" and "beiseitegelegt" mean, and `config/shutters.toml` now optional for shutters
- [ ] T053 [P] Update `deploy/README.md`: `EnableDiscovery = true` in Pi-Somfy (its default) is required for the app to find shutters
- [ ] T054 Run [quickstart.md](./quickstart.md) A1–A6 against the simulator in the browser
- [ ] T055 Run quickstart B against a local Mosquitto impersonating Pi-Somfy with `mosquitto_pub` (announce, `web_url`, restart without one shutter → forgotten)
- [ ] T056 Full backend suite, ruff check and format, frontend vitest and svelte-check; every feature 001–004 and 006 scenario green
- [ ] T057 On the Pi with current Pi-Somfy: quickstart C — add, program, restart → found; delete, restart → forgotten (joins the pending hardware tasks)

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1** (amendment) before any code: the constitution must allow the discovery subscription.
- **Phase 2** before any story: announcements, roster store and service, empty-start config.
- **US1** before **US2**: the guide confirms through US1's endpoint and store.
- **US3** and **US4** each need US1 only; they touch `roster.py` in different methods, so run them one after the other, not in parallel.
- **US5** needs US2's guide.
- **Polish** last; T057 needs hardware.

### Within each story

Tests first and failing, then backend, then frontend.

### Parallel opportunities

- Phase 1: T001 ∥ T002.
- Phase 2: T003 ∥ T004 ∥ T005; T010 ∥ T006–T009.
- US1: T015 ∥ T016; T022 ∥ T023 while the backend endpoints are written.
- US2: T026 ∥ T027 ∥ T028; T030 ∥ T029.
- US3: T032 ∥ T033 ∥ T034; T035 ∥ T036.
- US4: T042 ∥ T043.
- Polish: T051 ∥ T052 ∥ T053.

```text
# US1, after Phase 2:
T015 test_roster_rest.py      ∥ T016 test_roster_takeover.py
T022 frontend types           ∥ T023 roster store          (while T017–T021 land)
```

---

## Implementation Strategy

### MVP first

1. Phase 1 + 2: governance, announcements, a roster that can change — suite green.
2. US1: take over what the bridge announces. **This alone removes hand-copied addresses.**

### Incremental delivery

3. US2 — the guide, with the bridge restart.
4. US3 — removal and set aside.
5. US4 — forgotten.
6. US5 — power-cycle route.
7. Polish; T057 when a Pi and a motor are available.

### Task counts

| Phase | Tasks |
|---|---|
| Setup | 2 |
| Foundational | 12 |
| US1 | 11 |
| US2 | 6 |
| US3 | 10 |
| US4 | 7 |
| US5 | 2 |
| Polish | 7 |
| **Total** | **57** |
