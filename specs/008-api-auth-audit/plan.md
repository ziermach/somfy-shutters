# Implementation Plan: API authentication and audit

**Branch**: `main` (designed and built in a separate worktree, merged to `main` on 2026-09-22) | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-api-auth-audit/spec.md`

## Summary

A gate and a ledger. Every `/api/*` route declares one of five abilities — `watch`,
`command`, `configure`, `calibrate`, `manage` — through a FastAPI dependency, and a test
over `app.routes` fails the build for any route that declares none. Credentials are
random 256-bit tokens stored only as SHA-256, presented as a bearer header or as an
`HttpOnly`, `SameSite=Strict` cookie that the web app gets once, by redeeming a
six-character pairing code. Revocation closes the credential's open WebSockets at once.
`commands.apply` — already the single command path for buttons, groups and automations —
gains an `actor` and records each command after it is sent, so attribution cannot miss a
caller and never delays one. Throttling runs in memory on the monotonic clock. Recovery
and first run are one console command on the Pi that prints a pairing code; there is no
network route for it. The simulator runs open by default; open with a real bridge refuses
to start.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript + Svelte 5 (frontend) — unchanged

**Primary Dependencies**: none new. `hashlib`, `secrets`, `hmac` from the standard
library; FastAPI dependencies for the gate. Frontend: none new.

**Storage**: the existing SQLite database; three new tables
([data-model.md](./data-model.md)). Throttle state in memory.

**Testing**: pytest + pytest-asyncio — unit (tokens, codes, granting rule, throttles on a
fake monotonic clock, audit store), contract (every route guarded, refusal bodies,
credential and pairing endpoints, WebSocket close codes), integration (quickstart A–H);
vitest for the frontend's auth wording and the 4401 handling.

**Target Platform**: Raspberry Pi OS alongside Pi-Somfy; macOS for development.

**Project Type**: web application — `backend/` and `frontend/`, as in features 001–004.

**Performance Goals**: authentication adds under 1 ms per request on a Pi 3 (one SHA-256
and one indexed lookup); commands no slower to a person (SC-004) because the record is
written after sending.

**Constraints**: offline; no new transmitter path; credentials never readable from
storage; recovery impossible over the network; the simulator exemption impossible with a
real bridge; no per-request SD-card writes (last-used throttled, throttle state in memory).

**Scale/Scope**: one household, ≤ 10 credentials, a few hundred audit entries a day,
180 days retained — tens of thousands of rows.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. Pi-Somfy owns the radio** | Nothing here sends. The gate sits in front of `commands.apply`; refused requests never reach it. |
| **II. MQTT is the only integration boundary** | Unchanged. |
| **III. Honest position state** | Unchanged. The record says "commanded", never "arrived"; observed movements are marked as observed (FR-016). |
| **IV. Local-first operation** | Everything is local; no identity provider, no online check. Recovery needs only the Pi. |
| **V. Single-Pi simplicity** | No new dependency, no new service, no new process; three tables in the existing database; throttling in memory rather than a limiter library (research §8). One console script is added to the existing package. |
| **Stack table** | Unchanged. |
| **Command path verified on hardware** | `commands.apply` gains an argument and a record write after the send; the send itself is unchanged. Quickstart I1 verifies on hardware with the pending bring-up. |
| **Measured values in config** | None introduced. Throttle thresholds and retention are configuration, not measurements. |

**Result**: pass, before and after design. No complexity to justify.

## Project Structure

### Documentation (this feature)

```text
specs/008-api-auth-audit/
├── plan.md              # this file
├── research.md          # Phase 0 — decisions and why
├── data-model.md        # Phase 1 — tables, abilities, actions, config
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/
│   ├── rest.md          # refusals, route → ability, /api/auth/*, /api/audit
│   ├── websocket.md     # 4401 / 4429, revocation
│   └── cli.md           # somfy-shutters auth recover | list
└── tasks.md             # Phase 2 — /speckit-tasks
```

### Source Code

```text
backend/src/somfy_shutters/
├── auth/
│   ├── __init__.py
│   ├── tokens.py        # token and pairing-code generation, normalisation, hashing (pure)
│   ├── models.py        # Ability, Credential, PairingCode, Caller (Pydantic)
│   ├── store.py         # credential, pairing_code tables; granting rule; last-used throttle
│   ├── throttle.py      # failure windows and command buckets on an injected monotonic clock
│   ├── gate.py          # require(ability): resolve caller from bearer/cookie, Origin check,
│   │                    #   401/403/429, record refusals; WebSocket variant
│   └── audit.py         # audit_entry table: record() that never raises, query, purge
├── cli.py               # NEW — `somfy-shutters auth recover|list` (contracts/cli.md)
├── commands.py          # apply()/apply_many() take `actor`; record after send
├── api/
│   ├── auth_routes.py   # NEW — /api/auth/me, credentials, pairing, pair
│   ├── audit_routes.py  # NEW — GET /api/audit
│   ├── rest.py          # guards; health reduced for anonymous callers
│   ├── automation_routes.py, group_routes.py, calibration_routes.py   # guards + actor
│   └── ws.py            # authenticate the upgrade; hub tracks credential per socket
├── automation/engine.py # passes actor "automation:<rule id>"
├── config.py            # [auth] section; open-with-real-bridge is a startup error
└── main.py              # wiring: stores, gate, bus listener for observed movement,
                         #   expiry sweep, audit purge in the daily loop

backend/pyproject.toml   # [project.scripts] somfy-shutters = "somfy_shutters.cli:main"

backend/tests/
├── unit/test_tokens.py, test_auth_store.py, test_throttle.py, test_audit_store.py
├── contract/test_every_route_is_guarded.py
├── contract/test_auth_rest.py, test_audit_rest.py, test_ws_auth.py
├── integration/test_auth_quickstart.py        # quickstart A–H
└── unit/test_cli.py

frontend/src/
├── lib/auth.svelte.ts          # me, abilities; `can(ability)`; 401/4401 → pairing
├── lib/auth.ts                 # ability wording, credential states, code formatting (pure, tested)
├── lib/auth.test.ts
├── lib/shutters.svelte.ts      # 4401: stop reconnecting, show pairing
├── routes/Pair.svelte          # six-character code + device name
├── routes/Devices.svelte       # list, revoke (last-manager warning), issue token, mint code
├── routes/Record.svelte        # audit list, filters, paging
├── components/*                # hide what `can()` denies (arrival prompt needs calibrate)
└── App.svelte                  # pairing gate, navigation to Devices and Record

deploy/README.md                # upgrade note: run `somfy-shutters auth recover` once
```

**Structure Decision**: the existing layout. Authentication gets its own backend package
because it has six cooperating modules, as automations did in feature 003.

## Design notes

- **Caller resolution** (`gate.py`): bearer header, else `sst` cookie; hash; look up;
  active? → `Caller(id, name, abilities, via="bearer"|"cookie")`. In open mode a fixed
  `Caller(kind="simulator")` with all abilities. Failures increment the source's window
  *before* answering, and an already locked-out source is answered `429` without a lookup.
- **Ability check** after resolution; `command` routes additionally draw from the
  credential's bucket. Both refusals are recorded with the route's shutter id when the
  path has one.
- **Origin check** only for cookie-authenticated unsafe methods and the WebSocket upgrade
  (research §2).
- **`commands.apply(state, shutter_id, action, percent, actor=SYSTEM)`**: unchanged up to
  the send; afterwards `audit.record(...)` inside `try/except` that logs. `apply_many`
  passes the actor through. Routes build the actor from the caller; the engine passes
  `Actor("automation", rule.id, rule.name)`.
- **Observed movement**: a bus listener on `movement` events with `origin == "external"`.
- **WebSocket**: authenticate before `hub.join`; on failure accept and close `4401`. The
  hub keeps `socket → credential id`; `auth_store.revoke()` returns the id and the route
  calls `hub.close_for(credential_id)`. The expiry sweep runs in the existing tick loop.
- **Pairing redemption** is one `BEGIN IMMEDIATE` transaction: check redeemable, set
  `spent_at`, insert the credential, set `credential_id`. SQLite's write lock makes two
  racing redemptions serial; the second finds `spent_at` set.
- **Startup**: `config.py` rejects `auth.mode = "open"` unless `bridge.kind = "sim"`, with
  the message "auth.mode = \"open\" ist nur mit dem Simulator erlaubt."
- **Frontend**: `auth.svelte.ts` loads `/api/auth/me` after connecting; a `401` from any
  `fetch` or a `4401` close sets `paired = false`, which makes `App.svelte` show
  `Pair.svelte` instead of the app. Buttons the caller may not use are hidden, not
  disabled — a phone that may only watch should not look broken.

## Spec updates made with this plan

The spec predates features 003 and 004. It calls the remote-access work "feature 004";
that number is now shutter groups, and remote access has no number yet. The spec's text
is corrected to "a later remote-access feature" and its references to "features 001 and
002" to "features 001–004"; no requirement changed.

## Complexity Tracking

None. The constitution check passes without exceptions.

## Risks

- **iOS home-screen apps and cookies.** A PWA added to the iOS home screen has a cookie
  jar separate from Safari. Pairing inside the installed app works; pairing in Safari and
  then installing means pairing again once. Documented in the pairing screen's hint.
- **Cookie without `Secure` on plain HTTP.** Anyone who can sniff the home network can
  copy the cookie. Accepted by the spec's assumptions until remote access adds TLS; the
  flag switches on by itself over HTTPS.
- **Locking oneself out.** The last-manager warning (FR-013) and recovery (F1) cover it;
  recovery needs a shell on the Pi, which the owner has by construction.
- **Routes added by specs 005/006.** Covered by the every-route test: they fail until
  they declare an ability. Spec 005's add/remove maps to `configure`.
- **Clients from before this feature.** A cached PWA without the pairing screen gets
  `4401` and would reconnect forever. The service worker update from `eb3f6b0` brings the
  new app on the next load; the old one's backoff caps at 30 s, so the load is small.
