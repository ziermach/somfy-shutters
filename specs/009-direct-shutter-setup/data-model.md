# Data model: Setting up shutters directly in the app

Builds on [feature 005's data model](../005-shutter-add-remove/data-model.md).

## `household_shutter` (existing table, three changes)

| Field | Type | Rules |
|---|---|---|
| `state` | text | `active` \| `set_aside` \| **`deleted`** — `deleted` is a tombstone: removed from the bridge by the app; never "new" again until the address is announced **live** |
| `pairing` | text, **new** | `paired` \| `unpaired`; default `paired` (every row from feature 005 was paired in the bridge's interface) |
| `estimate_seconds` | real, **new**, nullable | the travel time typed at creation, 1–600; null for rows from feature 005 |

Unchanged: `id` (slug, fixed), `address` (from the bridge, lower-case, unique), `name` (1–40,
trimmed, unique among household shutters), timestamps.

Migration: `ALTER TABLE … ADD COLUMN` for both, with defaults; `state` has no CHECK change in
SQLite, so the new value is validated in code (as `set_state` already does).

### Which rows are in `settings.shutter`

`state = 'active' AND pairing = 'paired'` — as before, plus the pairing condition. An `unpaired`
row is in the household table but not in the household: no overview card, no "all", no group,
no rule (FR-011).

### State transitions

```text
                 add (bridge assigns address)
                          │
                          ▼
            active + unpaired ──"Löschen"──► (bridge delete) ► deleted
                          │
               "Hat gewackelt"
                          ▼
             active + paired ──remove, bridge too──► deleted
                          │
                  remove, app only (feature 005)
                          ▼
                     set_aside ──restore──► row gone → "new"
deleted ──live announcement of the address──► row gone → "new"
```

## Setup session (in memory, `setup.py`)

| Field | Meaning |
|---|---|
| `address` | the shutter this session created or resumed |
| `attempts` | "PROG senden" presses so far |
| `in_flight` | a program request is running (a second press is refused) |
| `announced` | a live announcement arrived after `add` (the bridge is patched) |

Keyed by address; lost on restart without harm — the `unpaired` row is what makes a flow
resumable ("Anlernen fortsetzen").

## Bridge shutter record (the bridge's, read through `getConfig`)

`{address: {name, duration}}`. Never stored by the app; read to probe management access and to
find the bridge's current name before a rename.

## Travel-time precedence (feature 002, extended)

hand-written in `shutters.toml` > measured > **`estimate_seconds`** > `general.default_travel_seconds`.
The source label for the new layer is `estimate` ("geschätzt beim Anlegen").

## Frontend

`Roster.active[]` entries gain `pairing`; `Roster` gains `unpaired: [{id, name, address}]` and
`management: {available, reason}`. The power-cycle windows and step logic live in
`lib/setup.ts` as data.
