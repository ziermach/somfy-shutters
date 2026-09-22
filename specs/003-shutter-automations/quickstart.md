# Quickstart: validating shutter automations

Scenarios that prove the feature end to end, against the simulator. Each maps to
acceptance scenarios in [spec.md](./spec.md). As with feature 002, the scenarios are
also automated in `backend/tests/integration/test_automation_quickstart.py`, driven
with a fake clock through `engine.run_due(now)` so none of them waits for real time —
except A1, which is worth seeing once with your own eyes.

## Setup

```bash
cd backend && .venv/bin/uvicorn somfy_shutters.main:app --host 0.0.0.0   # bridge.kind = "sim"
cd frontend && npm run dev
```

Open http://localhost:5173, go to **Automationen**, set a location (Berlin:
52.52 / 13.40) or press "Standort dieses Geräts verwenden".

API shapes: [contracts/rest.md](./contracts/rest.md),
[contracts/websocket.md](./contracts/websocket.md).

## A — Schedules (User Story 1)

**A1. It fires, with nobody watching.** Create "Test", *Uhrzeit* two minutes from now,
today's weekday, one shutter, *zu*. Close the browser. Reopen after three minutes.
→ The shutter is closed and certain; the rule's *Zuletzt* says `fired`, 1 of 1.

**A2. Wrong weekday.** Same rule with only tomorrow's weekday selected.
→ Nothing moves; *Nächste Ausführung* shows tomorrow's date.

**A3. Only its targets.** Two targets out of four. → Two move, two do not.

**A4. Position is an estimate.** Action *Position 30 %*. → The shutter settles at 30 %
with the *Schätzung* badge; the form showed the estimate note while editing.

## B — Sun (User Story 2)

**B1. Today's time is shown.** Sunset −30 min. → The form and the list show a concrete
*heute HH:MM*, equal to `location.sunset` − 30 min.

**B2. Bounds.** Sunrise, *nicht vor 06:30*, on a June date (fake clock).
→ Planned firing 06:30, not the ~04:45 sunrise.

**B3. No location.** Delete the location, try to create a sun rule. → 409 `no_location`,
the form explains it; existing time rules still show their next firing.

**B4. Offline.** Disconnect the network. → Sun times and next firings unchanged.

## C — Managing (User Story 3)

**C1. Next firing per rule**, as a date and time, or a reason (*aus*, *keine Tage*,
*kein Rolladen mehr*, *kein Standort*).

**C2. Toggle.** Switch a rule off at its firing minute. → It does not fire, and switched
on again it keeps every setting.

**C3. One refused shutter.** Start a calibration run on one target, let the rule fire.
→ Status `partial`; the history names that shutter with *Messung läuft*.

**C4. Conflict warning.** A second rule: same shutter, same minute, other action.
→ Warning on save, naming the winner. Saving is still allowed.

## D — Not today (User Story 4)

**D1. Pause until tomorrow.** → Overview banner *Automationen pausiert bis …*; a rule due
today records `paused`; tomorrow it fires without anyone resuming.

**D2. Skip next.** → Exactly one firing recorded `skipped`, the next one `fired`.

## E — The edges that matter

**E1. Restart within the grace.** Stop the backend one minute before a firing, start it
four minutes later. → Fired late, once, with planned and actual time in the history.

**E2. Restart after the grace.** Stop it for fifteen minutes across a firing.
→ Recorded `missed`, not carried out.

**E3. Clock unreliable.** `POST /api/sim/clock {"reliable": false}` before a firing,
`{"reliable": null}` twenty minutes after. → Overview banner *Uhrzeit unsicher —
Automationen angehalten*; the firing is recorded `held`.

**E4. Daylight saving.** Fake clock: a 02:30 rule on 2026-03-29 fires at 03:00; on
2026-10-25 it fires once.

**E5. No double firing.** Call `run_due(now)` twice for the same minute, and restart
the app in the second after a firing. → One record, one set of commands.

**E6. Bridge down.** `POST /api/sim/bridge/offline`, let a rule fire. → `failed`,
*Funkbrücke nicht erreichbar* per shutter; nothing moves when the bridge returns.

## Automated checks

```bash
cd backend && .venv/bin/python -m pytest tests/unit/test_planner.py tests/unit/test_sun.py \
  tests/integration/test_automation_engine.py tests/integration/test_automation_quickstart.py \
  tests/contract/test_automation_rest.py
cd frontend && npx vitest run && npx svelte-check --tsconfig ./tsconfig.json
```
