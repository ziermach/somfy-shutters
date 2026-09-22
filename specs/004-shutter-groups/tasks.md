---

description: "Task list for feature 004, shutter groups"
---

# Tasks: Shutter groups

**Input**: Design documents from `/specs/004-shutter-groups/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/rest.md](./contracts/rest.md), [contracts/websocket.md](./contracts/websocket.md)

**Tests**: Included where the feature can be wrong without anyone noticing — name uniqueness, pruning, partial group commands, target resolution (union, dedupe, `via`, deleted groups, legacy rows), conflicts through groups, the honest summary, and the API shapes. Not for UI wiring, which [quickstart.md](./quickstart.md) covers.

**Organization**: Grouped by user story. Features 001–003 are in place.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Separate file, no unfinished dependency — order does not matter
- **[Story]**: US1–US4 from [spec.md](./spec.md)

## Path Conventions

Existing layout: `backend/src/somfy_shutters/`, `backend/tests/`, `frontend/src/`. One new backend module `backend/src/somfy_shutters/groups.py`.

---

## Phase 1: Setup

- [X] T001 In the worktree, create `backend/.venv` (`uv venv --python 3.11 .venv && uv pip install -e ".[dev]"`) and run `npm install` in `frontend/`; confirm `pytest`, `ruff check`, `ruff format --check`, `npx svelte-check` and `npx vitest run` are green **before any change**, so later failures are this feature's

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the shared many-shutter command path, the group model and store, and groups arriving in every client.

**⚠️ No story work before this phase is done.**

- [X] T002 Add `apply_many(state, ids, action, target_percent) -> list[dict]` to `backend/src/somfy_shutters/commands.py`: calls `apply` for each id **in the given order**, sequentially, never concurrently; maps `MeasurementInProgress` → `{"id", "accepted": False, "error": "measurement_in_progress"}` and `BridgeUnreachable` → `"bridge_unreachable"`; accepted → `{"id", "accepted": True, "movement": <movement json or None>}`; keeps going after a failure; never retries (research §3)
- [X] T003 [P] Unit-test `apply_many` in `backend/tests/unit/test_apply_many.py` against the simulator: all accepted; one member measuring → others commanded, that one reported; bridge offline → all `bridge_unreachable` and nothing sent after it comes back; `stop` returns `movement: None`; commands go out in the order given
- [X] T004 Move `command_all` in `backend/src/somfy_shutters/api/rest.py` onto `apply_many` (ids in configuration order), keeping **200 all / 207 some / 503 none**; accepted results now carry `movement`; `position` without `target_percent` → **422 `target_required`**. The existing "Alle auf/zu" contract tests pass unmodified apart from the added `movement` field
- [X] T005 Move `AutomationEngine._command` in `backend/src/somfy_shutters/automation/engine.py` onto `apply_many`, mapping results to `Outcome` exactly as today (`measurement_in_progress` → skipped, `bridge_unreachable` → failed). Existing engine tests pass unmodified
- [X] T006 [P] Create `backend/src/somfy_shutters/groups.py` per [data-model.md](./data-model.md): `GroupDraft` (name **"1–40 chars after trimming"**, members **"≥ 1 on create and update; each configured; no duplicates"**) and `Group` (+ `id`); `name_key(name)` = **NFC + casefold of the trimmed name**; `GroupStore` on the app's SQLite file with tables `shutter_group` (**`name_key` UNIQUE**, `position`) and `shutter_group_member` (**PRIMARY KEY (group_id, shutter_id)**, `position`, **`ON DELETE CASCADE`**), `PRAGMA foreign_keys = ON`; methods `groups()` in order, `get`, `create` (appended last), `update` (replaces name and members in the given order), `delete`, `reorder(ids)` (rejects anything but a permutation), `prune(configured_ids) -> bool`
- [X] T007 [P] Unit-test the store in `backend/tests/unit/test_group_store.py`: round trip with member order; `"Südseite"` vs `" südseite "` collide; rename to own name with different case is allowed; delete cascades memberships only; `reorder` with a missing or extra id raises; `prune` removes unknown shutter ids, keeps the now-empty group, and reports whether anything changed; a pruned id re-added to the config is in no group
- [X] T008 Wire `GroupStore` in `backend/src/somfy_shutters/main.py`: construct on `store.path`, `prune(list(settings.shutters))` at startup, expose as `app.state.groups`, close on shutdown
- [X] T009 [P] Add `groups` to the snapshot in `backend/src/somfy_shutters/api/serialize.py` and a `groups` passthrough frame in `backend/src/somfy_shutters/api/ws.py` per [contracts/websocket.md](./contracts/websocket.md) (full list, never a delta)
- [X] T010 [P] Frontend plumbing: `Group` type, `snapshot.data.groups`, the `groups` frame in `frontend/src/lib/types.ts`; `frontend/src/lib/groups.svelte.ts` store with `groups = $state<Group[]>([])`, `set(list)`, `byId`; route snapshot and frame into it from `frontend/src/lib/shutters.svelte.ts`

**Checkpoint**: a group inserted through `GroupStore` reaches every open client in the snapshot; "Alle auf/zu" and automations behave exactly as before.

---

## Phase 3: User Story 1 — Name a set of shutters (Priority: P1) 🎯 MVP

**Goal**: The household creates, edits, orders and deletes overlapping groups in the app, and they survive restarts.

**Independent Test**: quickstart A1–A5.

### Tests for User Story 1

- [X] T011 [P] [US1] Contract tests in `backend/tests/contract/test_groups_rest.py` for `GET/POST/PUT/DELETE /api/groups` and `PUT /api/groups/order` per [contracts/rest.md](./contracts/rest.md): `201` appended last; **`409 name_taken` with `detail.group_id`**; **`422 invalid_group` with `detail.field`/`detail.problem`** for empty name, 41 chars, no members, duplicate member; **`422 unknown_shutter` with `detail.shutters`**; `404 unknown_group`; **`422 invalid_order`** for a non-permutation; each mutation publishes one `groups` frame

### Implementation for User Story 1

- [X] T012 [US1] Implement `backend/src/somfy_shutters/api/group_routes.py` (CRUD + order, not yet `command`) with the shared error shape and German messages ("Diesen Namen gibt es schon.", "Diese Gruppe gibt es nicht."); publish `{"type": "groups", "groups": [...]}` after every change; register in `backend/src/somfy_shutters/main.py`. `DELETE` calls a no-op hook for rule cleanup that US4 fills in (T029)
- [X] T013 [P] [US1] CRUD calls in `frontend/src/lib/groups.svelte.ts`: `create`, `update`, `remove`, `reorder` returning the server's message on failure, `null` on success; state itself only ever comes from the frame
- [X] T014 [P] [US1] `frontend/src/routes/GroupForm.svelte`: name field (**max 40**), member chips for every configured shutter in configuration order, the chosen members listed below with ↑/↓ to order them, save disabled until name and ≥ 1 member, server errors shown inline
- [X] T015 [US1] `frontend/src/routes/Groups.svelte`: list of groups with member count, ↑/↓ to reorder (calls `reorder`; on `invalid_order` re-fetch and say so), edit, delete with an inline confirm (no browser dialog), floating "+ Neue Gruppe"; navigation entry "Gruppen" in `frontend/src/App.svelte` and on `frontend/src/routes/Overview.svelte`

**Checkpoint**: quickstart A passes. Groups exist and sync, but the overview is still flat.

---

## Phase 4: User Story 2 — See the house by group (Priority: P1)

**Goal**: The overview is sorted under groups with an honest summary; a flat list remains one tap away.

**Independent Test**: quickstart B1–B5.

### Tests for User Story 2

- [ ] T016 [P] [US2] Vitest in `frontend/src/lib/groups.test.ts`: `summarize` — all open → "offen", all closed → "zu", mixed → "1 von 2 offen · 1 zu", any member moving counted as "fährt", unknown percent → "Position unbekannt" bucket, **never a percent in the text**, tone = **lowest member tone** (`sure` < `estimated` < `unsure`); counts in the **fixed order offen, zu, dazwischen, fährt, unbekannt**, empty buckets left out; `sections` — group order, member order, shared shutter in both, ungrouped last, empty group kept with no members; view preference — read/write through a storage that throws, unknown collapsed ids ignored

### Implementation for User Story 2

- [ ] T017 [US2] Implement `frontend/src/lib/groups.ts` (pure): `summarize(members, livePercent) -> {text, tone}` with the buckets of [data-model.md](./data-model.md) (moving / unknown / open 100 / closed 0 / between); `sections(groups, shutters) -> {group, members}[]` plus `ungrouped`; `loadView()`/`saveView()` on **`localStorage["somfy.view"]` = `{"mode": "grouped"|"flat", "collapsed": [...]}`**, every access in try/catch, default grouped when any group exists (research §9, §10)
- [ ] T018 [US2] `frontend/src/components/GroupSection.svelte`: header with name, summary text in the tone's colour from `ConfidenceBadge`, collapse chevron; the members' existing `ShutterCard`s below when expanded; "leer" and no cards for an empty group. Command buttons come in US3
- [ ] T019 [US2] Rework `frontend/src/routes/Overview.svelte`: *Gruppen / Liste* switch persisted via `saveView`; grouped mode renders `GroupSection` per section then "Ohne Gruppe"; flat mode and the no-groups case render exactly the current list, the latter with the hint "Rolladen zu Gruppen zusammenfassen" linking to Groups; "Alle auf/zu" stays at the top in both modes

**Checkpoint**: quickstart B passes. With US1 this is the MVP: the house is readable by room.

---

## Phase 5: User Story 3 — Move a whole group (Priority: P2)

**Goal**: One tap opens, closes, stops or positions every member; partial failures are named.

**Independent Test**: quickstart C1–C6.

### Tests for User Story 3

- [X] T020 [P] [US3] Contract tests for `POST /api/groups/{id}/command` in `backend/tests/contract/test_groups_rest.py`: **200 / 207 / 503** as for "Alle"; accepted results carry `movement`; **`409 empty_group`**; **`404 unknown_group`**; **`422 target_required`**; members commanded in configuration order, not member order
- [ ] T021 [P] [US3] Timing test in `backend/tests/integration/test_groups_quickstart.py` (C6): a 12-shutter simulated config, one group of all 12, the last member's `movement.started_at` within **5 s** of the request (FR-021)

### Implementation for User Story 3

- [X] T022 [US3] Add `POST /api/groups/{id}/command` to `backend/src/somfy_shutters/api/group_routes.py`: members sorted into configuration order, `commands.apply_many`, status 200/207/503 by accepted count
- [ ] T023 [P] [US3] `command(groupId, action, percent?)` in `frontend/src/lib/groups.svelte.ts`: patches each accepted `movement` into the shutters store immediately (as `shutters.command` does); returns `null`, or a German line naming the members not reached and why ("Küche: Messung läuft"), or "Kein Rolladen konnte erreicht werden." on 503
- [ ] T024 [US3] Buttons *auf / zu / stopp* and *Position…* in `frontend/src/components/GroupSection.svelte`: *Position…* opens the slider used in `frontend/src/routes/Detail.svelte` with the estimate note; disabled when the bridge is disconnected or no member would move (`canOpen`/`canClose`/`canStop`, skipping measuring members); the returned notice shown inline under the header until the next command

**Checkpoint**: quickstart C passes in the simulator.

---

## Phase 6: User Story 4 — Automate a group (Priority: P2)

**Goal**: Rules target groups; membership is read at firing time; each shutter is commanded once and its history says through which group.

**Independent Test**: quickstart D1–D7.

### Tests for User Story 4

- [ ] T025 [P] [US4] Unit-test resolution in `backend/tests/unit/test_target_resolution.py`: `"all"`; one group; two groups sharing a shutter → **one entry with both names in `via`**; group + direct shutter; unknown group id ignored; direct shutter no longer configured → `removed`; legacy stored list read as `{"shutters": list, "groups": []}`; result in configuration order; empty resolution → `no_targets`
- [ ] T026 [P] [US4] Extend `backend/tests/unit/test_conflicts.py`: draft targeting a group conflicts with a rule targeting one member directly; the conflict carries `via` = the group name; no conflict when the shared shutter left the group; **group change (FR-028)**: adding a member that two enabled rules command differently in the same minute yields one conflict naming both rules and the winner, a conflict that already existed before the change is not reported again, and removing a member yields none
- [ ] T027 [P] [US4] Extend `backend/tests/contract/test_automation_rest.py`: targets object round trip; plain list still accepted and returned as an object; **`422 unknown_group` with `detail.groups`**; empty object rejected; firing history outcomes carry `via`; deleting a group removes it from rules and publishes `rules_changed`

### Implementation for User Story 4

- [ ] T028 [US4] In `backend/src/somfy_shutters/automation/models.py`: `Targets` model `{shutters: list[str], groups: list[str]}` (**at least one entry total; no duplicates within a list**); `RuleDraft.targets: Literal["all"] | Targets` with a `before` validator turning a plain list into `Targets`; `Outcome.via: list[str] = []`. In `backend/src/somfy_shutters/automation/store.py`: read legacy targets and outcomes without `via`, write the object; add `drop_group(group_id) -> bool` that removes the id from every rule's targets
- [ ] T029 [US4] In `backend/src/somfy_shutters/automation/engine.py`: `targets(rule)` resolves per [data-model.md](./data-model.md) — union of direct shutters and current members of existing groups, **deduplicated, in configuration order**, `via` = names of listed groups containing the shutter — and `_command` passes `via` into each `Outcome`; the engine gets the `GroupStore` from `main.py`. Fill the delete hook of T012: `drop_group` → `reschedule()` → publish `rules_changed` if anything changed
- [ ] T030 [US4] In `backend/src/somfy_shutters/automation/conflicts.py` and `backend/src/somfy_shutters/api/automation_routes.py`: conflicts and `/preview` use the engine's resolution (so the warning and the firing agree); each conflict gains **`via`** (group name or `null`); `parse_draft` rejects unknown group ids with `422 unknown_group`; `rule_json` returns targets as an object
- [ ] T031 [P] [US4] Frontend types and wording: targets object in `frontend/src/lib/types.ts`; target text with group names ("Obergeschoss, Büro") and outcome text "über Obergeschoss" in `frontend/src/lib/automations.ts`, with cases in `frontend/src/lib/automations.test.ts`
- [ ] T032 [US4] `frontend/src/routes/RuleForm.svelte`: target chips in three rows — *Alle*, groups, shutters; *Alle* clears the others and vice versa; below them "Betrifft jetzt: …" resolved live from the groups store; conflict line names the group when `via` is set. `frontend/src/components/RuleCard.svelte` shows the target text and, for group targets, the shutters they currently mean ("Obergeschoss: Bad, Kind, Schlafzimmer"), resolved live from the groups store (US4 scenario 5); and `frontend/src/components/FiringHistory.svelte` shows `via`

- [ ] T033 [US4] Conflicts on group save (FR-028) per [contracts/rest.md](./contracts/rest.md): in `backend/src/somfy_shutters/api/group_routes.py`, `POST` and `PUT` compute, for each enabled rule targeting the group, `find_conflicts` with the old and the new membership and return **only pairs present with the new one**, deduplicated by rule pair and shutter, as `conflicts` (**`rule_id`, `rule_name`, `other_rule_id`, `other_rule_name`, `shutter_id`, `via`, `first_at`, `winner`**); the group is saved regardless. `frontend/src/routes/GroupForm.svelte` shows the returned conflicts as a warning after saving, worded like the rule form's conflict line

**Checkpoint**: quickstart D passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T034 [P] Scenario tests A–D (including D6, D7) of [quickstart.md](./quickstart.md) in `backend/tests/integration/test_groups_quickstart.py` with the simulator and a fake clock (A5 via two app instances with different configs on one database); plus **SC-005**: 30 simulated days of `run_due` with three rules whose group targets overlap, asserting at most one outcome per shutter per firing and one `level/cmd` per shutter per firing on the simulated bridge
- [ ] T035 Walk quickstart B2–B4 and C1–C4 by hand in two browser windows, one of them a private window (storage unavailable path). On a phone, time **SC-001** (a group of three created in < 30 s without help) and **SC-007** (with a 20-shutter sim config in 6 groups, a named shutter found in < 5 s); note the times in the commit message
- [ ] T036 [P] Update `README.md` ("What works today", test counts) and `CLAUDE.md` (groups live in the app database, not in `shutters.toml`)
- [ ] T037 On the Pi, once ≥ 3 motors are paired: quickstart E1 — a real group closes with every motor moving and no frame lost when Pi-Somfy gets the commands back-to-back; if frames are lost, measure the smallest safe gap and add it as `bridge.command_gap_ms` in config (research §4). **The constitution's hardware check for the consolidated command loop** (joins T042–T044 of feature 002 and T052 of feature 003)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (1)** → **Foundational (2)** → user stories.
- **US1 (3)** is needed by every other story: without groups there is nothing to show, command or target.
- **US2 (4)** needs US1. Together they are the MVP.
- **US3 (5)** needs US1's routes and US2's `GroupSection` for its buttons; the backend part (T020–T022) needs only US1.
- **US4 (6)** needs US1; independent of US2 and US3.
- **Polish (7)** after the stories it tests. T037 needs hardware.

### Within Phase 2

T002 first; T003 alongside it. T004 and T005 after T002. T006/T007 in parallel with T002–T005. T008 after T006; T009 after T008; T010 any time.

### Parallel opportunities

- Phase 2: T002/T003 ∥ T006/T007 ∥ T010.
- US1: T011, T013, T014 together while T012 is done.
- US2: T016 while T017 is written; T018 after T017.
- US3: T020, T021, T023 together.
- US4: T025–T027 together, T031 alongside T028–T030; T033 after T030.
- Polish: T034, T036 together.
- After US1, US3's backend and all of US4 can proceed in parallel with US2.

---

## Implementation Strategy

### MVP first

1. Phase 1 + 2: one command loop for everything; groups stored and pushed.
2. Phase 3 + 4: groups can be made and the overview is sorted by them. **Stop and validate with quickstart A and B.**

### Incremental delivery

3. US3 — one tap per floor.
4. US4 — rules that survive changes to the house.
5. Polish, then T037 when motors are paired.

### Task counts

| Phase | Tasks |
|---|---|
| Setup | 1 |
| Foundational | 9 |
| US1 | 5 |
| US2 | 4 |
| US3 | 5 |
| US4 | 9 |
| Polish | 4 |
| **Total** | **37** |
