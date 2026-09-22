# REST contract: API authentication and audit

Errors keep the shared shape `{"error", "message", "detail"}`; messages are German.

## Presenting a credential

- `Authorization: Bearer sst_…`, or
- cookie `sst=sst_…` (set by `POST /api/auth/pair`). Cookie-authenticated `POST`, `PUT`,
  `PATCH`, `DELETE` must send an `Origin` equal to the request's origin, else
  `403 {"error": "bad_origin"}`.

## Refusals (every `/api/*` route)

| Status | Body `error` | When |
|---|---|---|
| `401` | `unauthorized` | no, unknown, malformed, expired or revoked credential — one body for all (FR-003) |
| `403` | `forbidden` | known credential without the route's ability; `detail.needs` names it |
| `429` | `throttled` | failed-auth lockout or command rate; `Retry-After` header in seconds |

`401` message: "Dieses Gerät ist nicht angemeldet." `403` message: "Dieses Gerät darf das
nicht." `429` message: "Zu viele Versuche. Bitte kurz warten."

## Route → ability

| Ability | Routes |
|---|---|
| none | `GET /api/health` (anonymous: `{"status": "ok"}` only), `POST /api/auth/pair`, everything outside `/api/` |
| `watch` | every other `GET /api/*`, `GET /api/ws`, `GET /api/auth/me` |
| `command` | `POST /api/shutters/command`, `POST /api/shutters/{id}/command`, `POST /api/shutters/{id}/resync`, `POST /api/groups/{id}/command`, `DELETE /api/calibration/{id}/confirm` (dismiss prompt) |
| `configure` | `POST/PUT/PATCH/DELETE /api/automations…` incl. pause and preview, `PUT /api/location`, `POST/PUT/DELETE /api/groups…` except command |
| `calibrate` | every other `POST/DELETE /api/calibration/…` |
| `manage` | `/api/auth/credentials…`, `/api/auth/pairing…`, `GET /api/audit` |
| sim only | `/api/sim/*` — registered only with the simulator; `watch` for `GET`, `command` otherwise |

A route added later without an entry fails `tests/contract/test_every_route_is_guarded.py`.

## `GET /api/auth/me` — `watch`

```json
{ "id": "c_4Fq9", "name": "Küche", "abilities": ["watch", "command"], "origin": "paired",
  "expires_at": null, "mode": "required" }
```

In open mode: `{"id": null, "name": "Simulator", "abilities": [all five], "origin": "simulator", "mode": "open"}`.

## Credentials — `manage`

### `GET /api/auth/credentials`

```json
{ "credentials": [
  { "id": "c_4Fq9", "name": "Küche", "abilities": ["watch", "command"], "origin": "paired",
    "created_at": "…", "last_used_at": "…", "expires_at": null,
    "revoked_at": null, "state": "active", "is_me": true }
] }
```

`state`: `active` | `revoked` | `expired`. Never a secret or its hash (FR-007).

### `POST /api/auth/credentials`

Body: `{"name": "Kurzbefehl Nacht", "abilities": ["command"], "expires_at": null}`

`201` → the credential object plus `"token": "sst_…"` — the only time it is ever sent
(FR-006). `422 invalid_credential` (name, unknown ability), `403 exceeds_own` with
`detail.abilities` when asking for more than the caller holds (FR-011).

### `DELETE /api/auth/credentials/{id}`

`204`. Revokes; open sockets of that credential close at once (FR-005). Outstanding
pairing codes it minted are cancelled. `404 unknown_credential`.
`409 last_manager` when it is the last active `manage` credential, unless the body is
`{"confirm_lockout": true}` (FR-013). Revoking oneself is allowed.

## Pairing

### `POST /api/auth/pairing` — `manage`

Body: `{"abilities": ["watch", "command"]}` → `201`
`{"id": "p_…", "code": "K7Q-9XM", "abilities": [...], "expires_at": "…"}`.
`403 exceeds_own` as above.

### `DELETE /api/auth/pairing/{id}` — `manage`

`204`, or `404 unknown_code`. Cancels (FR-035).

### `GET /api/auth/pairing` — `manage`

Outstanding codes: id, abilities, expires_at — never the code.

### `POST /api/auth/pair` — no credential needed

Body: `{"code": "k7q9xm", "name": "Annas Handy"}`

| Status | When |
|---|---|
| `201` | `{"credential": {...}}`, cookie `sst` set (`HttpOnly; SameSite=Strict; Path=/; Max-Age=315360000`, plus `Secure` over HTTPS). With `"token": true` in the body the token is returned instead of a cookie, for non-browser clients |
| `401 unauthorized` | unknown, spent, cancelled or expired code, or its minter revoked — one body for all; counts as a failed authentication |
| `422 invalid_pairing` | missing name or malformed code (not counted) |
| `429 throttled` | source locked out |

## Record — `manage`

### `GET /api/audit?shutter=&actor=&before=&limit=`

Newest first by id. `limit` default 50, max 200. `before` is an entry id, for paging.

```json
{ "entries": [
  { "id": 1873, "at": "2026-09-23T11:02:14+02:00", "clock_ok": true,
    "actor": {"kind": "credential", "id": "c_4Fq9", "name": "Küche", "state": "revoked"},
    "action": "command", "shutter_id": "wohnzimmer", "target": null,
    "outcome": "accepted", "detail": {"action": "close"} }
], "next_before": 1824 }
```

Times are local wall clock with offset, as elsewhere in the API.

## Changed routes

- `GET /api/health`: anonymous callers get `{"status": "ok"}` only; with `watch` the
  existing body.
- Every command route: a refused or throttled attempt is recorded before the refusal is
  sent; an accepted one is recorded by `commands.apply` after the frame goes out.
