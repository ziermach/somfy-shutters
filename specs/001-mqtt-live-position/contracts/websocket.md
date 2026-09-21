# Contract: WebSocket — the state push

`GET /api/ws`, upgraded. One-directional in practice: the server pushes, the client
sends nothing but protocol-level pongs. Commands go over [REST](./rest.md).

Clients never connect to MQTT (FR-019). This socket is the only way state reaches a
browser.

## On connect: a full snapshot, always

The first frame after every connect is the complete state — identical in shape to
`GET /api/shutters`:

```json
{ "type": "snapshot", "seq": 1041, "data": { "shutters": [ "..." ], "bridge": { "...": "" } } }
```

This satisfies FR-020 and removes a whole class of bug: there is no resume-from-offset,
no missed-message detection, no replay buffer. A client that reconnects after five
minutes or five hours is in the same position as one connecting for the first time.

`seq` increments on every frame the server sends. A client that sees a gap knows it
missed something and can reconnect for a fresh snapshot, but does not have to — the
next snapshot repairs everything anyway.

## Frames the server sends

### `movement` — a shutter started travelling

```json
{
  "type": "movement",
  "seq": 1042,
  "shutter_id": "wohnzimmer",
  "movement": {
    "from_percent": 100,
    "target_percent": 0,
    "direction": "down",
    "started_at": "2026-09-21T18:03:11.412Z",
    "expected_arrival": "2026-09-21T18:03:27.512Z",
    "origin": "local"
  }
}
```

Sent to **every** client including the one that issued the command, so all of them
animate from the same timestamps (FR-018, SC-003). The commanding client does not wait
for it — it animates optimistically on its own REST response — but it does accept this
frame as the authoritative timing.

`origin: "external"` means the movement was inferred from Pi-Somfy reports, i.e.
somebody used a physical remote.

### `position` — a shutter settled

```json
{
  "type": "position",
  "seq": 1043,
  "shutter_id": "wohnzimmer",
  "position": {
    "percent": 0,
    "confidence": "certain",
    "certain_at": "2026-09-21T18:03:27.512Z",
    "age_seconds": 0,
    "stale": false,
    "source": "command"
  }
}
```

Sent when a movement ends, is stopped, or when a report changes the stored value. Ends
any animation for that shutter.

### `correction` — the estimate moved without a movement

FR-017. A report disagreed with the local estimate while idle, and the report won.

```json
{
  "type": "correction",
  "seq": 1044,
  "shutter_id": "buero",
  "position": { "percent": 48, "confidence": "estimated", "certain_at": "...", "source": "report" },
  "ease_ms": 400
}
```

`ease_ms` tells the client to glide rather than jump. The value is already corrected in
the model; the easing is presentation only. A separate frame type rather than a plain
`position` because the client renders it differently, and because it is worth being able
to count corrections when judging whether the travel times are any good.

### `bridge` — the connection to Pi-Somfy changed

```json
{ "type": "bridge", "seq": 1045, "connected": false, "kind": "mqtt" }
```

Drives the "Funkbrücke nicht erreichbar" banner (FR-021). Sent on every transition, not
periodically.

## Heartbeat and reconnect

- The server sends a WebSocket ping every 20 s. A client that misses two treats the
  connection as dead.
- The client reconnects with backoff: 1 s, 2 s, 4 s, 8 s, capped at 30 s, with jitter
  (FR-023).
- While disconnected the UI marks positions as not current (FR-022) — it does not hide
  them, and it does not keep animating.
- On reconnect the snapshot arrives and replaces everything. SC-006 measures this:
  full state within 5 s of the connection returning.

## What this contract deliberately lacks

**No per-frame position updates during travel.** The server sends `movement` once, with
start and expected arrival; the client interpolates locally at 60 fps. Streaming
positions would multiply traffic by a hundred, add jitter on Wi-Fi, and make the
animation worse than computing it locally — and it would violate the constitution's
rule that animation must not wait on the bridge.

**No client→server messages.** Anything the client wants to cause is a REST call. If a
later feature needs a live drag, this is where it would be added.
