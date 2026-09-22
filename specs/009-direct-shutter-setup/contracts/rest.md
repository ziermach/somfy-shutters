# Contract: REST — setting up shutters directly

Conventions as in features 001–008: JSON, German `message`, errors `{ "error", "message",
"detail" }`. **Every route here requires the `configure` ability** (feature 008); the gate
records each successful call as a `shutter_setup` change entry, and every `program` is
additionally recorded with its outcome.

## `GET /api/setup`

```json
{ "management": { "available": true, "reason": null, "patched": true } }
```

`reason` when unavailable: `not_configured` (no `bridge.manage_url`) | `unreachable` |
`refused`. `patched`: whether the last `add` was announced live (null before any).

## `POST /api/setup/shutters` — create in the bridge (US1)

```json
{ "name": "Kinderzimmer", "travel_seconds": 20 }
```

**201**

```json
{ "id": "kinderzimmer", "address": "0x279625", "name": "Kinderzimmer",
  "pairing": "unpaired", "announced": true }
```

`announced` false: the bridge is unpatched; the client shows "Pi-Somfy einmal neu starten" before
pairing. **409 `name_taken`** (checked before the bridge is asked), **422** name 1–40 / seconds
1–600, **503 `management_unavailable`**, **502 `bridge_refused`** with the bridge's message in
`detail`.

## `POST /api/setup/shutters/{id}/program` — "PROG senden"

No body. **200** `{ "attempt": 2 }` — the bridge accepted one programming request. It says
nothing about the motor: RTS is one-way. **409 `busy`** (a request for this shutter is in
flight), **409 `already_paired`** (after "Hat gewackelt", unless `?intent=unpair`), **404**,
**503** / **502** as above.

`?intent=unpair` is used by removal's "Motor soll die Funkbrücke vergessen" (US3).

## `POST /api/setup/shutters/{id}/paired` — "Hat gewackelt"

**200** — the shutter as in feature 001's `GET /api/shutters/{id}`; it is now in the household
(snapshot to every client). **409 `not_programmed`** when no `program` was sent in this session.

## `DELETE /api/setup/shutters/{id}` — "Löschen" of an unpaired shutter

Deletes it in the bridge, row → `deleted`. **200** `{ "deleted": "kinderzimmer" }`.

## Removal with the bridge (US3) — extends `DELETE /api/shutters/{id}`

`DELETE /api/shutters/{id}?bridge=true` — deletes in the bridge first, then feature 005's
cascade; row → `deleted`.

**200** `{ "removed": "bad", "bridge": "deleted" }`.
**502 `bridge_refused`** / **503 `management_unavailable`**: nothing was removed;
`detail: { "done": ["unpaired"], "failed": "bridge_delete" }` lists what already happened, so the
client can offer "erneut versuchen" or "nur aus der App entfernen" (plain `DELETE` = feature 005).

`GET /api/shutters/{id}/removal` gains `"bridge_managed": true|false`.

## Renaming (US4) — extends `PATCH /api/shutters/{id}`

For a bridge shutter with management available, the bridge's name follows (research §8). A
bridge failure does not undo the app's rename: **200** with `"bridge_renamed": false` and a
message.

## `GET /api/roster` — additions

`"unpaired": [{ "id", "name", "address" }]`, `"management": { … as GET /api/setup }`.

## WebSocket

Unchanged frames. Pairing confirmed → `snapshot` to everyone (the household changed); create,
delete → `roster` frame.

## Simulator only

| Endpoint | Plays |
|---|---|
| `POST /api/sim/window/{address}/learn` | a person holding PROG on the old remote, or a clean power-cycle: the motor learns for 120 s |
| `POST /api/sim/bridge/patched {"patched": bool}` | a bridge with or without the `deploy/` patch |
| `GET /api/sim/bridge/programs` | every programming request the simulated bridge transmitted |
| `POST /api/sim/bridge/manage {"available": bool}` | a bridge whose management access fails (US5) |
