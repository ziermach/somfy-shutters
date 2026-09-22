---

description: "Task list for feature 003, shutter automations"
---

# Tasks: Shutter automations

**Input**: Design documents from `/specs/003-shutter-automations/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/rest.md](./contracts/rest.md), [contracts/websocket.md](./contracts/websocket.md)

**Tests**: Included where the feature can be wrong without anyone noticing — firing times (days, daylight saving, sun, bounds), the dedupe, the grace window, the held/paused/skipped decisions, and the API shapes. Not for UI wiring, which [quickstart.md](./quickstart.md) covers.

**Organization**: Grouped by user story. Features 001 and 002 are in place.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Separate file, no unfinished dependency — order does not matter
- **[Story]**: US1–US4 from [spec.md](./spec.md)

## Path Conventions

Existing layout: `backend/src/somfy_shutters/`, `backend/tests/`, `frontend/src/`. New backend package `backend/src/somfy_shutters/automation/`.

---

## Phase 1: Setup

- [X] T001 Add `APScheduler>=3.11,<4` and `astral>=3.2,<4` to `backend/pyproject.toml` dependencies and install into `backend/.venv`
- [X] T002 Extend `backend/src/somfy_shutters/config.py`: `general.timezone` (zoneinfo name, **default `Europe/Berlin`**, rejected if unknown) and an optional `[location]` with **latitude −90…90, longitude −180…180**; document both in `config/shutters.example.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the one command path, the rule model, time-trigger planning, storage, the clock guard and the engine — everything a single time rule needs to fire honestly.

**⚠️ No story work before this phase is done.**

- [X] T003 Move `_apply` and `MeasurementInProgress` from `backend/src/somfy_shutters/api/rest.py` into `backend/src/somfy_shutters/commands.py` as `apply(state, shutter_id, action, target_percent)`, **unchanged in behaviour**; `rest.py` calls it. The full existing test suite passing unmodified is the acceptance test (research §7)
- [X] T004 [P] Create `backend/src/somfy_shutters/automation/models.py` per [data-model.md](./data-model.md): `Rule` (name **1–60 chars**, `days` Monday-first 7 bools, `offset_minutes` **−360…360 and 0 for time triggers**, bounds only on sun triggers with **`not_before` < `not_after`**, `targets` `"all"` or a non-empty id list, `position` requires **percent 0–100**), `Trigger`, `Action`, `FiringStatus` (`fired`, `partial`, `failed`, `skipped`, `paused`, `held`, `missed`, `no_sun`) and per-shutter `Outcome` (`commanded` / `skipped: measurement_in_progress|removed` / `failed: bridge_unreachable`)
- [X] T005 [P] Implement time triggers in `backend/src/somfy_shutters/automation/planner.py`: `next_firing(rule, after, tz, location)` and `firings_between(rule, start, end, tz, location)`, base-date semantics, search from the day before `after` to eight days ahead, reasons `disabled` / `no_days` / `no_targets`; **spring-forward gap fires at the first valid minute, fall-back fires once (`fold=0`)** (research §2)
- [X] T006 [P] Unit-test time triggers in `backend/tests/unit/test_planner.py`: weekday selection, `after` exactly at a firing is not that firing, no days → `no_days`, **Europe/Berlin 2026-03-29 02:30 → 03:00 and 2026-10-25 02:30 → exactly one instant**
- [X] T007 [P] Implement `backend/src/somfy_shutters/automation/store.py`: tables `automation_rule`, `automation_firing` with **`UNIQUE(rule_id, planned_at)` and `ON DELETE CASCADE`**, and `app_setting` (key → JSON); CRUD for rules in FR-011 order (created, id); `record_firing()` that returns false when the row exists; `purge_before(instant)`
- [X] T008 [P] Unit-test the store in `backend/tests/unit/test_automation_store.py`: round-trip of every rule shape, a second `record_firing` for the same instant returns false, deleting a rule deletes its firings
- [X] T009 [P] Implement `backend/src/somfy_shutters/automation/clock.py`: `ClockGuard.check(now, last_heartbeat)` → reliable or `not_synchronised` / `went_backwards`; Linux `adjtimex(2)` via `ctypes` (`TIME_ERROR` = unreliable), reliable elsewhere; **went-backwards when `now` < heartbeat − 60 s**; an override for the simulator (research §5)
- [X] T010 [P] Unit-test the guard in `backend/tests/unit/test_clock_guard.py`: kernel verdict injected, backwards detection with and without slack, override wins over both
- [X] T011 Implement `backend/src/somfy_shutters/automation/engine.py`: `run_due(now)` — collect due, unrecorded firings across enabled rules, sort by **(planned time, created, id)**, for each insert the firing row first, decide `held` (clock) before anything else, otherwise resolve targets (`"all"` at firing time; missing ids → `skipped: removed`) and call `commands.apply` per shutter in configuration order, mapping `MeasurementInProgress` → skipped, `BridgeUnreachable` → failed, **never retrying**; update status and outcomes; publish `automation_fired`. Plus `reschedule()` setting a single APScheduler `DateTrigger` job to the earliest next firing
- [X] T012 Implement catch-up in `backend/src/somfy_shutters/automation/engine.py`: `catch_up(now)` over `(heartbeat, now]`, **capped at seven days back**; **within 10 minutes → carry out late, older → `missed` if the process started after it, else `held`**; heartbeat written every 60 s only while the clock is reliable (research §6)
- [X] T013 Integration-test the engine in `backend/tests/integration/test_automation_engine.py` with a fake clock and the simulator: one firing per planned instant however often `run_due` is called; same-minute rules run in FR-011 order and the last one decides the shutter; a shutter under measurement is skipped and the others commanded; bridge offline → `failed` and nothing sent later; catch-up at 4 min fires late once, at 15 min records `missed`; unreliable clock records `held`
- [X] T014 Wire the engine into `backend/src/somfy_shutters/main.py`: start `AsyncIOScheduler` **inside the lifespan** on uvicorn's loop and shut it down with it; run `catch_up` on start; from the tick loop: clock check every 30 s (catch-up + reschedule when it turns reliable), heartbeat every 60 s, reschedule at local midnight, **purge firings older than 90 days** once a day
- [X] T015 [P] Add frames to `backend/src/somfy_shutters/api/ws.py` per [contracts/websocket.md](./contracts/websocket.md): `automations` (its state also in the snapshot, see the contract), `automation_fired`, `rules_changed`

**Checkpoint**: a rule inserted into the database fires at its minute, once, through the ordinary command path, and is recorded.

---

## Phase 3: User Story 1 — Open and close on a schedule (Priority: P1) 🎯 MVP

**Goal**: A person creates a time rule in the app and the house carries it out.

**Independent Test**: Quickstart A1–A4 — a rule two minutes ahead fires with no browser open, only on its weekdays, only on its targets, and a position lands as an estimate.

### Tests for User Story 1

- [X] T016 [P] [US1] Contract test `backend/tests/contract/test_automation_rest.py`: `GET /api/automations` shape (`rules`, `pause`, `clock`, `location`), `POST` **201** with the stored rule, **422** for unknown shutter / empty targets / `position` without percent / offset on a time trigger, `DELETE` **204**, and a `rules_changed` frame after each change
- [X] T017 [P] [US1] Scenario test `backend/tests/integration/test_automation_quickstart.py` for A1–A4 with a fake clock: fired at the minute, not on another weekday, only its targets move, a `position` rule ends `estimated`

### Implementation for User Story 1

- [X] T018 [US1] Implement `backend/src/somfy_shutters/api/automation_routes.py`: `GET /api/automations`, `POST`, `DELETE /api/automations/{id}` per [contracts/rest.md](./contracts/rest.md); rules carry `next` from the planner; every change calls `engine.reschedule()` and publishes `rules_changed`; register the router in `main.py`
- [X] T019 [P] [US1] Create `frontend/src/lib/automations.ts`: German wording for triggers ("06:45", "Sonnenuntergang −30 Min"), actions ("auf", "zu", "30 %"), targets ("Alle Rolladen", names, "kein Rolladen mehr"), next firing ("heute 06:45", "morgen", weekday + date) and statuses — the phrases a person reads, kept testable
- [X] T020 [P] [US1] Unit-test the wording in `frontend/src/lib/automations.test.ts`
- [X] T021 [US1] Create `frontend/src/lib/automations.svelte.ts`: rules, pause, clock and location state loaded from `GET /api/automations`; create/delete; refetch on `rules_changed` and `automation_fired`; `automations` frames update pause and clock
- [X] T022 [US1] Create `frontend/src/routes/RuleForm.svelte` from `mocks/rolladen-ui.html`: name, trigger *Uhrzeit*, day chips with *Werktags / Wochenende / Alle*, shutter chips with *Alle*, action *auf / zu / Position* with the slider and **the estimate note for positions (FR-023)**, save and delete
- [X] T023 [US1] Create `frontend/src/components/RuleCard.svelte` and `frontend/src/routes/Automations.svelte`: list of rules with name, trigger, targets → action and next firing, and *+ Neue Regel*
- [X] T024 [US1] Add navigation in `frontend/src/App.svelte` and an *Automationen* entry on `frontend/src/routes/Overview.svelte`

**Checkpoint**: MVP — morning and evening schedules work end to end.

---

## Phase 4: User Story 2 — Follow the sun (Priority: P2)

**Goal**: Sunrise/sunset rules with offset and optional bounds, computed on the Pi.

**Independent Test**: Quickstart B1–B4 — today's time shown and honoured, bounds applied, no location explained, nothing fetched.

### Tests for User Story 2

- [ ] T025 [P] [US2] Collect published sunrise/sunset times for Berlin (52.52, 13.40) on 2026-03-20, 2026-06-21, 2026-09-23 and 2026-12-21 into `backend/tests/fixtures/sun_berlin.json`, noting the source; unit-test `backend/tests/unit/test_sun.py` **within ±2 minutes (FR-018)**
- [ ] T026 [P] [US2] Extend `backend/tests/unit/test_planner.py`: sunset −30 min, sunrise **"nicht vor 06:30" on 2026-06-21 → 06:30**, sunset "nicht nach 21:00" in June → 21:00, sunset +300 min lands on the next calendar day but belongs to the selected weekday, no location → `no_location`, a day without the event yields no firing
- [ ] T027 [P] [US2] Extend `backend/tests/contract/test_automation_rest.py`: `GET/PUT /api/location` with today's sunrise/sunset, **422** out of range, sun rule without location → **409 `no_location`**, `POST /api/automations/preview` returns `today`

### Implementation for User Story 2

- [ ] T028 [P] [US2] Implement `backend/src/somfy_shutters/automation/sun.py`: `sun_times(date, location, tz)` via `astral` with the standard −0.833° depression, `None` for an event that does not occur
- [ ] T029 [US2] Add sun triggers to `backend/src/somfy_shutters/automation/planner.py`: event + offset, then moved into `[not_before, not_after]` on the base date; `today_at(rule, now, …)` for the preview
- [ ] T030 [US2] Engine: record `no_sun` for a selected day whose event does not occur, in `backend/src/somfy_shutters/automation/engine.py`
- [ ] T031 [US2] Location in `backend/src/somfy_shutters/automation/store.py` (`app_setting.location`, seeded once from `[location]` in config) and `GET/PUT /api/location` plus `POST /api/automations/preview` (`next`, `today`) in `backend/src/somfy_shutters/api/automation_routes.py`; location change reschedules
- [ ] T032 [US2] Location card in `frontend/src/routes/Automations.svelte`: latitude/longitude inputs, today's sunrise and sunset, *Standort dieses Geräts verwenden* **shown only where `navigator.geolocation` exists and the context is secure**
- [ ] T033 [US2] Sun triggers in `frontend/src/routes/RuleForm.svelte`: *Sonnenaufgang / Sonnenuntergang*, offset with −/+ sign, collapsible *Zeitfenster* for *nicht vor / nicht nach*, the live *heute HH:MM* line from `/preview`, and the no-location explanation with a link to the location card

**Checkpoint**: sun rules follow the seasons; time rules unaffected.

---

## Phase 5: User Story 3 — See and manage what will happen (Priority: P2)

**Goal**: Next and last firing per rule, toggle, edit, history, and the conflict warning.

**Independent Test**: Quickstart C1–C4.

### Tests for User Story 3

- [ ] T034 [P] [US3] Unit-test `backend/tests/unit/test_conflicts.py`: two rules on one shutter in the same minute with different actions conflict and the winner follows FR-011; same action is no conflict; **two sun rules that meet only in June are found** over 366 days; a rule never conflicts with itself when editing
- [ ] T035 [P] [US3] Extend `backend/tests/contract/test_automation_rest.py`: `PUT` replace (**404** unknown), `PATCH {enabled}` keeps every other field, `GET /api/automations/{id}/firings` newest first with outcomes, `conflicts` in create/preview responses, `last` on each rule, rules listed in FR-011 order

### Implementation for User Story 3

- [ ] T036 [P] [US3] Implement `backend/src/somfy_shutters/automation/conflicts.py` over 366 days of planned firings (research §8)
- [ ] T037 [US3] Add `PUT`, `PATCH {enabled}`, `GET /api/automations/{id}/firings` and `conflicts` / `last` to `backend/src/somfy_shutters/api/automation_routes.py`
- [ ] T038 [US3] `frontend/src/components/RuleCard.svelte`: switch for enabled, *Zuletzt* line with status and "3 von 4", next firing or the reason it will not fire; open the form for editing
- [ ] T039 [US3] Create `frontend/src/components/FiringHistory.svelte`: per-rule list with planned and actual time, status, and each shutter's outcome with reason in German
- [ ] T040 [US3] Conflict warning in `frontend/src/routes/RuleForm.svelte` from `/preview`: names the other rule, the shutter, the first date and which rule wins; saving stays possible

**Checkpoint**: nothing a rule does is a surprise.

---

## Phase 6: User Story 4 — Not today (Priority: P3)

**Goal**: Pause everything until resumed or until a date; skip one rule's next firing.

**Independent Test**: Quickstart D1–D2.

### Tests for User Story 4

- [ ] T041 [P] [US4] Extend `backend/tests/integration/test_automation_engine.py`: paused → `paused` recorded, **resumes by itself after `until`**; skip next → exactly one `skipped`, the following firing `fired`; editing a rule so the skipped instant no longer exists clears the skip
- [ ] T042 [P] [US4] Extend `backend/tests/contract/test_automation_rest.py`: `PUT/DELETE /api/automations/pause` (**422** for a past time), `PATCH {skip_next}` (**409 `nothing_to_skip`**), and the `automations` frame on each change

### Implementation for User Story 4

- [ ] T043 [US4] Engine and store: pause in `app_setting`, `paused` and `skipped` decisions in `run_due`, an expired pause deleted on the next check, `skip_planned_at` cleared when used or when it is no longer a planned firing
- [ ] T044 [US4] `PUT/DELETE /api/automations/pause` and `PATCH {skip_next}` in `backend/src/somfy_shutters/api/automation_routes.py`, publishing `automations` on pause changes
- [ ] T045 [US4] Create `frontend/src/components/AutomationBanner.svelte` on `frontend/src/routes/Overview.svelte`: *Automationen pausiert bis …* with *Fortsetzen*, and *Uhrzeit unsicher — Automationen angehalten* (FR-026)
- [ ] T046 [US4] Pause controls in `frontend/src/routes/Automations.svelte` (*bis morgen*, *bis Datum*, *bis ich fortsetze*) and *Nächste Ausführung überspringen* on `frontend/src/components/RuleCard.svelte`

**Checkpoint**: holidays handled without deleting anything.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T047 [P] Scenario tests E1–E6 of [quickstart.md](./quickstart.md) in `backend/tests/integration/test_automation_quickstart.py`: restart inside and outside the grace, clock held and released, daylight-saving days, double `run_due` and restart right after a firing, bridge offline
- [ ] T048 [P] `POST /api/sim/clock` in `backend/src/somfy_shutters/api/rest.py` (simulator router only), with a contract test
- [ ] T049 [P] SC-003 check in `backend/tests/unit/test_planner.py`: for every day of 2026 the preview's `today` equals the instant `next_firing` returns for that day's sun rule
- [ ] T050 Walk quickstart A1 by hand once in the browser: a rule two minutes ahead with the browser closed
- [ ] T051 [P] Update `README.md` ("What works today", test counts) and `CLAUDE.md` (timezone and location settings)
- [ ] T052 On the Pi, once hardware is paired: confirm `adjtimex` reports unsynchronised after a cold boot without network and synchronised after NTP, and that one automated command drives a real shutter — **the constitution's hardware check for the moved command path** (joins T042–T044 of feature 002)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (1)** → **Foundational (2)** → user stories.
- **US1 (3)** is the MVP and the base for the UI of every later story.
- **US2 (4)** needs the planner from Phase 2 and the form from US1.
- **US3 (5)** needs US1's routes and cards; its conflict check covers sun rules once US2 is in, and is correct for time rules without it.
- **US4 (6)** needs the engine from Phase 2 and US1's screens.
- **Polish (7)** after the stories it tests. T052 needs hardware.

### Within Phase 2

T003 first (everything calls `commands.apply`). T004 before T005/T007/T011. T005, T007, T009 in parallel with their tests. T011 → T012 → T013 → T014.

### Parallel opportunities

- Phase 2: T004, T009/T010 alongside T005/T006 and T007/T008.
- US1: T016, T017, T019, T020 together; frontend T021–T024 while T018 is done.
- US2: T025–T028 together.
- US3: T034–T036 together.
- US4: T041, T042 together.
- Polish: T047–T049, T051 together.

---

## Implementation Strategy

### MVP first

1. Phase 1 + 2: a rule in the database fires, once, honestly.
2. Phase 3: rules can be made in the app. **Stop and validate with quickstart A.** This alone replaces the daily chore.

### Incremental delivery

3. US2 — sunset closing, the second most wanted routine.
4. US3 — visibility and conflicts.
5. US4 — pause and skip.
6. Polish, then T052 when a motor is paired.

### Task counts

| Phase | Tasks |
|---|---|
| Setup | 2 |
| Foundational | 13 |
| US1 | 9 |
| US2 | 9 |
| US3 | 7 |
| US4 | 6 |
| Polish | 6 |
| **Total** | **52** |
