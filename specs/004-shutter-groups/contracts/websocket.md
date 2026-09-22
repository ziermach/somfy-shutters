# WebSocket contract: Shutter groups

Additions to `specs/001-mqtt-live-position/contracts/websocket.md` and feature 003's
frames. Clients never speak MQTT; this is the only push channel.

## Snapshot (changed)

`snapshot.data` gains `groups`: the same list `GET /api/groups` returns.

```json
{ "type": "snapshot", "seq": 1, "data": { "shutters": [], "bridge": {}, "automations": {},
  "groups": [ { "id": "g_7Qm2", "name": "Obergeschoss", "members": ["schlafzimmer", "bad"] } ] } }
```

## `groups` (new)

Sent after any create, update, delete or reorder, and after startup pruning changed
anything. Carries the full list — at most a few kB — so a client replaces its copy and
never merges.

```json
{ "type": "groups", "seq": 42, "groups": [ { "id": "...", "name": "...", "members": ["..."] } ] }
```

## Unchanged

Group commands produce ordinary `movement` / `position` frames per member. There is no
group-level movement frame: a group has no state of its own.
