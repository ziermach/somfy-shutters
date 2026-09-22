# Data model: Shutter groups

Two new tables in the app's existing SQLite database, one changed JSON shape in
`automation_rule.targets`, one new field in firing outcomes. No migration step: new
tables are `CREATE TABLE IF NOT EXISTS`, old JSON shapes are read as they are.

## Tables

```sql
CREATE TABLE IF NOT EXISTS shutter_group (
    id          TEXT PRIMARY KEY,          -- random, url-safe; never shown
    name        TEXT NOT NULL,             -- as typed, trimmed
    name_key    TEXT NOT NULL UNIQUE,      -- NFC + casefold of name: FR-003 uniqueness
    position    INTEGER NOT NULL,          -- order of groups in the overview, 0-based
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shutter_group_member (
    group_id    TEXT NOT NULL REFERENCES shutter_group(id) ON DELETE CASCADE,
    shutter_id  TEXT NOT NULL,             -- config id from shutters.toml
    position    INTEGER NOT NULL,          -- order within the group, 0-based
    PRIMARY KEY (group_id, shutter_id)     -- membership is a set
);
```

`PRAGMA foreign_keys = ON` per connection, as the automation store already does.

## Entities

### Group

| Field | Type | Rules |
|---|---|---|
| `id` | string | server-assigned |
| `name` | string | 1–40 chars after trimming; unique by `name_key` (FR-003) |
| `members` | list of shutter ids | ≥ 1 on create and update (FR-001); each configured; no duplicates; order = display order |
| `position` | int | implicit: index in `GET /api/groups` |

A group can become empty only when its last member leaves the configuration
(research §8). An empty group is kept and shown as empty (FR-020); it can be edited or
deleted.

### Membership

Many-to-many between groups and configured shutters. Pruned at startup for ids no
longer configured (FR-009).

### Rule targets (changed, feature 003)

```text
targets := "all"
         | { "shutters": [shutter id, ...], "groups": [group id, ...] }   -- at least one entry total
```

Read compatibility: a stored plain list `["a", "b"]` is read as
`{"shutters": ["a", "b"], "groups": []}`. Written rows always use the object.

**Resolution at firing time** (`engine.targets(rule)`):

1. `"all"` → every configured shutter.
2. Otherwise the union of direct shutters and current members of each listed group
   that still exists; unknown group ids are ignored.
3. Deduplicated, in configuration order.
4. For each resolved shutter, `via` = names of the listed groups it is a member of.
5. Directly listed shutters no longer configured are reported `skipped / removed`, as
   in feature 003. Members of groups are always configured (pruned), so they never
   produce `removed`.

A rule whose resolution is empty has `next.reason = "no_targets"`, as in feature 003.

### Outcome (changed, feature 003)

| Field | Type | Change |
|---|---|---|
| `shutter_id` | string | — |
| `result` | `commanded` \| `skipped` \| `failed` | — |
| `reason` | as before | — |
| `via` | list of group names | **new**; empty for direct / `"all"`; missing in old rows → empty |

### Command result (new, shared)

Returned by `commands.apply_many` and, in JSON, by the "all" and group command routes:

| Field | Type |
|---|---|
| `id` | shutter id |
| `accepted` | bool |
| `error` | `measurement_in_progress` \| `bridge_unreachable` \| absent |

### View preference (frontend only, per device)

`localStorage["somfy.view"]` = `{"mode": "grouped" | "flat", "collapsed": [group id, ...]}`.
Unknown ids in `collapsed` are ignored. Missing or unreadable → grouped (when any
group exists), nothing collapsed.

## Derived state: group summary

Not stored. Computed in the client from members' live state (research §9):

| Bucket | Member condition |
|---|---|
| moving | `movement != null` |
| unknown | `position.percent == null` |
| open | percent 100 |
| closed | percent 0 |
| between | anything else |

Tone = lowest `tone()` of any member. The summary never carries a percent.
