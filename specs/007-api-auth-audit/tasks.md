---

description: "Task list for feature 007, API authentication and audit"
---

# Tasks: API authentication and audit

**Input**: Design documents from `/specs/007-api-auth-audit/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/rest.md](./contracts/rest.md), [contracts/websocket.md](./contracts/websocket.md), [contracts/cli.md](./contracts/cli.md)

**Tests**: Included, and for this feature they are the point: a door that nobody tried is not a door. Tests for every refusal path, the every-route guard, token and code handling, the granting rule, throttles on a fake monotonic clock, the record, and recovery. Not for UI wiring, which [quickstart.md](./quickstart.md) covers.

**Organization**: Grouped by user story. Features 001–004 are in place; specs 005 and 006 are not yet implemented.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Separate file, no unfinished dependency — order does not matter
- **[Story]**: US1–US7 from [spec.md](./spec.md)

## Path Conventions

Existing layout: `backend/src/somfy_shutters/`, `backend/tests/`, `frontend/src/`. New backend package `backend/src/somfy_shutters/auth/`.

---

## Phase 1: Setup

- [ ] T001 In the worktree, create `backend/.venv` (`uv venv --python 3.11 .venv && uv pip install -e ".[dev]"`) and run `npm install` in `frontend/`; confirm `pytest`, `ruff check`, `ruff format --check`, `npx svelte-check` and `npx vitest run` are green **before any change**
- [ ] T002 Add the `[auth]` section to `backend/src/somfy_shutters/config.py` per [data-model.md](./data-model.md): `mode` **`"required" | "open"`, default `"open"` when `bridge.kind = "sim"` and `"required"` otherwise**; `failed_attempts` **10**, `failed_window_minutes` **5**, `lockout_minutes` **15**, `command_burst` **10**, `command_per_second` **1.0**, `pairing_minutes` **5**, `audit_retention_days` **180**, optional `trusted_proxy`; **`mode = "open"` with any bridge but `"sim"` raises at load with "auth.mode = \"open\" ist nur mit dem Simulator erlaubt."** Document in `config/shutters.example.toml`; unit-test in `backend/tests/unit/test_auth_config.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: tokens and codes, the credential and pairing tables, and a record that never gets in a command's way.

**⚠️ No story work before this phase is done.**

- [ ] T003 [P] Create `backend/src/somfy_shutters/auth/tokens.py` (pure): `new_token()` → **`"sst_"` + 52 Crockford-base32 characters from 32 random bytes**; `new_code()` → **6 characters from `0123456789ABCDEFGHJKMNPQRSTVWXYZ`**; `format_code()` → `XXX-XXX`; `normalise_code()` upper-cases and drops `-` and spaces, returns None if not 6 alphabet characters; `digest(value)` → hex SHA-256 (research §1, §7)
- [ ] T004 [P] Unit-test tokens in `backend/tests/unit/test_tokens.py`: prefix and length, alphabet, no `I L O U`, normalisation of `k7q-9xm` and ` K7Q9XM `, rejection of 5/7 characters and foreign letters, digest stability, 1 000 tokens all distinct
- [ ] T005 [P] Create `backend/src/somfy_shutters/auth/models.py`: `Ability` (**`watch`, `command`, `configure`, `calibrate`, `manage`**), `Credential` (name **1–40 characters after trimming**, abilities **non-empty subset, `watch` always added**, origin **`issued | paired | recovery`**, `state` **`active | revoked | expired`**), `PairingCode`, `Actor` (kind **`credential | automation | bridge | recovery | simulator | anonymous`**, id, name), `Caller` (the resolved request identity; `SIMULATOR` with all abilities)
- [ ] T006 Create `backend/src/somfy_shutters/auth/store.py` on the app's SQLite file with tables `credential` and `pairing_code` exactly as in [data-model.md](./data-model.md) (**`secret_hash UNIQUE`, `code_hash UNIQUE`**): `issue(name, abilities, origin, created_by, expires_at) -> (Credential, token)`, `resolve(token) -> Credential | reason` (reason **`unknown | expired | revoked | malformed`**), `revoke(id, by) -> bool`, `list()`, `touch(id)` (**writes `last_used_at` at most once a minute per credential**, research §12), `mint(abilities, minted_by, minutes)`, `redeem(code, name) -> Credential | reason` in **one `BEGIN IMMEDIATE` transaction** (unspent, uncancelled, unexpired, minter active → set `spent_at`, insert credential, set `credential_id`), `cancel(id)`, `cancel_minted_by(credential_id)`
- [ ] T007 [P] Unit-test the store in `backend/tests/unit/test_auth_store.py`: the token is never stored (no column contains it), resolve of each reason, revoke is terminal, expiry, `touch` writes once a minute on a fake clock, redeem spends on the first attempt even when it fails later, a spent/cancelled/expired code and one whose minter was revoked are refused, **two concurrent `redeem` calls from two threads produce exactly one credential**
- [ ] T008 [P] Create `backend/src/somfy_shutters/auth/audit.py`: table `audit_entry` and its three indexes per [data-model.md](./data-model.md); `record(actor, action, outcome, shutter_id=None, target=None, detail=None, clock_ok=True)` that **catches every exception and logs it at ERROR, never raising** (FR-020); `query(shutter=None, actor=None, before=None, limit=50)` newest first by id, **limit max 200**; `purge(older_than)`
- [ ] T009 [P] Unit-test the record in `backend/tests/unit/test_audit_store.py`: order by id survives wall times going backwards, filters, paging with `before`, purge, **`record` on a closed connection logs and returns** instead of raising, an entry keeps its `actor_name` after the credential is renamed or revoked
- [ ] T010 Wire `AuthStore` and `AuditLog` in `backend/src/somfy_shutters/main.py` on `store.path`, close them on shutdown, expose as `app.state.auth` and `app.state.audit`

**Checkpoint**: credentials can be issued, resolved and revoked, codes minted and redeemed, and entries recorded — nothing is guarded yet.

---

## Phase 3: User Story 1 — Nothing moves without a credential (Priority: P1) 🎯 MVP

**Goal**: every route refuses an unidentified caller; a paired device works as before.

**Independent Test**: quickstart A1–A5 and H1–H2.

### Tests for User Story 1

- [ ] T011 [P] [US1] `backend/tests/contract/test_every_route_is_guarded.py`: walk `app.routes`; every route under `/api/` must carry a `require(...)` dependency or be on the exemption list **`GET /api/health`, `POST /api/auth/pair`**; with `mode = "required"`, every guarded route called without a credential answers **`401` with body exactly `{"error": "unauthorized", "message": "Dieses Gerät ist nicht angemeldet.", "detail": null}`** and no shutter moved (`/api/sim/truth` unchanged)
- [ ] T012 [P] [US1] `backend/tests/contract/test_auth_rest.py` (US1 part): no header / `Bearer sst_garbage` / malformed / expired / revoked give **byte-identical** `401` bodies; each is recorded `auth_failed` with its own `detail.reason`; cookie-authenticated `POST` without or with a foreign `Origin` → **`403 bad_origin`**, bearer without `Origin` passes; anonymous `GET /api/health` → exactly `{"status": "ok"}`
- [ ] T013 [P] [US1] `backend/tests/contract/test_ws_auth.py`: no credential → accepted then closed **`4401`** with zero frames; cookie with foreign `Origin` → `4401`; valid bearer or cookie → snapshot as before
- [ ] T014 [P] [US1] Startup test in `backend/tests/unit/test_auth_config.py`: `bridge.kind = "mqtt"` with `mode = "open"` fails `create_app` with the message; sim without `[auth]` runs open and `GET /api/auth/me` returns `"mode": "open"`

### Implementation for User Story 1

- [ ] T015 [US1] Implement `backend/src/somfy_shutters/auth/gate.py`: `resolve_caller(request)` — bearer header, else cookie `sst`; open mode → `Caller.SIMULATOR`; failures recorded `auth_failed` (actor `anonymous`, `detail.reason`, `detail.source`) and answered with the one `401` body; **cookie + unsafe method requires `Origin` equal to the request origin, else `403 bad_origin`**; `require(ability)` dependency that resolves, then checks the ability → **`403 {"error": "forbidden", "message": "Dieses Gerät darf das nicht.", "detail": {"needs": ...}}`**, recorded `refused_permission` with the path's `shutter_id` if any; successful calls `touch` the credential
- [ ] T016 [US1] Guard every router per the route → ability table in [contracts/rest.md](./contracts/rest.md): `backend/src/somfy_shutters/api/rest.py` (incl. `sim_router`: `watch` for GET, `command` otherwise), `automation_routes.py` (`configure`; GETs `watch`), `group_routes.py` (`configure`; command `command`; GET `watch`), `calibration_routes.py` (`calibrate`; `DELETE …/confirm` `command`; GETs `watch`); `/api/health` reduced to `{"status": "ok"}` for anonymous callers
- [ ] T017 [US1] Authenticate the WebSocket in `backend/src/somfy_shutters/api/ws.py`: resolve before `hub.join`; on failure `accept()` then `close(4401, "unauthorized")`; cookie upgrade needs a matching `Origin`; the hub stores `socket → credential id` and gains `close_for(credential_id, code=4401)`
- [ ] T018 [US1] `backend/src/somfy_shutters/api/auth_routes.py` (US1 part): `GET /api/auth/me` (`watch`) per contract, and `POST /api/auth/pair` (no credential): `{"code", "name"}` → redeem → **`201` with cookie `sst` (`HttpOnly; SameSite=Strict; Path=/; Max-Age=315360000`, `Secure` when the request was HTTPS)**, or the token in the body when `"token": true`; any failure → the one `401`, counted as a failed authentication; `422 invalid_pairing` for a missing name or malformed code; register in `main.py`
- [ ] T019 [US1] `backend/src/somfy_shutters/cli.py` + `[project.scripts] somfy-shutters = "somfy_shutters.cli:main"` in `backend/pyproject.toml`: `auth recover [--name NAME] [--token]` per [contracts/cli.md](./contracts/cli.md) — reads `SHUTTERS_CONFIG`/`SHUTTERS_DB`, mints an **all-abilities code valid 15 minutes** (or `--token` issues a credential), prints it, exits **`0`, or `2` with the reason** when the database or config cannot be opened; unit-test in `backend/tests/unit/test_cli.py` against a temp database while an app instance holds it open
- [ ] T020 [P] [US1] Frontend: `frontend/src/lib/auth.svelte.ts` (`me`, `paired`, `can(ability)`, `load()` from `/api/auth/me`, `pair(code, name)`), `frontend/src/lib/auth.ts` (pure: `formatCode`, `normaliseCode`, ability wording) with `frontend/src/lib/auth.test.ts`; in `frontend/src/lib/shutters.svelte.ts` a **`4401` close sets `paired = false` and stops reconnecting**; every `fetch` answering `401` does the same
- [ ] T021 [US1] `frontend/src/routes/Pair.svelte`: one code field (six characters, shown as `XXX-XXX`, `autocapitalize="characters"`), a device-name field, the server's message on failure, the iOS hint that an installed app pairs separately (plan risks); `frontend/src/App.svelte` shows it instead of the app while `paired` is false, and loads `me` after connecting

**Checkpoint**: the door is shut. The owner gets in by running `somfy-shutters auth recover` on the Pi and typing the code once. Quickstart A and H pass.

---

## Phase 4: User Story 2 — One credential per device, revocable alone (Priority: P1)

**Goal**: list, issue and revoke per device; a revoked device is cut off at once, including its open feed.

**Independent Test**: quickstart B1–B2.

### Tests for User Story 2

- [ ] T022 [P] [US2] Extend `backend/tests/contract/test_auth_rest.py`: `POST /api/auth/credentials` → **`201` with `token` once**; `GET` lists **name, abilities, origin, created_at, last_used_at, expires_at, revoked_at, state, is_me — never a token or hash** (assert no value in the body starts with `sst_` and no 64-hex string appears); revoke → **`204`**, next request with it `401`, the other still works, the list shows `state: "revoked"`; `404 unknown_credential`; issuance and revocation recorded
- [ ] T023 [P] [US2] Extend `backend/tests/contract/test_ws_auth.py`: a socket open with credential A closes **`4401` within 1 s** of revoking A; B's socket stays open; an expired credential's socket closes on the next sweep

### Implementation for User Story 2

- [ ] T024 [US2] `GET/POST /api/auth/credentials` and `DELETE /api/auth/credentials/{id}` (`manage`) in `backend/src/somfy_shutters/api/auth_routes.py`; revoke calls `hub.close_for(id)` and `auth.cancel_minted_by(id)`, records `credential_revoked`; issuance records `credential_issued`
- [ ] T025 [US2] Expiry sweep in the existing tick loop of `backend/src/somfy_shutters/main.py`: **every 30 s** close sockets of credentials that expired, record `credential_expired` once
- [ ] T026 [US2] `frontend/src/routes/Devices.svelte` (`manage` only): list with name, abilities in words, *zuletzt benutzt vor …*, state; *Widerrufen* with an inline confirm; *Neues Gerät (Token)* showing the token once with a copy button and the warning that it cannot be shown again; navigation from `frontend/src/App.svelte`

**Checkpoint**: quickstart B passes.

---

## Phase 5: User Story 3 — A credential can do less than everything (Priority: P2)

**Goal**: abilities limit what a credential can do and what it can hand on.

**Independent Test**: quickstart C1–C3.

### Tests for User Story 3

- [ ] T027 [P] [US3] `backend/tests/contract/test_abilities.py`: for each ability, a credential holding only it (plus `watch`) is refused **`403` with `detail.needs`** on one route of every other ability and accepted on its own; refusals recorded `refused_permission`; issuing or minting with more than one's own → **`403 exceeds_own` with `detail.abilities`**

### Implementation for User Story 3

- [ ] T028 [US3] Granting rule in `backend/src/somfy_shutters/auth/store.py` and `api/auth_routes.py`: requested abilities must be a subset of the caller's (**FR-011, FR-032**); `watch` always added
- [ ] T029 [US3] Frontend hides what `can()` denies: command buttons (`command`), rule/group/location editing (`configure`), calibration screens and **the arrival prompt (`calibrate`)**, Devices and Record (`manage`) — in `frontend/src/routes/*.svelte`, `frontend/src/components/*.svelte`; ability checkboxes in `Devices.svelte` offer only the caller's own abilities; wording in `frontend/src/lib/auth.ts` ("zusehen", "fahren", "einstellen", "kalibrieren", "Geräte verwalten")

**Checkpoint**: quickstart C passes.

---

## Phase 6: User Story 4 — Adding a phone without typing a long secret (Priority: P2)

**Goal**: a paired device mints a six-character code; a new device redeems it for its own credential.

**Independent Test**: quickstart D1–D5.

### Tests for User Story 4

- [ ] T030 [P] [US4] `backend/tests/contract/test_pairing_rest.py`: mint → **`201` with `code` `XXX-XXX` and `expires_at` 5 minutes ahead**; `GET` lists outstanding codes **without the code**; redeem gives exactly the minted abilities and `origin: "paired"`; second redemption `401`; cancel → `401`; revoke the minter → `401`; **ten failed redemptions in total while a code is outstanding cancel it** (recorded `pairing_cancelled`); mint, redeem, fail, cancel, expire all recorded

### Implementation for User Story 4

- [ ] T031 [US4] `POST/GET /api/auth/pairing` and `DELETE /api/auth/pairing/{id}` (`manage`) in `backend/src/somfy_shutters/api/auth_routes.py`; the global guess cap (research §7) as an in-memory counter reset when no code is outstanding; expired codes recorded `pairing_expired` by the sweep of T025
- [ ] T032 [US4] Pairing in `frontend/src/routes/Devices.svelte`: *Gerät koppeln* → choose abilities (own only) → big `XXX-XXX` with a live countdown and *Abbrechen*; the list refreshes when the new device appears

**Checkpoint**: quickstart D passes.

---

## Phase 7: User Story 5 — Explaining a movement afterwards (Priority: P2)

**Goal**: every command, refusal and observed movement is in the record, attributed, and readable in the app.

**Independent Test**: quickstart E1–E5.

### Tests for User Story 5

- [ ] T033 [P] [US5] `backend/tests/contract/test_audit_rest.py`: commands from two credentials appear newest first with names and `accepted`; filter by shutter and by actor; paging with `before`/`next_before`; a revoked credential's entries keep its name with `state: "revoked"`; an injected external movement (`POST /api/sim/report`) appears as actor `bridge`, action `movement_observed`; an automation firing appears as actor `automation` with the rule id; `GET /api/audit` needs `manage`
- [ ] T034 [P] [US5] `backend/tests/unit/test_apply_records.py`: `commands.apply` records **after** `send_level` (a bridge stub asserts no entry exists at send time); a failing `record` still returns the movement; bridge unreachable → `failed`, measurement → `skipped`

### Implementation for User Story 5

- [ ] T035 [US5] `backend/src/somfy_shutters/commands.py`: `apply(..., actor=Actor.SYSTEM)` and `apply_many(..., actor=...)`; record `command` with `detail.action`/`detail.percent` and outcome after the send, and `skipped`/`failed` on the two exceptions, with `clock_ok` from `state.automation.verdict`; pass the caller's actor from every command route (`api/rest.py`, `api/group_routes.py`), `Actor("automation", rule.id, rule.name)` from `backend/src/somfy_shutters/automation/engine.py`, and record `resync` in `rest.py`
- [ ] T036 [US5] Record configuration and calibration changes (`rule_changed`, `group_changed`, `location_changed`, `pause_changed`, `calibration`) in `api/automation_routes.py`, `api/group_routes.py`, `api/calibration_routes.py`
- [ ] T037 [US5] Bus listener in `backend/src/somfy_shutters/main.py`: `movement` events with **`origin == "external"`** → `movement_observed`, actor `bridge`; daily `audit.purge(now - audit_retention_days)` beside the firing purge
- [ ] T038 [US5] `GET /api/audit` (`manage`) in `backend/src/somfy_shutters/api/audit_routes.py` per contract; register in `main.py`
- [ ] T039 [US5] `frontend/src/routes/Record.svelte`: newest first, one line per entry ("11:02 · Küche · Wohnzimmer zu · ausgeführt"), filters by shutter and by device, *Ältere laden*, refused entries marked, observed movements worded as "bemerkt, nicht von der App"; wording in `frontend/src/lib/auth.ts` with tests

**Checkpoint**: quickstart E passes.

---

## Phase 8: User Story 6 — Getting back in after losing everything (Priority: P2)

**Goal**: recovery by physical presence is recorded and safe; the app warns before locking the owner out.

**Independent Test**: quickstart F1–F2.

### Tests for User Story 6

- [ ] T040 [P] [US6] Extend `backend/tests/unit/test_cli.py` and `test_auth_rest.py`: recovery records a `recovery` entry; revoking the last active `manage` credential → **`409 last_manager`** unless `{"confirm_lockout": true}`; after revoking everything and recovering, shutters, calibration, rules, groups, firings and the record are unchanged (row counts before/after); `auth list` prints no secret

### Implementation for User Story 6

- [ ] T041 [US6] Last-manager check in `DELETE /api/auth/credentials/{id}` (`backend/src/somfy_shutters/api/auth_routes.py`); `auth list` and the `recovery` entry in `backend/src/somfy_shutters/cli.py`
- [ ] T042 [US6] Lockout warning in `frontend/src/routes/Devices.svelte`: on `409 last_manager` explain that only `somfy-shutters auth recover` on the Pi gets back in, and ask again; upgrade note and recovery in `deploy/README.md`

**Checkpoint**: quickstart F passes.

---

## Phase 9: User Story 7 — Guessing and flooding are throttled (Priority: P3)

**Goal**: failed attempts lock out their source; command floods are cut off before the bridge.

**Independent Test**: quickstart G1–G3.

### Tests for User Story 7

- [ ] T043 [P] [US7] `backend/tests/unit/test_throttle.py` on an injected monotonic clock: **10 failures in 5 minutes lock the source for 15 minutes**, the window slides, other sources unaffected; bucket **burst 10, refill 1/s**; a wall-clock jump of −6 h changes nothing
- [ ] T044 [P] [US7] Extend `backend/tests/contract/test_auth_rest.py`: an eleventh failure → **`429` with `Retry-After`**, even with a valid token from that source; another source is fine; thirty commands in two seconds → about ten accepted, the rest `429` recorded `refused_throttle`, and the simulated bridge received only the accepted ones; `X-Forwarded-For` ignored unless `trusted_proxy` matches the peer; a throttled WebSocket closes `4429`

### Implementation for User Story 7

- [ ] T045 [US7] `backend/src/somfy_shutters/auth/throttle.py` (failure windows per source, token buckets per credential, injected `monotonic`) and its use in `auth/gate.py`: a locked source is answered `429` **before** any lookup; `command` routes draw from the bucket; both recorded `throttled`; source address = socket peer, or the first `X-Forwarded-For` hop only when the peer equals `trusted_proxy`

**Checkpoint**: quickstart G passes.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T046 [P] Scenario tests A–H of [quickstart.md](./quickstart.md) in `backend/tests/integration/test_auth_quickstart.py` with the simulator and `mode = "required"`
- [ ] T047 Walk quickstart A4, B, D1 and F1 by hand in two browsers (one a private window), including pairing from a phone on the home network
- [ ] T048 [P] Update `README.md` ("What works today", test counts), `CLAUDE.md` (auth mode, `somfy-shutters auth recover`) and `deploy/README.md` (first run after upgrade)
- [ ] T049 On the Pi, once a motor is paired: quickstart I1 — a paired phone moves it and the move is recorded; without a credential nothing reaches Pi-Somfy (broker log). Joins the pending hardware checks of features 001–004

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (1)** → **Foundational (2)** → user stories.
- **US1 (3)** first: every other story needs the gate and a way in.
- **US2 (4)** needs US1. With US1 it is the MVP: a door with per-device keys.
- **US3 (5)** needs US1's gate (which already checks abilities) and US2's issuing.
- **US4 (6)** needs US1's redemption and US3's granting rule.
- **US5 (7)** needs US1; independent of US2–US4 except for naming actors.
- **US6 (8)** needs US1's CLI and US2's revocation.
- **US7 (9)** needs US1's gate; independent otherwise.
- **Polish (10)** after the stories it tests. T049 needs hardware.

### Within Phase 2

T003–T005 in parallel; T006 after T003/T005; T008 in parallel with T006; tests beside each; T010 last.

### Parallel opportunities

- Phase 2: T003/T004 ∥ T005 ∥ T008/T009.
- US1: T011–T014 together; T020 while T015–T019 are done.
- US2: T022, T023 together. US3: T027 alone, then T028 ∥ T029.
- After US1: US5 and US7 can proceed in parallel with US2–US4.
- Polish: T046, T048 together.

---

## Implementation Strategy

### MVP first

1. Phases 1 + 2: tables, tokens, a record that cannot block.
2. Phase 3 (US1): the door, recovery-as-first-run, the pairing screen. **Stop and validate with quickstart A and H** — the house is no longer open to anyone on the network.
3. Phase 4 (US2): per-device keys and revocation. This is the MVP the spec's remote-access work waits for.

### Incremental delivery

4. US3 abilities, US4 pairing from the app, US5 the record, US6 recovery hardening, US7 throttling.
5. Polish, then T049 when a motor is paired.

### Task counts

| Phase | Tasks |
|---|---|
| Setup | 2 |
| Foundational | 8 |
| US1 | 11 |
| US2 | 5 |
| US3 | 3 |
| US4 | 3 |
| US5 | 7 |
| US6 | 3 |
| US7 | 3 |
| Polish | 4 |
| **Total** | **49** |
