# Quickstart: validating shutter groups

Scenarios that prove the feature end to end, against the simulator. Each maps to
acceptance scenarios in [spec.md](./spec.md). A–D are also automated in
`backend/tests/integration/test_groups_quickstart.py` (REST + engine with a fake
clock); the overview scenarios (B) are checked by hand and by the pure tests in
`frontend/src/lib/groups.test.ts`.

## Setup

```bash
cd backend && .venv/bin/uvicorn somfy_shutters.main:app --host 0.0.0.0   # bridge.kind = "sim"
cd frontend && npm run dev
```

Use the four shutters of `config/shutters.example.toml` (wohnzimmer, kueche,
schlafzimmer, buero). Open http://localhost:5173 on two devices or two browser windows.

API shapes: [contracts/rest.md](./contracts/rest.md),
[contracts/websocket.md](./contracts/websocket.md).

## A — Groups (User Story 1)

**A1. Create and overlap.** Create *Erdgeschoss* = wohnzimmer, kueche; *Südseite* =
wohnzimmer, schlafzimmer. → Both exist; wohnzimmer is in both. The second window shows
both groups without reloading.

**A2. Name taken.** Create *  südseite *. → Refused: "Name ist schon vergeben".

**A3. Survives restart.** Restart the backend. → Both groups, members and order unchanged.

**A4. Delete leaves shutters alone.** Delete *Südseite*. → schlafzimmer moves on its own
button as before; wohnzimmer is still in *Erdgeschoss*.

**A5. Shutter leaves the config.** Remove `buero` from `shutters.toml` after putting it
in a group of its own; restart. → The group remains, says *leer*, offers no commands.
Put `buero` back, restart. → It appears under *Ohne Gruppe*, not in its old group.

## B — Overview (User Story 2)

**B1. Grouped view.** With A1's groups → *Erdgeschoss*, *Südseite*, then *Ohne Gruppe*
(buero). wohnzimmer appears twice.

**B2. Same animation twice.** Close wohnzimmer from its card under *Erdgeschoss*. → The
card under *Südseite* animates identically, same percent at every moment.

**B3. Honest summary.** kueche open, wohnzimmer closed. → *Erdgeschoss* reads
"1 von 2 offen · 1 zu", never "50 %". Make wohnzimmer's estimate stale
(`POST /api/sim/report` then wait past `stale_after_hours`, or restart with a restored
position) → the summary shows the reduced-confidence tone.

**B4. Flat list, remembered.** Switch to *Liste*, reload. → Still the flat list. In a
private window → grouped (default), and the page still works.

**B5. No groups.** Delete all groups. → The overview looks as before feature 004, with a
hint "Rollläden zu Gruppen zusammenfassen".

## C — Group commands (User Story 3)

**C1. Close a group.** *Erdgeschoss* → *zu*. → Both members animate from their own send
time; the response carries both movements.

**C2. Position.** *Erdgeschoss* → 30 %. → Both settle at 30 % with the *Schätzung* badge.

**C3. Stop.** While C1 runs, *Stopp* on the group. → Both halt.

**C4. One member being measured.** Start a calibration on kueche; *Erdgeschoss* → *auf*.
→ wohnzimmer opens; the app says "Küche: Messung läuft" (HTTP 207).

**C5. Bridge down.** `POST /api/sim/bridge/offline`; *Erdgeschoss* → *zu*. → Nothing
animates; "Kein Rolladen konnte erreicht werden" (HTTP 503). Bring it back online:
nothing moves by itself (no queue).

**C6. Timing.** With a 12-shutter sim config, command a group of 12.
→ The last member's `movement.started_at` is within 5 s of the tap (FR-021).

## D — Automations (User Story 4)

**D1. Group target.** Rule "Test", time now + 2 min, targets *Erdgeschoss*, *zu*.
→ Both members close; history shows each with *über Erdgeschoss*.

**D2. Membership follows.** Add buero to *Erdgeschoss*; fire the rule again.
→ buero closes too; the rule was not edited.

**D3. Once per shutter.** Targets *Erdgeschoss* + *Südseite* (sharing wohnzimmer).
→ wohnzimmer has one outcome, *über Erdgeschoss, Südseite*.

**D4. Group deleted.** Rule targeting only *Südseite*; delete *Südseite*. → The rule card
says it has no shutters left and will not fire.

**D5. Conflict through a group.** Rule A: 20:00, kueche, *auf*. Save rule B: 20:00,
*Erdgeschoss*, *zu*. → Warning names A, kueche via *Erdgeschoss*, and which wins.

**D6. Old rules untouched.** A rule saved by feature 003 with a list of shutters still
lists them and fires them unchanged.

## E — Hardware (pending, with feature 001's bring-up)

**E1.** A real group of ≥ 3 shutters closes with every motor moving; no frame dropped
when Pi-Somfy receives the commands back-to-back (research §4).
