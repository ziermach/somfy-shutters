# Contract: REST and WebSocket — adding and removing shutters

Conventions as in features 001–004: JSON, German `message`, errors as
`{ "error", "message", "detail" }`, no authentication (home network is the trust boundary).

## `GET /api/roster`

Everything the management screen needs (FR-019).

```json
{
  "active": [
    { "id": "wohnzimmer", "name": "Wohnzimmer", "address": "0x279621",
      "origin": "config", "forgotten": false, "removable": false },
    { "id": "gaestezimmer", "name": "Gästezimmer", "address": "0x279625",
      "origin": "bridge", "forgotten": false, "removable": true }
  ],
  "new": [ { "address": "0x279626", "bridge_name": "Bad" } ],
  "set_aside": [ { "address": "0x279627", "name": "Alte Küche" } ],
  "bridge": { "announcements_seen": true, "web_url": "http://pi-somfy.local:80/" }
}
```

- `origin`: `config` (from `shutters.toml`, not removable in the app) or `bridge`.
- `announcements_seen` false means the bridge has never announced anything — likely
  announcements are switched off in the bridge; the guide says so.
- `web_url` from the bridge's announcements or `bridge.web_url` in config, else `null`.

## `POST /api/roster/new/{address}` — confirm a new shutter

```json
{ "name": "Bad" }
```

**201** — the shutter as in feature 001's `GET /api/shutters/{id}`, with its new `id`.
Name 1–40 characters, trimmed; a name already used gets a numeric suffix in the prefilled
suggestion, but a duplicate submitted name is **409 `name_taken`**. **404 `not_announced`**
when the address is not currently new.

## `PATCH /api/shutters/{id}` — rename

`{ "name": "Badezimmer" }` → the shutter. The id never changes. **409 `name_taken`**.
Hand-configured shutters: **409 `configured_by_hand`** (the name lives in `shutters.toml`).

## `GET /api/shutters/{id}/removal` — what removal would do

```json
{
  "removable": true,
  "groups": [ { "id": "g_1", "name": "Erdgeschoss" } ],
  "rules": [ { "id": "r_2", "name": "Abends zu", "left_without_target": false } ],
  "calibrated": true,
  "still_announced": true,
  "reason": null
}
```

`removable` false with `reason`: `configured_by_hand` | `measurement_in_progress`.

## `DELETE /api/shutters/{id}` — remove

**200** `{ "removed": "gaestezimmer", "set_aside": true }` — `set_aside` true when the bridge
still announces it (FR-016). Sends nothing to the bridge (FR-015). **409** with the reasons
above; **404** unknown.

## `POST /api/roster/set-aside/{address}/restore`

Puts a set-aside shutter back as **new**, to be confirmed again with a name. **404** unknown.

## WebSocket

- `snapshot` — **may now arrive at any time**, not only on connect: after every roster change
  the server sends a fresh snapshot to every client (research §9). Clients already replace
  all state on a snapshot.
- `roster` — `{ "type": "roster", "new": 1, "forgotten": ["kueche"] }`, sent whenever the new or
  forgotten sets change; the management screen re-fetches `GET /api/roster`, and the
  overview shows a "Neuer Rolladen gefunden" hint when `new > 0` (spec US2 scenario 5).
- Each shutter in snapshots gains `"forgotten": bool` and `"origin": "config" | "bridge"`.

## Commands to a forgotten shutter

`POST /api/shutters/{id}/command` → **409 `forgotten`**, "Die Funkbrücke kennt diesen Rolladen
nicht mehr." Automations record `skipped` with reason `forgotten`.

## Simulator only (`bridge.kind = "sim"`)

| Endpoint | Models |
|---|---|
| `POST /api/sim/bridge/shutters {"name"}` | a person adds a shutter in the bridge: next free address, **not announced until a restart** |
| `DELETE /api/sim/bridge/shutters/{address}` | a person deletes it in the bridge: the retained announcement stays |
| `POST /api/sim/bridge/restart` | the bridge restarts: offline, online, every current shutter announced live |
