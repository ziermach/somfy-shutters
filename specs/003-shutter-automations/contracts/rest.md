# Contract: REST — automations

Base path `/api`. Same conventions as
[feature 001](../../001-mqtt-live-position/contracts/rest.md): JSON in and out, no
authentication (home network is the trust boundary), every error body is
`{ "error", "message", "detail" }` with a German `message`.

## The rule, on the wire

```json
{
  "id": "r_4k2f",
  "name": "Abends zu",
  "enabled": true,
  "days": [true, true, true, true, true, true, true],
  "trigger": { "kind": "sunset", "offset_minutes": -30, "not_before": null, "not_after": "21:00" },
  "targets": "all",
  "action": { "kind": "close" },
  "skip_next": false,
  "next": { "at": "2026-09-22T17:12:00+02:00", "reason": null },
  "last": { "planned_at": "2026-09-21T17:14:00+02:00", "status": "partial", "commanded": 3, "total": 4 },
  "created_at": "2026-09-22T09:30:11Z"
}
```

- `days` is Monday first.
- `trigger` is one of
  `{ "kind": "time", "time": "06:45" }` or
  `{ "kind": "sunrise" | "sunset", "offset_minutes": -360…360, "not_before": "HH:MM" | null, "not_after": "HH:MM" | null }`.
- `targets` is `"all"` or a list of shutter ids.
- `action` is `{ "kind": "open" }`, `{ "kind": "close" }` or
  `{ "kind": "position", "percent": 0…100 }`.
- `next.at` is local time with offset, so a client can print it as is; `null` with a
  `reason` of `disabled` | `no_days` | `no_targets` | `no_location` when it will not fire.
- `last` is the most recent firing record, or `null`.
- Times in responses are local with offset; times in requests are `HH:MM` wall clock.

## `GET /api/automations`

Everything the automations screen needs.

```json
{
  "rules": [ "…rule…" ],
  "pause": { "paused": true, "until": "2026-09-29T00:00:00+02:00" },
  "clock": { "reliable": true, "reason": null },
  "location": { "latitude": 52.52, "longitude": 13.40, "sunrise": "07:01", "sunset": "19:08" }
}
```

- Rules in FR-011 order: by next firing, then creation.
- `pause.until` is `null` for "until resumed"; `{ "paused": false, "until": null }` when
  not paused.
- `clock.reason` is `not_synchronised` | `went_backwards` when `reliable` is false.
- `location` is `null` until set; `sunrise`/`sunset` are today's, local.

## `POST /api/automations/preview`

The form's live preview. Takes a rule body as for create (plus optional `id` when
editing, so a rule does not conflict with itself) and saves nothing.

```json
{
  "next": { "at": "2026-09-22T17:12:00+02:00", "reason": null },
  "today": "17:12",
  "conflicts": [
    { "rule_id": "r_9x", "rule_name": "Kino", "shutter_id": "wohnzimmer",
      "first_at": "2026-06-18T21:00:00+02:00", "winner": "r_9x" }
  ]
}
```

`today` is the concrete time this trigger resolves to today, for "heute 17:12" in the
form, even if today is not a selected day. `winner` is the rule carried out last in the
same minute (FR-011, FR-022).

## `POST /api/automations`

Create. Body: a rule without `id`, `next`, `last`, `created_at`, `skip_next`.

**201** — the stored rule, plus `"conflicts": [ … ]` as in preview. Conflicts are a
warning; the rule is saved regardless.

**422** — invalid: unknown shutter id, empty target list, `position` without `percent`,
offset out of range, bounds on a time trigger, `not_before` ≥ `not_after`.

**409** `no_location` — a sun trigger while no location is set (FR-016).

## `PUT /api/automations/{id}`

Replace. Same body and responses as create; **404** for an unknown id.

## `PATCH /api/automations/{id}`

Only `{ "enabled": bool }` or `{ "skip_next": bool }`. Returns the rule.

- `skip_next: true` marks the rule's current next firing to be skipped (FR-025); the
  response's `next` still shows that instant, with `skip_next: true`.
- `skip_next: true` on a rule with no next firing: **409** `nothing_to_skip`.

## `DELETE /api/automations/{id}`

**204**. Deletes its firing records too.

## `GET /api/automations/{id}/firings?limit=50`

Newest first, up to 90 days (FR-021).

```json
{
  "firings": [
    {
      "planned_at": "2026-09-21T17:14:00+02:00",
      "fired_at": "2026-09-21T17:14:01+02:00",
      "status": "partial",
      "outcomes": [
        { "shutter_id": "wohnzimmer", "result": "commanded", "reason": null },
        { "shutter_id": "schlafzimmer", "result": "skipped", "reason": "measurement_in_progress" }
      ]
    },
    { "planned_at": "2026-09-20T17:16:00+02:00", "fired_at": null, "status": "held", "outcomes": [] }
  ]
}
```

Statuses and reasons: [data-model.md](../data-model.md#status).

## `PUT /api/automations/pause`

`{ "until": "2026-09-29T00:00" }` (local, minute precision) or `{ "until": null }` for
"until resumed". **422** for a time in the past. Returns the `pause` object.

## `DELETE /api/automations/pause`

Resume. Returns `{ "paused": false, "until": null }`.

## `GET /api/location`, `PUT /api/location`

`{ "latitude": 52.52, "longitude": 13.40 }`; the response adds today's `sunrise` and
`sunset`. **422** outside −90…90 / −180…180.

## Simulator only

Registered only when `bridge.kind = "sim"`, like feature 001's `/api/sim/*`.

- `POST /api/sim/clock` `{ "reliable": false }` — force the clock guard's verdict, to
  exercise FR-013 without pulling a network cable. `{ "reliable": null }` returns to the
  real check.
