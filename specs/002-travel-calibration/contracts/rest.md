# Contract: calibration endpoints

Extends [feature 001's REST surface](../../001-mqtt-live-position/contracts/rest.md);
same error shape, same base path.

## `GET /api/calibration`

One row per shutter, both directions, for the overview screen.

```json
{
  "shutters": [
    {
      "id": "wohnzimmer",
      "name": "Wohnzimmer",
      "state": "calibrated",
      "up":   { "travel_seconds": 18.12, "dead_seconds": 0.74, "runs": 3,
                "curve_k": 0.2, "source": "measured", "updated_at": "2026-09-21T19:14:02Z" },
      "down": { "travel_seconds": 16.04, "dead_seconds": 0.69, "runs": 3,
                "curve_k": 0.2, "source": "measured", "updated_at": "2026-09-21T19:16:41Z" }
    }
  ]
}
```

`state` is `calibrated`, `partial` (one direction), `uncalibrated`, or `manual` (a
person typed it). `source` says which configuration layer the number came from, so the
interface can explain why a measurement did not take effect.

## `POST /api/calibration/{id}/run`

Starts a guided run. The direction is not a parameter — it follows from where the
shutter rests, so runs alternate on their own (FR-006).

**200**

```json
{ "direction": "down", "from_percent": 100, "run_id": 41 }
```

**409** `not_at_end_stop` — the position is not at an end stop (FR-002). The body
carries `suggested_target`, the end stop a non-measured drive would go to.

**409** `already_running` — a run is in progress for this shutter.

**503** `bridge_unreachable`.

## `POST /api/calibration/{id}/home`

The non-measured drive to an end stop (FR-003). Same shape as a command response;
explicitly not recorded as a measurement.

## `POST /api/calibration/{id}/mark`

The two presses. The server timestamps on arrival of the request rather than trusting a
client clock.

```json
{ "mark": "moving" }
{ "mark": "arrived" }
```

**200** after `moving`: `{ "phase": "timing", "dead_seconds": 0.74 }`

**200** after `arrived`: the finished run, with its verdict.

```json
{
  "run": { "id": 41, "direction": "down", "dead_seconds": 0.74,
           "total_seconds": 16.04, "rejected": null },
  "calibration": { "travel_seconds": 16.04, "dead_seconds": 0.69, "runs": 3 },
  "next_direction": "up"
}
```

A rejected run comes back with the same shape and `rejected` set to a reason —
**200, not an error**. The run happened; it just does not count, and the interface
shows it struck through.

**409** `no_run` — nothing in progress.

## `DELETE /api/calibration/{id}/run`

Aborts. The shutter is left where it is, so its position is no longer at an end stop
and feature 001's confidence handling takes over (FR-008).

## `DELETE /api/calibration/{id}`

Discards every measurement for a shutter (FR-016). It reverts to the default and is
marked uncalibrated. Manual values in `shutters.toml` are untouched — the app does not
edit that file.

## `POST /api/calibration/{id}/check`

Starts verification: drives to the displayed midpoint (FR-023).

```json
{ "accepted": true, "target_percent": 50, "movement": { "...": "" } }
```

**409** `not_calibrated` — nothing to verify yet.

## `POST /api/calibration/{id}/check/answer`

```json
{ "answer": "too_high" }
```

**200** `{ "curve_k": 0.3, "shift_pp": 1.6, "at_limit": false }`

`at_limit` is true once the bound is reached, so the interface can stop offering more
of something that will not move.

## `DELETE /api/calibration/{id}/check`

Undoes every verification answer (FR-026): `curve_k` returns to 0, measurements stay.

## WebSocket

One new frame, on the channel from
[feature 001](../../001-mqtt-live-position/contracts/websocket.md):

```json
{ "type": "calibration", "seq": 1102, "shutter_id": "wohnzimmer",
  "direction": "down", "travel_seconds": 16.04, "runs": 3 }
```

Sent when a stored value changes, so other open clients stop animating with the old
timing (FR-017).
