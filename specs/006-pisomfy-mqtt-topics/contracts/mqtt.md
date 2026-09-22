# Contract: MQTT — the whole integration surface (current Pi-Somfy)

> **Superseded in part** by [feature 005's contract](../../005-shutter-add-remove/contracts/mqtt.md):
> the discovery topic `homeassistant/cover/+/config`, excluded here, is now subscribed to.

Supersedes [feature 001's contract](../../001-mqtt-live-position/contracts/mqtt.md), whose
`level/cmd` / `level/set_state` topics no longer exist in Pi-Somfy since v3.1. Everything in
this file is known only to `backend/src/somfy_shutters/bridge/mqtt.py`; nothing above the
port speaks topics (constitution, principle II).

`<id>` is the shutter's radio address as the bridge spells it in its topics — see
"Identity" below.

## Outbound — what we publish

| Port call | Topic | Payload |
|---|---|---|
| `send_level(address, 100)` | `somfy/<id>/command` | `OPEN` |
| `send_level(address, 0)` | `somfy/<id>/command` | `CLOSE` |
| `send_level(address, n)`, 0 < n < 100 | `somfy/<id>/set_position` | `n` as a decimal integer |
| `send_stop(address)` | `somfy/<id>/command` | `STOP` |

- QoS 0, not retained. A command is for now; a retained command would replay on the next
  bridge restart and move a shutter nobody asked to move.
- **Never** a `set_position` to stop. The bridge ignores a position equal to its own belief,
  so that would let the shutter run on.
- Publishing raises `BridgeUnreachable` when the broker is not connected **or** the bridge
  has not announced itself `online`. Nothing is queued.

## Inbound — what we subscribe to

| Topic | Payload | Becomes |
|---|---|---|
| `somfy/+/position` | integer 0–100 | `Report(kind="position", percent=n, retained=…)` |
| `somfy/+/state` | `opening` \| `closing` \| `open` \| `closed` \| `stopped` | `Report(kind="movement", state=…, retained=…)` |
| `somfy/bridge/availability` | `online` \| `offline` | availability; not a report |

- `retained` is the MQTT retain flag of the *received* message. By the MQTT 3.1.1 rules a
  broker sets it only for messages delivered from its store at subscription time, and clears
  it when forwarding a live publish — so it means exactly "old news".
- Malformed payloads (non-numeric position, out of range, unknown state word) are logged
  and dropped. A topic with the wrong shape is ignored silently.
- `homeassistant/#` is not subscribed here (feature 005).
- Reports for an `<id>` that matches no configured address are passed up; the tracker drops
  them and logs once per address, as before.

## Availability

`connected` (what feature 001 calls "bridge reachable") is

```
broker connected  AND  last payload on somfy/bridge/availability == "online"
```

Before any availability payload has arrived, the bridge is not reachable. The bridge sets
`offline` as its MQTT last will, so a crashed bridge is announced by the broker.

## Identity

The bridge builds topics from the key in its `[Shutters]` config section, typed by a person
(`0x279621`, `0X279621`, …). Our config normalises addresses to lower case.

- Inbound: the `<id>` segment is compared case-insensitively with configured addresses.
- Outbound: the adapter publishes with the spelling it last received for that address on
  any inbound topic; before anything was received, with the configured address.

## Direction

The bridge declares `position_open: 100`, `position_closed: 0` — the same convention as the
whole app. No translation happens anywhere. `bridge.invert_level` in `shutters.toml` is
accepted for compatibility, ignored, and logged once as a warning when true.

## What is deliberately absent

No programming (`PROG`), no creating or deleting shutters: the bridge offers those only in
its own web interface, which this project must not operate. Feature 005 guides a person
through them.
