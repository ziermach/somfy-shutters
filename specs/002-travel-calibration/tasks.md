---

description: "Task list for feature 002, travel-time calibration"
---

# Tasks: Travel-time calibration

**Input**: Design documents from `/specs/002-travel-calibration/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/rest.md](./contracts/rest.md)

**Tests**: Included for the arithmetic and the invariants — medians, plausibility, the curve's fixed end points, and convergence against the simulator's hidden truth. Not for UI wiring, which [quickstart.md](./quickstart.md) covers by hand.

**Organization**: Grouped by user story. Feature 001 is in place, so there is no setup phase worth the name.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Separate file, no unfinished dependency — order does not matter
- **[Story]**: US1, US2, US3 from [spec.md](./spec.md)

## Path Conventions

Existing layout: `backend/src/somfy_shutters/`, `backend/tests/`, `frontend/src/`.

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: The arithmetic and the storage every story needs. All of it is pure arithmetic
or plain storage, which is why the tests below are cheap.

**⚠️ No story work before this phase is done.**

- [X] T001 [P] Add `MeasurementRun`, `Calibration`, `ActiveRun` and `CheckAnswer` to `backend/src/somfy_shutters/models.py` per [data-model.md](./data-model.md), with `direction` one of `up`/`down`, `kind` one of `guided`/`confirmed`, and `rejected` holding a reason string or null
- [X] T002 [P] Implement `backend/src/somfy_shutters/calibration.py`: median over valid runs (**FR-013: median, never mean**), the plausibility band (**reject outside 0.5× to 2× the established value**), and the rejection reasons `dead_after_arrival`, `too_short`, `implausible`, `disturbed`, `abandoned`
- [X] T003 [P] Implement the curve in `backend/src/somfy_shutters/calibration.py`: `position(p) = p − k·sin(2πp)/2π` with `k` bounded to **±0.8**, and a step of **0.1 per check answer**
- [X] T004 [P] Unit-test the curve invariants in `backend/tests/unit/test_curve.py`: for every `k` in the band, `f(0) == 0` and `f(1) == 1` **exactly**, the curve is monotonic, and one step moves mid-travel by 1.6 points — these are what make FR-025 safe by construction rather than by clamping
- [X] T005 [P] Unit-test medians and rejection in `backend/tests/unit/test_calibration_math.py`: three runs yield the middle one, a late outlier does not move the value, each rejection reason fires on its own rule
- [X] T006 Implement `backend/src/somfy_shutters/calibration_store.py`: the `measurement_run` table in the existing SQLite file, and reading and writing `config/calibration.toml` in the shape from [data-model.md](./data-model.md)
- [X] T007 Extend `backend/src/somfy_shutters/config.py` with the precedence chain **manual in `shutters.toml` > measured in `calibration.toml` > `default_travel_seconds`**, exposing which layer a value came from
- [X] T008 [P] Unit-test precedence in `backend/tests/unit/test_calibration_precedence.py`: a manual value wins over a measurement and is never overwritten, a measurement wins over the default, and the reported `source` matches
- [X] T009 Make `travel_seconds()` in `backend/src/somfy_shutters/tracker.py` use the precedence chain, and apply `curve_k` in the movement interpolation — **the two places this feature touches feature 001**
- [X] T010 Ensure a calibrated shutter's position stays `estimated` between end stops in `backend/src/somfy_shutters/tracker.py`, and assert it in `backend/tests/unit/test_calibration_confidence.py` — **calibration improves the estimate, never the confidence** (constitution III)

**Checkpoint**: values flow through to the animation; nothing measures yet.

---

## Phase 2: User Story 1 — Measure a shutter by watching it (Priority: P1) 🎯 MVP

**Goal**: A person can measure a shutter in both directions and the animation then matches the window.

**Independent Test**: Calibrate the uncalibrated shutter with three runs per direction; the stored times land within about a second of the simulator's hidden truth and the live view finishes with it.

### Tests for User Story 1

- [X] T011 [P] [US1] Contract test `backend/tests/contract/test_calibration_rest.py`: shapes for `GET /api/calibration`, `POST /api/calibration/{id}/run`, `/mark`, `/home`, including **409 `not_at_end_stop` carrying `suggested_target`** and a rejected run returning **200 with a reason, not an error**
- [X] T012 [P] [US1] Integration test `backend/tests/integration/test_guided_run.py`: a full run recorded end to end, direction alternating on the next run, and the abandon timeout at twice the expected travel
- [X] T013 [P] [US1] Convergence test `backend/tests/integration/test_convergence.py`: simulate three runs per direction **with jittered reaction times, not perfect presses**, and assert the median lands within a second of the simulator's hidden travel time

### Implementation for User Story 1

- [X] T014 [US1] Implement the run state machine in `backend/src/somfy_shutters/calibration.py`: start requires an end stop (**FR-002**), phases `waiting_for_movement` then `timing`, timestamps taken **server-side on a monotonic clock** so a client clock and a daylight-saving jump cannot corrupt a measurement
- [X] T015 [US1] Mark a run `disturbed` in `backend/src/somfy_shutters/calibration.py` when a command or report for that shutter arrives from elsewhere (**FR-029**; undetectable for a physical remote with receive off — the plausibility band catches those, see [research.md §4](./research.md))
- [X] T016 [US1] Implement `POST /api/calibration/{id}/run`, `/mark`, `/home` and `DELETE …/run` in `backend/src/somfy_shutters/api/rest.py` per [contracts/rest.md](./contracts/rest.md); the homing drive must **not** be recorded as a measurement (**FR-003**)
- [X] T017 [US1] Implement `GET /api/calibration` and `DELETE /api/calibration/{id}` in `backend/src/somfy_shutters/api/rest.py`, returning per-direction values, run counts, `source` and `updated_at`
- [X] T018 [US1] Block other commands to a shutter under measurement in `backend/src/somfy_shutters/api/rest.py`, with a stated reason rather than a silent refusal (**FR-028**)
- [X] T019 [US1] Broadcast the `calibration` frame from `backend/src/somfy_shutters/api/ws.py` when a stored value changes, so other clients stop animating on the old timing (**FR-017**)
- [X] T020 [P] [US1] Implement the run state machine client-side in `frontend/src/lib/calibration.svelte.ts`: elapsed time, which press is expected next, and the two `mark` calls
- [X] T021 [P] [US1] Build `frontend/src/components/RunTable.svelte`: runs with dead time, total and verdict; **rejected runs struck through with their reason, not hidden** (**FR-012**)
- [X] T022 [US1] Build `frontend/src/routes/Calibration.svelte`: every shutter with its state — calibrated, partly measured, never measured, or manual — and when its value last changed (**FR-015**, **SC-006**)
- [X] T023 [US1] Build `frontend/src/routes/CalibrationRun.svelte`: the guided run, one large button that changes with the phase, abort, and the homing drive when the shutter is not at an end stop
- [X] T024 [US1] Reach the calibration screen from the detail view in `frontend/src/routes/Detail.svelte`, for the shutter already open

**Checkpoint**: run quickstart C1.1–C1.8.

---

## Phase 3: User Story 2 — Stay accurate with one tap (Priority: P2)

**Goal**: Values stay true over months without anybody opening the calibration screen.

**Independent Test**: Seed a wrong travel time, drive the shutter end to end a few times from the normal view answering each prompt, and watch the stored value converge.

> Built to the **amended** story. The original asked for measurement with no user
> involvement, which cannot be done — see [research.md §1](./research.md).

### Tests for User Story 2

- [X] T025 [P] [US2] Integration test `backend/tests/integration/test_confirmation.py`: a confirmation after an end-to-end travel is recorded as a measurement; an ignored prompt records nothing; a stopped, reversed or partial travel prompts nothing at all (**FR-019**)
- [X] T026 [P] [US2] Convergence test in `backend/tests/integration/test_confirmation.py`: a deliberately wrong stored value reaches within 5 % of the truth after at most ten confirmations (**SC-004**)

### Implementation for User Story 2

- [X] T027 [US2] Detect a confirmable travel in `backend/src/somfy_shutters/calibration.py`: initiated by us, end stop to end stop, uninterrupted — and **at most once per shutter per day** (**FR-018a**)
- [X] T028 [US2] Implement `POST /api/calibration/{id}/confirm` in `backend/src/somfy_shutters/api/rest.py`, recording the request's arrival as the observation and storing the run with `kind: "confirmed"` (**FR-020**)
- [X] T029 [US2] Build the prompt in `frontend/src/components/ArrivalPrompt.svelte`: one line, **Ja** and **Noch nicht**, dismissable, shown only while the app is in the foreground
- [X] T030 [US2] Wire the prompt into `frontend/src/App.svelte`: appears after a qualifying travel, "Noch nicht" leaves it up so the later tap is the measurement, ignoring it records nothing

**Checkpoint**: values maintain themselves at one tap each.

---

## Phase 4: User Story 3 — Check it without a stopwatch (Priority: P3)

**Goal**: The middle of the travel can be corrected without measuring again.

**Independent Test**: On a calibrated shutter, answer "zu hoch" a few times and watch mid-travel shift while the end stops stay exact.

### Tests for User Story 3

- [X] T031 [P] [US3] Integration test `backend/tests/integration/test_verification.py`: answers move `curve_k` by a bounded step, `at_limit` is reported at the bound, undo returns `curve_k` to 0 with the measurements untouched (**FR-026**)
- [X] T032 [P] [US3] Property test in `backend/tests/unit/test_curve.py`: after **any** sequence of answers, the displayed position at an end stop is exactly 0 or exactly 100 (**FR-025** — the invariant that makes this control safe)

### Implementation for User Story 3

- [X] T033 [US3] Implement check start, answer and undo in `backend/src/somfy_shutters/calibration.py`, storing answers so they can be reversed independently of the measurements
- [X] T034 [US3] Implement `POST /api/calibration/{id}/check`, `/check/answer` and `DELETE …/check` in `backend/src/somfy_shutters/api/rest.py` per [contracts/rest.md](./contracts/rest.md)
- [X] T035 [US3] Build the check flow in `frontend/src/routes/CalibrationRun.svelte`: drive to the displayed midpoint, ask **zu hoch / passt / zu tief**, and stop offering answers once `at_limit` is reported

**Checkpoint**: quickstart C3.1–C3.4.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T036 Walk quickstart **C4.1** with your eyes: after full calibration a shutter at 50 % must still read as an estimate with its age. **The most likely way this feature does damage is by letting "calibrated" read as "known"**
- [X] T037 Walk quickstart **C4.2**: a manual value in `shutters.toml` overrides a measurement, the interface says so, and the measurement is not discarded
- [X] T038 [P] Add `GET /api/sim/truth` in `backend/src/somfy_shutters/api/rest.py`, registered only for the simulator, so convergence can be checked by hand as the quickstart describes
- [X] T039 [P] Document calibration in `backend/README.md` and add `config/calibration.example.toml`; add `config/calibration.toml` to `.gitignore`
- [ ] T040 Run the whole of [quickstart.md](./quickstart.md) against the simulator and fix what it surfaces
- [X] T041 Update root `README.md` once the feature works: calibration moves from the "not yet" column to what works today

---

## Hardware bring-up (blocked on pairing)

- [ ] T042 [US1] Calibrate one real window and compare the measured times against a stopwatch, recording both in `config/calibration.toml` and the result in [quickstart.md](./quickstart.md) — the first check of whether reaction time behaves as assumed
- [ ] T043 [US1] Confirm the plausibility band in `backend/src/somfy_shutters/calibration.py` does not reject honest runs on a real motor, whose travel differs more between runs than the simulator's does; widen the band there if it does
- [ ] T044 [US3] Check whether verification converges for a real person judging "halfway" through a real window, which is harder than judging a rendered graphic; adjust the step in `backend/src/somfy_shutters/calibration.py` if three answers prove too coarse

---

## Dependencies & Execution Order

- **Phase 1** blocks everything. T001 and T002 before T006; T007 before T009.
- **US1 (Phase 2)** needs Phase 1. It is the MVP.
- **US2 (Phase 3)** needs Phase 1 and reuses US1's run recording, so it reads better after it, but its acceptance does not depend on the wizard having been used.
- **US3 (Phase 4)** needs Phase 1 only; it can be built before US2.
- **Polish** needs whichever stories ship.
- **Hardware** blocked on pairing, independent of all of it.

### Parallel Opportunities

Single developer, so `[P]` means "different file, any order":

- **Phase 1**: T001–T005 and T008 are separate files; T004 and T005 are pure arithmetic and can be written first as a specification of the maths
- **Phase 2**: T011–T013; then T020 and T021 in the frontend
- **Phase 3**: T025 and T026
- **Phase 4**: T031 and T032

---

## Implementation Strategy

**MVP: Phases 1 and 2.** Guided measurement is what makes every travel time real. Stop
there, calibrate the simulated house, and check the animation lands.

Then **Phase 4 before Phase 3** if the mid-travel error bothers you more than the upkeep
does — verification is smaller, and the stories do not depend on each other.

Two things to hold on to while building:

- The tests press with **jittered** reaction times. Pressing at the perfect instant
  proves a precision no person will reproduce, and hides why the median is there at all.
- Nothing in this feature may make a position more confident. A measured travel time
  makes the estimate better; it does not make the shutter's position known.

---

## Notes

- Commit per task or per coherent group
- Every checkpoint is a place to stop and validate
- `calibration.py` stays free of I/O, like `tracker.py` — that is what makes T004, T005
  and T032 cheap
- Constraints quoted in a task are quoted from [data-model.md](./data-model.md) and
  [research.md](./research.md) verbatim, so they are not re-decided while coding
