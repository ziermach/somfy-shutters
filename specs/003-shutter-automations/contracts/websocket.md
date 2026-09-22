# Contract: WebSocket — automations

New frames on the existing channel from
[feature 001](../../001-mqtt-live-position/contracts/websocket.md), and one addition to
its snapshot. Rules themselves are fetched over REST by the automations screen, so a
client that never opens it pays nothing for them.

## Snapshot addition

```json
{ "type": "snapshot", "seq": 1, "data": { "shutters": [ "…" ], "bridge": { "…": "" },
  "automations": { "paused": false, "until": null, "clock_reliable": true, "clock_reason": null } } }
```

So the overview's banner (FR-026) is right from the first frame. An earlier draft sent
this as a separate frame right after the snapshot; that shifted the frame order every
existing client and test relies on, for no gain.

A rule firing needs **no** new frame to be visible: its commands produce the ordinary
`movement` frames, so every open client animates it like a button press (FR-009).

## `automations` — pause or clock state changed

```json
{ "type": "automations", "seq": 2210, "paused": true, "until": "2026-09-29T00:00:00+02:00",
  "clock_reliable": true, "clock_reason": null }
```

Sent on every change of either; same shape as the snapshot's `automations`. Clients
show a banner when `paused` or when `clock_reliable` is false (`clock_reason`:
`not_synchronised` | `went_backwards`).

## `automation_fired` — a firing was dealt with

```json
{ "type": "automation_fired", "seq": 2211, "rule_id": "r_4k2f", "rule_name": "Abends zu",
  "planned_at": "2026-09-22T17:12:00+02:00", "status": "partial", "commanded": 3, "total": 4 }
```

Sent for every firing record written, including `missed`, `held`, `paused` and
`skipped`. The automations screen uses it to refresh `last` and `next` without polling.

## `rules_changed` — a rule was created, edited, toggled or deleted

```json
{ "type": "rules_changed", "seq": 2212 }
```

No payload: a client showing the automations screen re-fetches `GET /api/automations`.
Rules change rarely and by hand; sending diffs would be code with nothing to gain.
