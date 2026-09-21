# Phase 1 Data Model: Live position and movement

**Date**: 2026-09-21 · **Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Three places hold data, and the split matters:

| Where | Holds | Why there |
|---|---|---|
| `config/shutters.toml` | which shutters exist, addresses, travel times | Physical facts a human measured and may correct. Constitution: measured values in configuration, never code |
| SQLite | last known position, confidence, when it was last certain | Survives a restart, changes constantly, nobody edits by hand |
| Memory | movements in flight, client connections | Meaningless after a restart, by design |

---

## Configuration: `shutters.toml`

```toml
[general]
stale_after_hours = 12        # FR-008: when an estimate is de-emphasised
default_travel_seconds = 20   # FR-015: used where nothing was measured

[bridge]
kind = "mqtt"                 # or "sim" — the only switch between real and simulated
host = "localhost"
port = 1883
# user / password when the broker requires them

[[shutter]]
id = "wohnzimmer"             # stable key, used in URLs and storage
name = "Wohnzimmer"           # what the user reads
address = "0x279621"          # RTS address, from operateShutters.conf, copied by hand
travel_up_seconds = 18.2      # optional; absent means not measured
travel_down_seconds = 16.1
```

**Validation** (fails startup loudly — a wrong address is silent otherwise):

- `id` unique, lowercase, `[a-z0-9_-]`
- `address` matches `0x[0-9a-f]{6}`, unique across shutters
- travel times, when present, between 1 and 600 seconds
- at least one shutter, or the app has nothing to do

**On duplication**: the address is written here *and* in Pi-Somfy's
`operateShutters.conf`. That is deliberate — see [research.md §5](./research.md).
`shutters.toml` must never be committed; the example file is.

---

## Entity: Shutter

Configuration plus current state, joined at runtime. This is what the API returns.

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable key |
| `name` | string | display |
| `address` | string | RTS address; never shown prominently in the UI |
| `travel_up_seconds` | float \| null | null means not measured |
| `travel_down_seconds` | float \| null | null means not measured |
| `calibrated` | bool | derived: both travel times present |
| `position` | PositionEstimate | below |
| `movement` | Movement \| null | present only while travelling |

`travel_seconds(direction)` returns the configured value, or
`general.default_travel_seconds` when absent. **FR-015**: a shutter with no measurement
still animates, and `calibrated: false` is what the UI marks.

---

## Entity: PositionEstimate

The heart of Principle III. A bare number is not representable — serialising a position
without its confidence is impossible by construction.

| Field | Type | Notes |
|---|---|---|
| `percent` | int 0–100 \| null | null only when `confidence` is `unknown` |
| `confidence` | `certain` \| `estimated` \| `unknown` | FR-006 |
| `certain_at` | timestamp \| null | when it last became certain; drives the age shown (FR-007) |
| `source` | `command` \| `report` \| `restored` | where this value came from |

`100` is fully open, `0` fully closed, throughout the system. Whatever Pi-Somfy expects
is translated in exactly one place, the MQTT adapter — see
[contracts/mqtt.md](./contracts/mqtt.md).

### Confidence transitions

```text
unknown ──command reaches an end stop──▶ certain
estimated ──command reaches an end stop──▶ certain
estimated ──report says 0 or 100 while idle──▶ certain
certain ──any movement away from the end stop──▶ estimated
estimated ──certain_at older than stale_after_hours──▶ estimated (stale flag set)
any ──restart while travelling──▶ unknown        (FR-010)
certain ──restart──▶ certain                     (an end stop survives a reboot)
estimated ──restart──▶ estimated, age preserved
```

`stale` is not a fourth confidence value — it is `estimated` with an old `certain_at`,
computed on read. Storing it would mean keeping a clock in the database.

---

## Entity: Movement

In memory only. A movement that was interrupted by a restart is exactly the case
FR-010 wants reported as `unknown`, so persisting it would defeat the point.

| Field | Type | Notes |
|---|---|---|
| `shutter_id` | string | |
| `from_percent` | int | where it started |
| `target_percent` | int | 0, 100, or an intermediate |
| `direction` | `up` \| `down` | |
| `started_at` | monotonic timestamp | not wall clock — immune to time jumps (edge case) |
| `expected_arrival` | monotonic timestamp | `started_at + travel × distance` |
| `origin` | `local` \| `external` | `external` = inferred from a report stream |

The interpolation is linear between `started_at` and `expected_arrival`. The mock's
explainer shows this lands within roughly 9 pp mid-travel even with measured times,
because the real motor does not move linearly. That is accepted here; modelling the
curve belongs with the feature that measures it.

---

## Entity: Command

Not persisted in this feature. A history table is easy to add later and nothing here
needs it.

| Field | Type | Notes |
|---|---|---|
| `shutter_id` | string | |
| `action` | `open` \| `close` \| `stop` \| `position` | |
| `target_percent` | int \| null | required for `position` |
| `issued_at` | timestamp | |
| `accepted` | bool | false when the bridge was unreachable (FR-021) |

---

## Storage schema

```sql
CREATE TABLE shutter_state (
    shutter_id  TEXT PRIMARY KEY,
    percent     INTEGER,             -- NULL when unknown
    confidence  TEXT NOT NULL,       -- certain | estimated | unknown
    certain_at  TEXT,                -- ISO 8601 UTC, NULL if never
    source      TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

One row per shutter, written on every settled change — not during travel, which would
be a write every frame for no benefit. Rows for shutters no longer in the config are
left alone; they cost nothing and come back if the shutter does.

**On startup**: every row loads, and any shutter that was mid-travel cannot be
distinguished from one that settled — so the writer records the settled state only, and
a shutter interrupted mid-travel simply never got its write. Its last row is the
position it left from, which is now wrong. Therefore the tracker marks a shutter
`unknown` on load when `updated_at` is older than `certain_at` is allowed to be *and* the
stored confidence was `estimated` with a movement flag. Simpler and safer: a
`was_moving` boolean is written when a movement starts and cleared when it settles.

```sql
ALTER TABLE shutter_state ADD COLUMN was_moving INTEGER NOT NULL DEFAULT 0;
```

On load, `was_moving = 1` → confidence becomes `unknown`. That is one extra write per
movement and makes FR-010 exact rather than inferred.

---

## Derived values the API exposes

| Value | Derivation |
|---|---|
| `stale` | `confidence == estimated` and `now − certain_at > stale_after_hours` |
| `age_seconds` | `now − certain_at`, null when never certain |
| `calibrated` | both travel times configured |
| `eta_seconds` | while moving: `expected_arrival − now` |

None are stored. All are computed on read, so no background job has to keep them
honest.
