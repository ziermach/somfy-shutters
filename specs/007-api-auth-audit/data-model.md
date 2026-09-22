# Data model: API authentication and audit

Three new tables in the app's existing SQLite database, created with
`CREATE TABLE IF NOT EXISTS` — an upgrade adds them and touches nothing else (FR-027).
Throttle state is in memory only (research §8).

## Tables

```sql
CREATE TABLE IF NOT EXISTS credential (
    id            TEXT PRIMARY KEY,          -- "c_" + random; shown in the record, never secret
    name          TEXT NOT NULL,             -- "Küche", "Annas Handy"; 1–40 chars, trimmed
    secret_hash   TEXT NOT NULL UNIQUE,      -- hex sha256 of the token (research §1)
    abilities     TEXT NOT NULL,             -- JSON list, subset of ABILITIES
    origin        TEXT NOT NULL,             -- issued | paired | recovery
    created_by    TEXT,                      -- credential id, NULL for recovery
    created_at    TEXT NOT NULL,
    last_used_at  TEXT,                      -- written at most once a minute (research §12)
    expires_at    TEXT,                      -- optional (FR-012)
    revoked_at    TEXT,
    revoked_by    TEXT                       -- credential id
);

CREATE TABLE IF NOT EXISTS pairing_code (
    id            TEXT PRIMARY KEY,          -- "p_" + random
    code_hash     TEXT NOT NULL UNIQUE,      -- sha256 of the normalised six characters
    abilities     TEXT NOT NULL,             -- fixed at minting (FR-032)
    minted_by     TEXT,                      -- credential id; NULL when minted by recovery
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    spent_at      TEXT,                      -- first redemption attempt naming it (FR-031)
    cancelled_at  TEXT,
    credential_id TEXT                       -- what it produced, if the exchange succeeded
);

CREATE TABLE IF NOT EXISTS audit_entry (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,  -- the order (research §9)
    at            TEXT NOT NULL,             -- UTC wall time
    clock_ok      INTEGER NOT NULL,          -- feature 003's clock verdict at that moment
    actor_kind    TEXT NOT NULL,             -- credential | automation | bridge | recovery | simulator | anonymous
    actor_id      TEXT,                      -- credential id, rule id, or NULL
    actor_name    TEXT,                      -- name at that moment; survives revocation (FR-017)
    action        TEXT NOT NULL,             -- see "Actions"
    shutter_id    TEXT,                      -- when one shutter is concerned
    target        TEXT,                      -- group id, "all", credential id, code id …
    outcome       TEXT NOT NULL,             -- see "Outcomes"
    detail        TEXT NOT NULL DEFAULT '{}' -- JSON: percent, reason, source address …
);

CREATE INDEX IF NOT EXISTS audit_entry_shutter    ON audit_entry (shutter_id, id);
CREATE INDEX IF NOT EXISTS audit_entry_actor      ON audit_entry (actor_id, id);
CREATE INDEX IF NOT EXISTS audit_entry_at         ON audit_entry (at);
```

## Entities

### Credential

| Field | Rules |
|---|---|
| `name` | 1–40 characters after trimming; need not be unique (two "Handy"s are allowed, the id tells them apart) |
| `abilities` | non-empty subset of `watch`, `command`, `configure`, `calibrate`, `manage`; `watch` is always added |
| token | `sst_` + 52 Crockford-base32 characters (32 bytes); exists in full only in the issuing response |
| active | `revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now)` |

**Granting rule (FR-011, FR-032)**: a credential can issue, or mint a code for, only a
subset of its own abilities. Recovery grants all five.

**States**: active → revoked (terminal) · active → expired (terminal; distinguished from
revoked in the record, identical to the caller).

### Pairing code

| Field | Rules |
|---|---|
| code | 6 characters from `0123456789ABCDEFGHJKMNPQRSTVWXYZ`; displayed `XXX-XXX`; entry normalised by upper-casing and dropping `-` and spaces |
| lifetime | 5 minutes (`[auth] pairing_minutes`); recovery codes 15 minutes |
| redeemable | not spent, not cancelled, not expired, and `minted_by` still active (or NULL) |

**States**: outstanding → spent (redemption attempted; `credential_id` set if it
succeeded) · outstanding → cancelled (by the owner, by the minting credential's
revocation, or by the global guess cap of research §7) · outstanding → expired.

### Audit entry

**Actions**

| Action | Written by | Notes |
|---|---|---|
| `command` | `commands.apply` | `detail.action` open/close/stop/position, `detail.percent` |
| `resync` | the resync route | |
| `movement_observed` | bus listener | external origin only (FR-016), actor `bridge` |
| `calibration` | calibration routes | run start/abort, mark, confirm, check answer |
| `rule_changed`, `group_changed`, `location_changed`, `pause_changed` | the routes | `configure` actions; `target` names the rule/group |
| `credential_issued`, `credential_revoked`, `credential_expired` | auth routes, sweep | `target` = credential id |
| `pairing_minted`, `pairing_redeemed`, `pairing_failed`, `pairing_cancelled`, `pairing_expired` | auth routes, sweep | |
| `recovery` | the CLI | actor `recovery` |
| `auth_failed` | the gate | `detail.reason` none/unknown/expired/revoked/malformed, `detail.source` |
| `throttled` | the gate | `detail.kind` auth/command |

**Outcomes**: `accepted` · `refused_permission` · `refused_throttle` ·
`refused_auth` · `skipped` (measurement in progress) · `failed` (bridge unreachable).

Automation firings keep their own per-shutter records (feature 003); each command they
send additionally appears here with actor `automation`, so "who moved it" has one answer
place (SC-003).

**Retention**: rows with `at` older than `[auth] audit_retention_days` (default 180) are
deleted once a day.

## Configuration (`shutters.toml`)

```toml
[auth]
# "required" everywhere except the simulator, where the default is "open" (research §10).
# "open" with bridge.kind = "mqtt" refuses to start.
# mode = "required"
failed_attempts = 10          # per source address …
failed_window_minutes = 5     # … within this window …
lockout_minutes = 15          # … locks it out for this long
command_burst = 10            # commands per credential in a burst …
command_per_second = 1.0      # … refilled at this rate
pairing_minutes = 5
audit_retention_days = 180
# trusted_proxy = "127.0.0.1" # only then is X-Forwarded-For believed
```

## In memory

| Structure | Key | Holds |
|---|---|---|
| failure window | source address | monotonic times of recent failures; lockout-until |
| command bucket | credential id | tokens, last refill (monotonic) |
| last-used writes | credential id | monotonic time of the last `last_used_at` write |
| socket owners | WebSocket | credential id (research §6) |
| outstanding-guess counter | — | failed redemptions since the oldest outstanding code was minted |
