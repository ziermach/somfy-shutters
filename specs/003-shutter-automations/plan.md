# Implementation Plan: Shutter automations

**Branch**: `main` (single-developer repository, no feature branches) | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-shutter-automations/spec.md`

## Summary

Rules that open, close or position shutters at a clock time or at sunrise/sunset with
an offset and optional bounds, on chosen weekdays. A pure **planner** computes every
firing time — sun, bounds, daylight saving — and an **engine** carries firings out
through the same command function a button press uses, records each one per shutter
under a uniqueness key that makes double firing impossible, and holds everything while
the clock cannot be trusted. APScheduler is the single timer that wakes the engine;
`astral` computes the sun offline. A new automations screen, a rule form ported from
the mock, and an overview banner for pause and clock state make it visible.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript + Svelte 5 (frontend) — unchanged

**Primary Dependencies**: FastAPI, Pydantic v2 (existing); **new**: `APScheduler>=3.11,<4`,
`astral>=3.2,<4`. Frontend: none new.

**Storage**: the existing SQLite database; three new tables
([data-model.md](./data-model.md)).

**Testing**: pytest + pytest-asyncio; the planner is pure and table-tested, the engine is
driven through `run_due(now)` with a fake clock; vitest for frontend logic.

**Target Platform**: Raspberry Pi OS (Linux) alongside Pi-Somfy; macOS for development.

**Project Type**: web application — `backend/` and `frontend/`, as in features 001–002.

**Performance Goals**: a firing starts within 5 s of its planned time (SC-002); the
conflict check over 366 days answers within the form's preview round trip (< 200 ms for
tens of rules).

**Constraints**: offline (sun computed locally, no time service assumed beyond the local
network); no double firing across restarts and clock jumps; no firing on an unreliable
clock; every firing honours the measurement lock and never queues.

**Scale/Scope**: one household, ≤ 20 shutters, tens of rules, a few firings a day;
90 days of records is a few thousand rows.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. Pi-Somfy owns the radio** | Automations call the existing command function, which publishes `level/cmd` over MQTT. No new path to the radio. |
| **II. MQTT is the only integration boundary** | Unchanged; nothing here talks to Pi-Somfy except through that function. |
| **III. Honest position state** | Automated commands produce the same movements and estimates as manual ones; a `position` action is labelled as an estimate in the form (FR-023). Firing records say "commanded", never "arrived". |
| **IV. Local-first operation** | `astral` computes sun times on the Pi; location is typed in or taken from the phone; nothing is fetched. The clock guard handles the one offline hazard specific to the Pi — no RTC (research §5). |
| **V. Single-Pi simplicity** | Two small pure-Python libraries, both named in the constitution's stack table. No new service, no broker change, no background process beyond the existing app. |
| **Stack table** | APScheduler for time triggers and `astral` for sun, as fixed. APScheduler is used as a single timer rather than a job per rule; research §1 argues why. That is a use of the fixed choice, not a deviation from it. |
| **Command path verified on hardware** | The command function is *moved* from `api/rest.py` to `commands.py`, not changed. Existing contract tests prove equivalence here; hardware verification rides with the pending tasks T042–T044. |
| **Measured values in config** | No physical values introduced. Timezone and optional seed location are configuration. |

**Result**: pass, before and after design. No complexity to justify.

## Project Structure

### Documentation (this feature)

```text
specs/003-shutter-automations/
├── plan.md              # this file
├── research.md          # Phase 0 — decisions and why
├── data-model.md        # Phase 1 — tables, statuses, settings
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/
│   ├── rest.md          # /api/automations, /api/location, /api/sim/clock
│   └── websocket.md     # automations, automation_fired, rules_changed
└── tasks.md             # Phase 2 — /speckit-tasks
```

### Source Code

```text
backend/src/somfy_shutters/
├── commands.py              # NEW — apply(): the one command path, moved from api/rest.py
├── automation/
│   ├── __init__.py
│   ├── models.py            # Rule, Trigger, Action, Firing, statuses (Pydantic)
│   ├── planner.py           # next_firing(), firings_between(), today_at(); pure
│   ├── sun.py               # astral wrapper: sunrise/sunset for a date, or None
│   ├── clock.py             # ClockGuard: adjtimex + went-backwards check, sim override
│   ├── store.py             # rules, firings, settings tables; retention
│   ├── conflicts.py         # same-minute overlaps over 366 days
│   └── engine.py            # run_due(now), catch_up(), reschedule(); APScheduler job
├── api/
│   ├── automation_routes.py # NEW — contracts/rest.md
│   ├── rest.py              # uses commands.apply
│   └── ws.py                # new frames
├── config.py                # general.timezone, optional [location]
└── main.py                  # wires engine into lifespan and tick loop

backend/tests/
├── unit/test_planner.py         # days, DST, sun + offset + bounds, midnight crossing
├── unit/test_sun.py             # published-times fixture, ±2 min
├── unit/test_clock_guard.py
├── unit/test_conflicts.py
├── integration/test_automation_engine.py      # dedupe, grace, held, paused, skip, ordering
├── integration/test_automation_quickstart.py  # quickstart.md A–E, fake clock
└── contract/test_automation_rest.py

frontend/src/
├── lib/automations.svelte.ts    # store: rules, pause, clock, location; WS frames
├── lib/automations.ts           # wording: trigger/next/status text (testable)
├── lib/automations.test.ts
├── routes/Automations.svelte    # list, pause, location card
├── routes/RuleForm.svelte       # ported from mocks/rolladen-ui.html
├── components/RuleCard.svelte
├── components/FiringHistory.svelte
├── components/AutomationBanner.svelte   # paused / clock unreliable, on the overview
└── App.svelte, routes/Overview.svelte   # navigation + banner
```

**Structure Decision**: the existing web-application layout. Automation code gets its
own backend package because it has seven cooperating modules; everything else slots into
the places features 001 and 002 established.

## Design notes

- **Engine loop.** `reschedule()` computes the earliest next firing across enabled rules
  and sets the one APScheduler job to it (or removes it). The job calls `run_due(now)`,
  which collects every rule due at or before `now` and not yet recorded, sorts them by
  (planned time, created, id), and for each: insert the firing row (dedupe) → decide
  status (held / paused / skipped / no_sun) → otherwise apply commands to each resolved
  target in configuration order → update outcomes → publish `automation_fired`. Then
  `reschedule()` again.
- **Triggers of reschedule**: rule create/edit/delete/toggle/skip, pause change, location
  change, clock becoming reliable, and midnight (sun times move).
- **Catch-up** runs on startup and when the clock turns reliable (research §6).
- **Heartbeat** and **retention** run from the existing tick loop, once a minute and once
  a day.
- **UI** follows the mock: list of rule cards with a switch, a floating "+ Neue Regel",
  the form with segmented trigger, offset with −/+ sign, a collapsible "Zeitfenster" for
  sun bounds, day chips with shortcuts, shutter chips with "Alle", action auf/zu/Position
  with the estimate note, live preview line and conflict warning from `/preview`.

## Complexity Tracking

None. The constitution check passes without exceptions.

## Risks

- **Clock guard on real Pi OS.** `adjtimex` semantics are standard, but whether the Pi's
  NTP client (systemd-timesyncd) clears `STA_UNSYNC` promptly is to be confirmed on the
  device. Mitigation: the went-backwards check does not depend on it, and a held firing
  is visible, not silent.
- **Phone geolocation over plain HTTP.** Browsers only allow geolocation in a secure
  context; `http://<pi>:8000` is not one. Typing coordinates always works; the button is
  shown only where the API is available.
- **Firing into a manual action.** By the spec, rules fire even right after a person
  drove a shutter by hand. If that annoys in practice, it is a spec change, not a bug.
- **APScheduler and event loop ownership.** `AsyncIOScheduler` must be started inside the
  app's lifespan, on uvicorn's loop, and shut down with it; a scheduler started at import
  time would bind to the wrong loop.
