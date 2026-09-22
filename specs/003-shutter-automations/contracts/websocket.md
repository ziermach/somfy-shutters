# Contract: WebSocket — automations

New frames on the existing channel from
[feature 001](../../001-mqtt-live-position/contracts/websocket.md). The snapshot is
unchanged: automations have their own screen and fetch over REST, so a client that
never opens it pays nothing.

A rule firing needs **no** new frame to be visible: its commands produce the ordinary
`movement` frames, so every open client animates it like a button press (FR-009).

## `automations` — pause or clock state changed

```json
{ "type": "automations", "seq": 2210, "paused": true, "until": "2026-09-29T00:00:00+02:00",
  "clock_reliable": true }
```

Sent on every change of either, and once right after the snapshot on every connect, so
the overview's banner (FR-026) is right from the first frame. Clients show a banner
when `paused` or when `clock_reliable` is false.

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
