# Implementation Plan: Travel-time calibration

**Branch**: `main` (single-developer repository) | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-travel-calibration/spec.md`

## Summary

Feature 001 animates from a travel time somebody typed in. This feature measures it.
A person stands at the window and presses twice per run; runs alternate direction so
each starts at the end stop the last one reached; the median of three per direction
becomes the stored value, and the live view uses it at once.

An optional check drives to the displayed midpoint and asks whether it looks halfway.
Each answer bends one shape parameter whose end points are fixed by construction, so
verification can improve the middle of the travel and can never distort 0 % or 100 %.

**One story cannot be built as specified.** User Story 2 asks for passive
recalibration from ordinary use. Nothing in this system observes when a travel ends —
the arrival time is computed from the travel time we are trying to measure, so the
measurement would be circular. [research.md §1](./research.md) works through every
candidate observer and proposes a one-tap replacement. That needs a spec amendment,
and this plan does not implement FR-018 to FR-020 until it happens.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5 with Svelte 5 (frontend) — unchanged from feature 001

**Primary Dependencies**: no new ones. Calibration is arithmetic and storage.

**Storage**: individual runs in the existing SQLite file; derived values in a new
`config/calibration.toml` the app owns; manual overrides stay in `shutters.toml`.

**Testing**: pytest against the simulator, whose per-window dead time and travel curve
the app cannot see — a correct implementation has to converge on them from presses
alone. Vitest for the frontend's run-state logic.

**Target Platform**: unchanged — Raspberry Pi, phone browsers on the home network.

**Project Type**: extends the existing web application; no new services.

**Performance Goals**: the elapsed-time display during a run must be smooth and the
recorded timestamps accurate to well under the human reaction time the measurement is
limited by anyway.

**Constraints**: measurement timing uses a monotonic clock, so a daylight-saving jump
mid-run cannot corrupt a value. Offline as always.

**Scale/Scope**: about 10 shutters, two directions each, a handful of runs per
direction retained.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1.*

| Principle | Verdict |
|---|---|
| **I. Pi-Somfy owns the radio** | **Pass.** Calibration issues ordinary level commands through the existing bridge. Nothing new touches radio. |
| **II. MQTT is the only integration point** | **Pass.** No new integration surface at all. |
| **III. Honest position state** | **Pass, and load-bearing.** A measurement improves the *estimate*, never the confidence: a calibrated shutter's position is still `estimated` between end stops, and a curve adjustment leaves `certain_at` untouched. The interface must not let "calibrated" read as "known". |
| **IV. Local-first operation** | **Pass.** Measurement is inherently local. |
| **V. Single-Pi simplicity** | **Pass.** No new dependency, no new process. Power monitoring would have solved User Story 2 outright and was rejected precisely here. |

Two constitution-adjacent points the design has to keep honest:

- **Measured values are configuration** (FR-030). Hence `calibration.toml` rather than
  values buried in a database ([research.md §2](./research.md)).
- **An uncalibrated shutter stays fully operable** (FR-027), on the stated default,
  marked as not calibrated. Feature 001 already behaves this way; this feature must not
  make calibration a precondition for anything.

**Post-Phase-1 re-check**: unchanged. The one risk found is recorded below.

## Project Structure

### Documentation (this feature)

```text
specs/002-travel-calibration/
├── plan.md              # This file
├── research.md          # Phase 0 — including why User Story 2 cannot be built
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── rest.md          # the calibration endpoints
└── tasks.md             # Phase 2, from /speckit-tasks
```

### Source Code (repository root)

New files, and the existing ones this feature touches:

```text
backend/src/somfy_shutters/
├── calibration.py       # NEW  runs, medians, plausibility, the curve parameter
├── calibration_store.py # NEW  run history in SQLite, calibration.toml read and write
├── config.py            #      gains the calibration layer and its precedence
├── tracker.py           #      travel_seconds() consults calibration; curve applied here
├── api/rest.py          #      the calibration endpoints
└── api/ws.py            #      a frame when a stored value changes

frontend/src/
├── lib/calibration.svelte.ts   # NEW  run state machine, elapsed time, presses
├── routes/Calibration.svelte   # NEW  the list of shutters and their state
├── routes/CalibrationRun.svelte# NEW  the guided run
└── components/RunTable.svelte  # NEW  runs with their verdicts
```

**Structure Decision**: calibration arithmetic goes in its own module rather than into
`tracker.py`. The tracker's job is where a shutter is; this feature's job is how long it
takes to get there. Keeping them apart means the median, the plausibility band and the
curve can be tested without constructing a tracker, and it keeps `tracker.py` — already
the most rule-dense file in the project — from growing a second responsibility.

`tracker.py` changes in exactly two places: `travel_seconds()` gains the precedence
chain, and the interpolation applies the curve parameter.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| A third configuration layer (`calibration.toml` beside `shutters.toml` and the default) | FR-030 wants measured values inspectable and hand-correctable, but the app rewrites them; one file cannot be both hand-authored and machine-written without losing comments | Writing measurements into `shutters.toml` destroys the human's file; keeping them only in SQLite fails "correctable by hand" and makes a config backup useless |
| A shape parameter on top of a linear travel model | FR-024 and FR-025 require the middle to be adjustable while the ends stay exact; a single `k` does that by construction rather than by clamping | A piecewise-linear midpoint needs a third press, which measurably makes things *worse* here; a fitted polynomial has more parameters than three taps can support |

## Risks

**The one that matters**: "calibrated" must not start reading as "known". A user who has
just measured a shutter three times in each direction will reasonably feel the number is
now trustworthy — and mid-travel it is still an estimate that drifts the moment anything
unobserved happens. The interface has to keep the confidence language of feature 001
exactly as loud after calibration as before it. Worth an explicit check during the
quickstart walkthrough rather than a requirement nobody re-reads.

**Second**: the simulator makes this feature pleasant to develop and could flatter it.
Its dead time and curve are stable and noise-free, while a real person at a real window
presses late and inconsistently. The tests should inject reaction-time jitter rather
than pressing at the exact right moment, or they will prove a precision the field will
not reproduce.
