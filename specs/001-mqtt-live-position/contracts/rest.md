# Contract: REST — commands and queries

Base path `/api`. JSON in, JSON out. No authentication: the home network is the trust
boundary (spec Assumptions).

The shared shape of a shutter is defined once here and reused by
[websocket.md](./websocket.md).

## `GET /api/shutters`

Everything the UI needs to draw itself. Also the recovery path for a client that would
rather re-fetch than reconnect.

```json
{
  "shutters": [
    {
      "id": "wohnzimmer",
      "name": "Wohnzimmer",
      "calibrated": true,
      "travel_up_seconds": 18.2,
      "travel_down_seconds": 16.1,
      "position": {
        "percent": 62,
        "confidence": "estimated",
        "certain_at": "2026-09-21T06:45:12Z",
        "age_seconds": 7512,
        "stale": false,
        "source": "command"
      },
      "movement": null,
      "measuring": false
    },
    {
      "id": "schlafzimmer",
      "name": "Schlafzimmer",
      "calibrated": false,
      "travel_up_seconds": null,
      "travel_down_seconds": null,
      "position": {
        "percent": null,
        "confidence": "unknown",
        "certain_at": null,
        "age_seconds": null,
        "stale": false,
        "source": "restored"
      },
      "movement": null,
      "measuring": false
    }
  ],
  "bridge": { "connected": true, "kind": "mqtt" }
}
```

While a shutter travels, `movement` is present:

```json
"movement": {
  "from_percent": 100,
  "target_percent": 0,
  "direction": "down",
  "started_at": "2026-09-21T18:03:11.412Z",
  "expected_arrival": "2026-09-21T18:03:27.512Z",
  "origin": "local",
  "curve_a": 1.0
}
```

The client animates from `started_at` to `expected_arrival` on its own clock.
`curve_a` is the travel shape (feature 002; `1.0` is linear): the motor runs linearly
in the bridge's level, `level = 100·(p/100)^(1/a)`, so the client interpolates there and
converts back with `p = 100·(level/100)^a` — the same way the server does, so a stop
mid-travel settles where the animation already is. It does
**not** poll for intermediate positions — that is the whole point of FR-012.

## `POST /api/shutters/{id}/command`

```json
{ "action": "open" }
{ "action": "close" }
{ "action": "stop" }
{ "action": "position", "target_percent": 30 }
```

**200** — accepted for delivery, with the movement that resulted:

```json
{ "accepted": true, "movement": { "...": "as above" } }
```

`movement` is `null` for a `stop`, or when the shutter is already at the requested
position (a no-op, still 200).

**404** — unknown shutter (FR-004).

**422** — malformed: unknown action, `target_percent` missing or outside 0–100.

**503** — the bridge is unreachable (FR-021):

```json
{
  "accepted": false,
  "error": "bridge_unreachable",
  "message": "Der Befehl konnte nicht zugestellt werden. Die Funkbrücke antwortet nicht."
}
```

Nothing is queued and no animation starts. Saying "it did not happen" beats a shutter
closing twenty minutes late.

## `POST /api/shutters/command`

Same body, applied to every shutter (FR-002). Each is commanded independently and one
failure does not stop the rest:

```json
{
  "results": [
    { "id": "wohnzimmer", "accepted": true },
    { "id": "kueche", "accepted": false, "error": "bridge_unreachable" }
  ]
}
```

**207** when results are mixed, **200** when all succeeded, **503** when all failed.

## `POST /api/shutters/{id}/resync`

FR-009. Drives to the nearest end stop for the sole purpose of making the position
certain again. Which end stop is chosen is stated in the response so the UI can say
what will happen before it happens.

```json
{ "accepted": true, "target_percent": 100, "movement": { "...": "" } }
```

When the position is `unknown`, the nearest end stop cannot be computed; the server
picks **open** and says so. Response shape is identical.

## `GET /api/health`

```json
{ "status": "ok", "bridge": { "connected": true, "kind": "mqtt" }, "shutters": 4 }
```

`status` is `ok` even when the bridge is down — the service is up and correctly
reporting a broken dependency. Conflating the two would make the health check useless
for telling them apart.

## Error shape

Every error body uses the same three fields, so the client has one code path:

```json
{ "error": "machine_readable_code", "message": "Was der Nutzer lesen soll.", "detail": null }
```

`message` is German, because it is shown to the user. `error` is the stable identifier
tests assert on.
