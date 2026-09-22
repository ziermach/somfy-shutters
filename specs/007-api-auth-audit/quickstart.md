# Quickstart: validating API authentication and audit

Scenarios that prove the feature end to end, against the simulator **with
`[auth] mode = "required"`** — the simulator's default is open (research §10), which is
itself scenario H1. Each maps to acceptance scenarios in [spec.md](./spec.md). A–G are
also automated in `backend/tests/integration/test_auth_quickstart.py`.

## Setup

```bash
# config/shutters.toml: bridge.kind = "sim", and
#   [auth]
#   mode = "required"
cd backend && .venv/bin/uvicorn somfy_shutters.main:app --host 0.0.0.0
.venv/bin/somfy-shutters auth recover            # prints a pairing code
cd frontend && npm run dev
```

Open http://localhost:5173, enter the code and a name ("Laptop"). Shapes:
[contracts/rest.md](./contracts/rest.md), [websocket.md](./contracts/websocket.md),
[cli.md](./contracts/cli.md).

## A — The front door (User Story 1)

**A1. Nothing without a credential.** `curl -i localhost:8000/api/shutters` → `401`,
body names no shutter. `curl -X POST …/api/shutters/wohnzimmer/command -d '{"action":"open"}'`
→ `401`; `GET /api/sim/truth` shows the shutter did not move.

**A2. The feed closes first.** `websocat ws://localhost:8000/api/ws` → closed `4401`,
zero frames received.

**A3. Same refusal for every kind of bad.** No header, `Bearer sst_garbage`, a revoked
token, an expired token → four identical `401` bodies. `GET /api/audit` (as the owner)
shows four `auth_failed` entries with four different reasons.

**A4. Unchanged in use.** With the paired browser: overview, commands, groups, rules,
calibration all work as before; reload → still paired, no screen asks again.

**A5. Every route guarded.** `pytest tests/contract/test_every_route_is_guarded.py`.

## B — One per device (User Story 2)

**B1.** Issue "Handy A" and "Handy B" as tokens. Both command. Revoke A → A's next call
`401`, B unaffected. The list shows A as *widerrufen*, not gone.

**B2. Open feed cut.** Connect a socket with A's token, revoke A → the socket closes
`4401` within a second.

## C — Less than everything (User Story 3)

**C1.** Token with `watch` only → command `403 forbidden`, `detail.needs = "command"`;
the record has it as `refused_permission`.

**C2.** Token with `watch, command` → calibration run `403`, issuing a credential `403`,
commands work.

**C3.** A `manage, command` token asking to issue `calibrate` → `403 exceeds_own`.

## D — Pairing (User Story 4)

**D1.** Mint a code with `watch, command`; redeem on a second browser as "Anna" → Anna's
device works, has exactly those abilities, is listed as *gekoppelt*.

**D2.** Redeem the same code again → `401`; recorded `pairing_failed`.

**D3.** Mint, cancel, redeem → `401`. Mint, revoke the minting credential, redeem → `401`.

**D4.** Two parallel redemptions of one code → exactly one `201`.

**D5.** Eleven wrong codes from one address → the eleventh is `429`; ten wrong codes from
ten addresses while a code is outstanding → that code is cancelled.

## E — The record (User Story 5)

**E1.** Command wohnzimmer from "Laptop" and "Anna" → `GET /api/audit?shutter=wohnzimmer`
lists both, newest first, correct names, `accepted`.

**E2.** `POST /api/sim/report` a movement the app did not start → an entry with actor
`bridge`, action `movement_observed`.

**E3.** An automation fires (feature 003 quickstart A1) → entries with actor
`automation` and the rule's id.

**E4.** Revoke Anna → her past entries still read "Anna", marked *widerrufen*.

**E5. Retention.** Entries older than `audit_retention_days` are gone after the daily
purge (fake clock in the test).

## F — Recovery (User Story 6)

**F1.** Revoke every credential (the app demands `confirm_lockout`), reload → pairing
screen. On the Pi: `somfy-shutters auth recover` → code → pair → back in. Shutters,
calibration, rules, groups and history intact; the record has a `recovery` entry.

**F2.** There is no network route for recovery: `grep -r recover backend/src/somfy_shutters/api`
finds nothing, and A5 would fail if one appeared unguarded.

## G — Throttling (User Story 7)

**G1.** Ten bad tokens from one address in a minute → the eleventh request, even with a
*valid* token from that address, is `429` for 15 minutes; a valid token from another
address is unaffected.

**G2.** Thirty commands in two seconds from one token → about ten accepted, the rest `429`,
recorded `refused_throttle`; `GET /api/sim/truth` shows no more than the accepted ones
reached the bridge.

**G3. Clock jump.** Move the fake wall clock back six hours mid-lockout → the lockout still
ends on time (monotonic), the record stays in id order.

## H — The exemption (FR-029)

**H1.** `bridge.kind = "sim"`, no `[auth]` → app runs open, `GET /api/auth/me` says
`"mode": "open"`, all 541+ existing tests pass unchanged.

**H2.** `bridge.kind = "mqtt"` with `[auth] mode = "open"` → the process refuses to start
with a message naming the setting.

## I — Hardware (pending, with feature 001's bring-up)

**I1.** On the Pi with a paired motor: a command from a paired phone moves it and is
recorded; the same command without a credential does not reach Pi-Somfy (broker log).
