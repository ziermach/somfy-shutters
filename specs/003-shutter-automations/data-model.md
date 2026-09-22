# Data model: Shutter automations

Three new tables in the existing SQLite database (`config/state.db`), created with
`CREATE TABLE IF NOT EXISTS` like features 001 and 002. Times are stored as UTC ISO
strings; wall-clock values (a rule's time of day, bounds) as `HH:MM` local.

## Rule — `automation_rule`

| Field | Type | Rules |
|---|---|---|
| `id` | text, PK | generated, URL-safe |
| `name` | text | 1–60 characters, trimmed |
| `enabled` | bool | |
| `days` | int | bitmask, bit 0 = Monday … bit 6 = Sunday; 0 allowed (never fires, FR-007 edge case) |
| `trigger_kind` | text | `time` \| `sunrise` \| `sunset` |
| `time_of_day` | text, nullable | `HH:MM`; required for `time`, null otherwise |
| `offset_minutes` | int | −360…360; must be 0 for `time` |
| `not_before` | text, nullable | `HH:MM`; sun triggers only |
| `not_after` | text, nullable | `HH:MM`; sun triggers only; if both set, `not_before` < `not_after` |
| `targets` | text (JSON) | `"all"` or a non-empty list of shutter ids |
| `action_kind` | text | `open` \| `close` \| `position` |
| `action_percent` | int, nullable | 0–100, required for `position` only |
| `skip_planned_at` | text, nullable | UTC instant of the one firing to skip (FR-025) |
| `created_at` | text | UTC; with `id`, the tie-break for FR-011 |
| `updated_at` | text | UTC |

- Target ids are **not** validated against the configuration on read: a shutter removed
  from `shutters.toml` stays in the list and is reported as removed when the rule fires
  (spec edge case). On save, unknown ids are rejected — you cannot add a shutter that
  does not exist.
- `"all"` resolves at firing time (FR-004).
- Changing a rule clears `skip_planned_at` if that instant is no longer a planned firing.

### Derived, never stored

- **next firing** — `planner.next_firing(rule, now, location, tz)`: an instant, or a
  reason it has none: `disabled`, `no_days`, `no_targets` (every target removed),
  `no_location` (sun rule, no location set).
- **today's sun time** for the form's preview.

## Firing — `automation_firing`

One row per planned firing that the engine dealt with, however it dealt with it.

| Field | Type | Rules |
|---|---|---|
| `id` | int, PK | |
| `rule_id` | text, FK → rule, `ON DELETE CASCADE` | |
| `planned_at` | text | UTC instant from the planner |
| `fired_at` | text, nullable | when commands went out; null unless status is `fired`/`partial`/`failed` |
| `status` | text | see below |
| `outcomes` | text (JSON) | list of `{shutter_id, result, reason}`; empty for statuses that sent nothing |
| | | `UNIQUE(rule_id, planned_at)` — the dedupe (research §1) |

### Status

| Status | Meaning | Commands sent |
|---|---|---|
| `fired` | every target commanded | yes |
| `partial` | some commanded, some skipped or failed | yes |
| `failed` | none could be commanded (bridge down, all under measurement) | attempted |
| `skipped` | "skip next" was set for this instant | no |
| `paused` | automations were paused | no |
| `held` | the clock was unreliable (research §5) | no |
| `missed` | the system was not running, and came back too late (FR-012) | no |
| `no_sun` | the sun did not rise or set that day | no |

### Per-shutter outcome

| `result` | `reason` |
|---|---|
| `commanded` | null |
| `skipped` | `measurement_in_progress` \| `removed` |
| `failed` | `bridge_unreachable` |

A firing is written with its status **before** commands go out (`fired` provisional,
outcomes empty) and updated with the outcomes after, so a crash in between can never
lead to the same firing twice.

Retention: rows with `planned_at` older than 90 days are deleted daily.

## Settings — `app_setting`

Key–value, value as JSON. Small, and not worth a table each.

| Key | Value |
|---|---|
| `location` | `{latitude: -90…90, longitude: -180…180}`, or absent |
| `automation.pause` | `{until: UTC instant \| null}` — null means until resumed; absent means not paused |
| `automation.heartbeat` | UTC instant, written every 60 s while the clock is reliable |

A pause whose `until` has passed is treated as absent and deleted on the next check.

## Configuration additions — `shutters.toml`

```toml
[general]
timezone = "Europe/Berlin"   # zoneinfo name; the wall clock rules follow

[location]                    # optional; seeds the database on first start only
latitude = 52.52
longitude = 13.40
```

Once the location has been set in the app, the file is not consulted for it again. The
app is where people will change it, so the app's value wins — the opposite of travel
times in feature 002, where a hand-written value is a deliberate override.

## Relationships

```
automation_rule 1 ──< automation_firing       (cascade on delete)
automation_rule >──< shutter (config)          by id, resolved at firing time
app_setting.location ── used by planner for sun triggers
```
