# Contract: MQTT — managing shutters in the bridge

Extends [feature 006's contract](../../006-pisomfy-mqtt-topics/contracts/mqtt.md) and
[feature 005's](../../005-shutter-add-remove/contracts/mqtt.md). Known only to
`backend/src/somfy_shutters/bridge/mqtt.py` (app side) and `mqtt.py` in the Pi-Somfy fork
(bridge side). Driving and state are unchanged.

## Topics

| Topic | Direction | Retained | Payload |
|---|---|---|---|
| `somfy/bridge/manage/request` | app → bridge | no | one JSON request |
| `somfy/bridge/manage/response` | bridge → app | no | one JSON response |

QoS 1 both ways. Responses must not be retained: a retained answer would be replayed to the
next client that subscribes and read as a fresh result.

## Request

```json
{ "request_id": "3f7a…", "op": "add", "name": "Kinderzimmer", "duration": 20 }
```

- `request_id`: 32 hex characters, generated per request by the app.
- `op` and its fields:

| `op` | Fields | Effect in the bridge |
|---|---|---|
| `add` | `name`, `duration` (seconds, 1–600) | creates the shutter, assigns the next free address, rolling code 1, subscribes and announces it |
| `program` | `address` | transmits one RTS PROG frame for that shutter |
| `rename` | `address`, `name`, `duration` | renames / re-times, re-announces |
| `delete` | `address` | removes it, unsubscribes, clears its announcement |

## Response

```json
{ "request_id": "3f7a…", "status": "ok", "address": "0x279625" }
```

```json
{ "request_id": "3f7a…", "status": "error", "error": "name_taken",
  "message": "Name is not unique" }
```

- `address` is returned by `add` only, lower-case, `^0x[0-9a-f]{6}$`. The app validates it and
  never computes an address itself; anything else is treated as an error.
- `error`: `name_taken` | `bad_name` | `bad_duration` | `unknown_shutter` | `failed`.
- **Idempotency**: the bridge keeps the last 32 `request_id`s with their responses. A repeat
  (QoS 1 may deliver twice) is answered from that store and **not** acted on again — vital for
  `program`, where a second frame would undo a pairing.

## Timing and absence

- The app waits 5 s for the matching `request_id`. Nothing → `management_unavailable`
  (an upstream bridge never answers), cached until the bridge's availability changes.
- A timeout on `program` is reported as "unklar, ob gesendet"; the app does **not** repeat it.
- After `add`, the shutter's announcement (`homeassistant/cover/…/config`, feature 005) arrives
  live within the same second; it, not the response, is what makes the shutter commandable.

## What the bridge fork changes (upstreamable in this order)

1. `announceShutter(id)` / `withdrawShutter(id)`, called from add, rename and delete — so a
   shutter added through *any* interface works without a bridge restart.
2. The management channel above, handlers reusing the existing add/edit/delete/program code.
3. `sendMQTT(topic, msg, retain=True)` gains the flag, for non-retained responses.
4. The Pi 5 detection fix, currently `deploy/pi-somfy-pi5-detection.patch`.
