# Contract: Pi-Somfy's command interface, as this app uses it

Known only to `backend/src/somfy_shutters/bridge/manage.py`. Base URL `bridge.manage_url`
(e.g. `http://127.0.0.1:80`); header `Password: <bridge.manage_password>` when configured.
Requests are `POST` with form parameters; timeout 5 s; no retries (a doubled `program` would
undo the pairing).

| Call | Request | Success | Failure |
|---|---|---|---|
| probe | `/cmd/getConfig` | 200 JSON with `Shutters` | anything else → unavailable |
| add | `/cmd/addShutter` `name`, `duration` | `{"status":"OK","id":"0x…"}` | `{"status":"ERROR","message"}` |
| program | `/cmd/program` `shutter` | `{"status":"OK"}` | ERROR "Shutter does not exist" |
| rename | `/cmd/editShutter` `id`, `name`, `duration` | `{"status":"OK", "nameChanged"}` | ERROR |
| delete | `/cmd/deleteShutter` `id` | `{"status":"OK"}` | ERROR |

- The returned id is lower-cased and validated against `^0x[0-9a-f]{6}$`; anything else is
  treated as a refusal — the app never guesses an address.
- `"Name is not unique"` on add or rename → retry once per suffix `_2` … `_9` (research §8).
- HTTP 200 with `status: ERROR` → `BridgeRefused(message)`; HTTP ≥ 400, timeout, connection
  error → `ManagementUnavailable`.
- Never called: `up`, `down`, `stop`, `setPosition`, `press` — driving stays on MQTT
  (constitution II as amended).

## The bridge patch (`deploy/pi-somfy-live-shutters.patch`)

| Bridge event | Added behaviour |
|---|---|
| `addShutter` OK | subscribe `somfy/<id>/command` and `/set_position`; publish discovery (retained) |
| `editShutter` with a new name | publish discovery again |
| `deleteShutter` OK | unsubscribe both; publish an empty retained message on its discovery topic |

Without the patch the app still works; a new shutter then needs one bridge restart before it
answers, and a deleted one keeps its stale announcement (the app's tombstone hides it).
