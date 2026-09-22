# Data model: Adding and removing shutters

## `household_shutter` (new table, existing SQLite database)

| Field | Type | Rules |
|---|---|---|
| `id` | text, PK | slug of the confirmed name, `^[a-z0-9_-]+$`, unique across config and table; never changes |
| `address` | text, unique | lower-case, as parsed from the announcement |
| `name` | text | 1–40 chars, trimmed, unique among household shutters |
| `state` | text | `active` \| `set_aside` |
| `created_at`, `updated_at` | text | UTC |

Shutters from `shutters.toml` are **not** stored here; the file stays the only record of them.
An address in both the file and the table is a conflict resolved in the file's favour at
start (the table row is ignored and logged).

## Announcement (in memory, from MQTT) — `bridge/base.py`

| Field | Type |
|---|---|
| `address` | str, lower-case |
| `name` | str \| None (None = withdrawn) |
| `web_url` | str \| None |
| `retained` | bool |

Delivered through the existing `reports()` stream as a third report kind, `announcement`, so
the pump in `main.py` stays single.

## Roster state (in memory) — `roster.py`

| Structure | Meaning |
|---|---|
| `announced: dict[address, Announcement]` | latest announcement per address |
| `live_since_online: set[address]` | announced live since the bridge's last `online` |
| `forgotten: set[shutter_id]` | active bridge shutters missing after the last window |
| `window_ends: float \| None` | end of the 30 s window after `online` |

Derived:

- **new** = announced addresses − active addresses − set-aside addresses
- **forgotten** = decided when the window ends: active `origin=bridge` shutters whose address
  is not in `live_since_online`; cleared per shutter by any later live announcement

## `settings.shutter` (existing list, now mutated at runtime)

Built at start from `shutters.toml` + active `household_shutter` rows (with no travel times —
feature 002's calibration or the default applies). Confirming appends; removing deletes.
Every existing reader (`settings.shutters`, `settings.by_address`) sees the change.

## Removal cascade

| Thing | Action |
|---|---|
| `settings.shutter` | entry removed |
| tracker | position, movement, bridge counter, external-moving flag dropped |
| `shutter_state` row (feature 001 store) | deleted |
| calibration (feature 002) | values and runs cleared |
| groups (feature 004) | membership pruned; a group left empty stays, says so |
| automation rules (003/004) | shutter removed from `targets.shutters`; a rule left without targets reports `no_targets` |
| firing history | kept (it names the shutter id; history is per rule) |
| `household_shutter` | `set_aside` if still announced, else deleted |

## Frontend

`Shutter` gains `forgotten: boolean`, `origin: 'config' | 'bridge'`. A `roster` store holds the
`GET /api/roster` result for the management screen and the guide.
