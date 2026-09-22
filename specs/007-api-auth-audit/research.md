# Research: API authentication and audit

Decisions taken while planning feature 007, each with what was weighed against it.
The spec was written before features 003 (automations) and 004 (groups) landed; this
plan covers the routes they added, and the ones specs 005 and 006 will add.

## 1. The credential: an opaque random token, stored as its SHA-256

**Decision**: a credential is `sst_` + 32 random bytes, base32 (Crockford, no padding) —
56 characters. The server stores `sha256(token)` and looks it up by that hash; the value
itself is never stored (FR-004).

**Rationale**: 256 bits of randomness make guessing hopeless whatever the rate (SC-005),
so a slow password hash (bcrypt, argon2) buys nothing and would cost a Pi a noticeable
fraction of a second per request. A plain hash of a high-entropy secret is the standard
construction for API tokens. The `sst_` prefix makes a leaked token recognisable in a
log or a paste. Lookup by hash needs no constant-time comparison: the attacker never
controls a comparison against a stored secret.

**Alternatives considered**: signed JWTs (rejected: revocation needs a server-side list
anyway, which removes the only advantage, and adds a signing key to protect); bcrypt of
the token (rejected: cost without benefit, see above); `secrets.token_urlsafe` (fine, but
Crockford base32 is unambiguous when a person does have to read one out).

## 2. How a client presents it: cookie for the app, bearer header for everything else

**Decision**: two ways in, checked in this order:

1. `Authorization: Bearer <token>` — shortcuts, scripts, a later assistant.
2. Cookie `sst` — the web app. Set by the server on pairing redemption, `HttpOnly`,
   `SameSite=Strict`, `Path=/`, `Max-Age` ten years. The credential's own expiry and
   revocation are enforced server-side, so the cookie lifetime only has to outlast them.

State-changing requests authenticated **by cookie** must carry an `Origin` header equal
to the request's own origin; the WebSocket upgrade must too. Bearer requests are exempt:
no browser attaches a bearer header on its own. In open mode (the simulator, §10) there
is no credential to protect and no check is made.

**Rationale**: FR-028 — present once, never asked again, no login screen. An `HttpOnly`
cookie survives reloads and PWA restarts, is sent on the WebSocket upgrade (a browser
cannot set headers on `new WebSocket`), and cannot be read by script, so an XSS bug
cannot exfiltrate it. `SameSite=Strict` stops cross-site sends; the `Origin` check closes
the gap `SameSite` leaves open for other ports on the same host (Pi-Somfy's own web UI
runs on the same Pi and is "same site").

**Alternatives considered**: token in `localStorage` plus a header (rejected: readable by
any script on the page, and the WebSocket needs it in the URL, where it lands in logs);
token as a WebSocket query parameter (rejected for the same logging reason);
a session cookie separate from the credential (rejected: a second thing to expire and
revoke, with no benefit for a household).

`Secure` is not set: until a later remote-access feature adds TLS the app is served over
plain HTTP on the home network, which the spec's assumptions accept. The flag is set
automatically when the request arrived over HTTPS (`request.url.scheme` or
`X-Forwarded-Proto` from a configured proxy), so that feature needs no change here.

## 3. Abilities: five, not four

**Decision**:

| Ability | Covers |
|---|---|
| `watch` | every `GET`, the WebSocket, `GET /api/auth/me` |
| `command` | shutter and group commands, "Alle auf/zu", resync, the arrival prompt's *dismiss* |
| `configure` | automation rules, pause/resume/skip, groups, location, and spec 005's add/remove |
| `calibrate` | calibration runs, marks, checks, confirming an arrival (it writes a measured time) |
| `manage` | issuing, revoking, pairing codes, reading the record |

Every ability implies `watch`: a credential that may close a shutter may see it.
The spec asks for "at minimum" four; `configure` is the fifth because features 003 and
004 added things that are neither commanding nor measuring. A night-time "close"
shortcut should not be able to create a rule that opens every window at 3 a.m.

**Reading the record needs `manage`**: the record says which device did what, and that
is the owner's view, not every phone's.

**Rationale**: FR-010, FR-011, user story 3. The table is enforced by one mapping from
route to ability (§4), so a new route cannot be forgotten.

## 4. One gate, default deny, proven by a test over every route

**Decision**: a FastAPI dependency `require(ability)` on each router or route, plus a
test that walks `app.routes` and fails for any `/api/*` route that declares no ability
and is not on the explicit exemption list: `GET /api/health` (reduced to
`{"status": "ok"}` for an anonymous caller), `POST /api/auth/pair` (redemption — it is
how a device gets a credential), and everything outside `/api/` (the built app, its
manifest, icons and service worker).

`GET /api/health` uses `optional_caller()`: it resolves a credential if one is presented
and answers the full body with `watch`, else `{"status": "ok"}` — and an anonymous or
failed attempt there is **neither recorded nor counted** towards a lockout, so a
monitoring ping cannot lock its own address out.

**Rationale**: FR-002 asks for complete coverage with a minimal, stated list of
exceptions. Middleware that inspects paths would work but hides the mapping; a
dependency on the route keeps the ability next to the code it guards, and the test makes
"forgot to guard it" a failing build rather than an open door. Specs 005 and 006 add
routes; this test is what makes them safe by default.

**Alternatives considered**: ASGI middleware with a path table (rejected: the table drifts
from the routes); decorators (rejected: FastAPI dependencies already are that).

## 5. Refusals look the same

**Decision**: every authentication failure — no credential, unknown, expired, revoked,
malformed — is `401 {"error": "unauthorized", "message": "Dieses Gerät ist nicht
angemeldet.", "detail": null}`, and closes a WebSocket with code `4401` before any frame.
A missing ability is `403 {"error": "forbidden", ...}` — distinguishable on purpose: the
caller is known, and telling it what it lacks is useful and leaks nothing. Throttling is
`429` with `Retry-After`.

**Rationale**: FR-003 — the caller must not learn whether a stolen token was revoked or
never existed. The record, not the response, distinguishes them (edge case: expired vs
unrecognised).

## 6. Revocation reaches open WebSockets at once

**Decision**: the hub remembers the credential id of every socket. Revoking a credential
closes its sockets immediately (`4401`), in the same process. A sweep every 30 s closes
sockets whose credential has expired.

**Rationale**: FR-005 — "within a stated short period": immediate on revoke, ≤ 30 s on
expiry. One process owns both the sockets and the credential table, so no messaging is
needed.

## 7. Pairing codes

**Decision**: six characters from Crockford base32 (no `I L O U`), shown as `K7Q-9XM`,
case- and dash-insensitive on entry. Stored hashed. Valid 5 minutes, configurable.
Spent on the first redemption attempt that names it, whether or not the exchange then
succeeds (FR-031). Redemption checks, in one transaction: unspent, uncancelled,
unexpired, **minting credential still active** (edge case), then marks it spent and
creates the credential — so two racing devices cannot both win.

Guessing: each failed redemption counts as a failed authentication for its source (§8).
Additionally, **ten failed redemptions in total while any code is outstanding cancel every
outstanding code** and are recorded — a distributed guesser gets ten tries, not ten per
address.

**Rationale**: 32⁶ ≈ 10⁹ codes; ten tries against one live code is a 10⁻⁸ chance.
Short enough to read out (FR-033, SC-007). The new credential's name is typed by the
redeeming device ("Annas Handy"), its abilities are fixed at minting (FR-032).

**Alternatives considered**: QR code (useful later, but reading a code aloud works across
a room and over the phone, and needs no camera permission); a longer code (rejected:
SC-007).

## 8. Throttling in memory, on the monotonic clock

**Decision**:

- **Failed authentication per source address**: 10 failures within 5 minutes → refused
  (`429`) for 15 minutes. Configurable under `[auth]`.
- **Commands per credential**: token bucket, 10 requests burst, refilled at 1 per second.
  Applies to routes needing `command`. A group command is one request. The excess is
  refused and recorded, never forwarded (FR-023). The ability is checked first: a request
  refused for permission does not draw from the bucket.
- Both kept in process memory, on `time.monotonic()`.

**Rationale**: FR-021–FR-024. The edge case of a Pi clock jumping hours at boot would
lock the owner out, or unlock an attacker, if throttling used wall time; the monotonic
clock does not jump. Memory is enough: a restart clears it, which an attacker cannot
trigger remotely, and it avoids writing to the SD card on every failed request. The
source address is the socket peer; behind a configured reverse proxy (later feature)
it becomes the first `X-Forwarded-For` hop — only when that proxy is configured, never by
default, since the header is trivially forged.

**Alternatives considered**: persisting throttle state (rejected: SD wear, no gain);
a limiter library such as `slowapi` (rejected, constitution V: forty lines of our own).

## 9. The record: one table, written after the command, never in its way

**Decision**: table `audit_entry` in the existing database. Commands are recorded by
`commands.apply` itself, which gains an `actor` argument: the route passes the
credential, the automation engine passes `automation:<rule id>`, the calibration flow
passes its credential. The entry is written **after** the frame is handed to the bridge;
the insert is wrapped so that a failure logs an error and never raises (FR-020).
Refusals (permission, throttle) are recorded by the gate, which knows the route and,
where the path names one, the shutter.

Inferred movement (FR-016): an event-bus listener records every `movement` event whose
origin is `external` — a physical remote or another controller — with actor `bridge`.
Reports that merely confirm a movement the app started are not recorded; they would
drown the record in echoes.

Ordering is by the autoincrement id, not by wall time, so a clock jump never reorders the
record (edge case); both the wall time and a "clock was unreliable" flag (from feature
003's clock guard) are stored so a jumped entry can be explained.

Retention: 180 days, `[auth] audit_retention_days`. Purged once a day by the existing
automation loop, beside firing retention.

**Rationale**: `commands.apply` is already the one command path (features 003/004), so
attributing there cannot miss a caller. Writing after sending keeps SC-004 (no slower to
a person). SQLite in WAL mode lets the record be read while commands are written.

**Alternatives considered**: a queue and writer task (rejected: an insert is well under a
millisecond; a queue adds a loss window on crash); Python `logging` to a file (rejected:
FR-018 wants it filterable in the app).

## 10. The simulator exemption, and why it cannot leak onto a real house

**Decision**: `[auth] mode = "required" | "open"`. Default: `"open"` when
`bridge.kind = "sim"`, `"required"` otherwise. `mode = "open"` with any other bridge is a
configuration error: the app refuses to start and says why (FR-029, SC-009, edge case).
In open mode every request acts as a built-in pseudo-credential `simulator` with all
abilities, so the record still has an actor and the UI behaves as for an owner.

**Rationale**: SC-008 — development against the simulator needs no new step, and the
existing tests keep running unchanged. The exemption is keyed to the thing that makes
it harmless (no radio), not to a flag a person could leave on. Tests of this feature run
the simulator with `mode = "required"`.

## 11. First run and recovery are the same thing: a command on the Pi

**Decision**: `somfy-shutters auth recover [--name NAME]`, a console script run on the
Pi as the service user. It opens the database directly, creates a pairing code with all
five abilities and a 15-minute lifetime, records a `recovery` entry, and prints the code.
The owner types it into the phone. `--token` instead prints a full credential for
headless use.

After upgrading an existing installation, no credential exists, so the app shows the
pairing screen and the upgrade notes say to run this once. Nothing else changes: the
same database, tables added with `CREATE TABLE IF NOT EXISTS` (FR-027).

**Rationale**: FR-025/FR-026 — "physical access" to a headless Pi means a shell on it
(keyboard or SSH with the owner's key); the network API has no recovery route at all,
so there is nothing to attack remotely. Printing a pairing code rather than a token keeps
the owner from transcribing 56 characters (SC-006, SC-007). The command works while the
service runs: SQLite serialises the writes, and the service reads credentials from the
table on every request.

**Alternatives considered**: a recovery file dropped on the SD card (rejected: needs a
restart and a second code path); a physical button on GPIO (rejected: new hardware,
constitution V).

## 12. Last-used time without a write per request

**Decision**: `last_used_at` is updated at most once a minute per credential, from an
in-memory "last written" map.

**Rationale**: FR-007 wants it; per-request writes would put the SD card under the
WebSocket's reconnect rate. A minute of imprecision is invisible in a list that says
"zuletzt benutzt vor 3 Std.".

## 13. The last manager

**Decision**: after any revocation at least one active credential holding `manage`
**and having no expiry** must remain. Otherwise the revocation needs
`confirm_lockout: true`; without it the API answers `409 last_manager` and the UI shows
why and what recovery then means (FR-013).

**Rationale**: counting an expiring manager as "remaining" would let the owner revoke the
permanent one and be locked out silently weeks later, when the other expires. Issuing a
credential never reduces the set, so only revocation is checked. Recovery credentials
have no expiry, so the first manager always qualifies.

## 14. What the frontend needs

- `GET /api/auth/me` → name and abilities, so the UI hides what the credential may not
  do instead of offering buttons that answer 403. The arrival prompt of feature 002
  appears only with `calibrate`.
- A **pairing screen** shown when the socket closes with `4401` or any call answers
  `401`: one six-character field and a name. It is not a login screen — nothing to
  remember, used once per device (FR-028).
- A **devices screen** (`manage`): list, revoke, issue a token, mint a pairing code with
  a countdown, cancel it.
- A **record screen** (`manage`): newest first, filter by shutter and by credential,
  paged.
