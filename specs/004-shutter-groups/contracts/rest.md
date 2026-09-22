# REST contract: Shutter groups

All errors use the shared shape `{"error", "message", "detail"}`; messages are German
and shown to the user as they are.

## Group object

```json
{ "id": "g_7Qm2", "name": "Obergeschoss", "members": ["schlafzimmer", "bad", "kind"] }
```

## `GET /api/groups`

`200` → `{"groups": [Group, ...]}` in overview order.

## `POST /api/groups`

Body: `{"name": "Obergeschoss", "members": ["schlafzimmer", "bad"]}`

| Status | When |
|---|---|
| `201` | created; body is the Group, appended at the end of the order |
| `409 name_taken` | another group has the same name ignoring case and whitespace; `detail.group_id` |
| `422 invalid_group` | name empty/too long, no members, duplicate member; `detail.field`, `detail.problem` |
| `422 unknown_shutter` | a member is not configured; `detail.shutters` |

Publishes `groups` (see websocket.md).

## `PUT /api/groups/{id}`

Same body and errors as `POST`, plus `404 unknown_group`. Replaces name and members
(members in the given order). `200` → Group. Publishes `groups`.

## `DELETE /api/groups/{id}`

`204`, or `404 unknown_group`. Removes the group from every rule's targets (FR-026).
Publishes `groups`, and `rules_changed` if any rule changed.

## `PUT /api/groups/order`

Body: `{"ids": ["g_1", "g_2", ...]}` — every existing group id exactly once.

`200` → `{"groups": [...]}`; `422 invalid_order` if the list is not a permutation of
the current ids (e.g. a group was created or deleted meanwhile — the client re-fetches).
Publishes `groups`.

## `POST /api/groups/{id}/command`

Body: same as `POST /api/shutters/{id}/command` — `{"action": "open"|"close"|"stop"|"position", "target_percent": 0-100|null}`.

Commands every member through `commands.apply_many`, in configuration order.

| Status | When |
|---|---|
| `200` | every member accepted |
| `207` | some accepted, some not |
| `503` | none accepted (typically `bridge_unreachable`) |
| `404 unknown_group` | |
| `409 empty_group` | the group has no members (FR-020) |
| `422 target_required` | `position` without `target_percent` |

Body for 200/207/503:

```json
{
  "results": [
    { "id": "schlafzimmer", "accepted": true, "movement": { "...": "as for one shutter" } },
    { "id": "bad", "accepted": false, "error": "measurement_in_progress" }
  ]
}
```

`movement` is included for accepted open/close/position so the client animates from
the response at once, exactly as the single-shutter route does. `stop` returns
`movement: null`.

## `POST /api/shutters/command` (changed)

Unchanged status codes and shape; now implemented via `commands.apply_many`, and
accepted results carry `movement` as above. `position` requires `target_percent`
(`422 target_required`) — previously an unchecked assertion.

## Automations (changed, feature 003)

### Rule `targets`

Request and response:

```json
"targets": "all"
"targets": { "shutters": ["buero"], "groups": ["g_7Qm2"] }
```

- At least one entry across both lists; no duplicates within a list.
- A plain list of shutter ids is still **accepted** on input, as `{"shutters": list, "groups": []}`.
  Responses always use the object.
- `422 unknown_group` with `detail.groups` for an id that does not exist.

### Conflicts (`POST /api/automations`, `PUT`, `/preview`)

Each conflict gains `via`: the group name through which the *shared* shutter is reached
in the rule being saved, or `null` if it is targeted directly or by `"all"`.

```json
{ "rule_id": "r_9", "rule_name": "Abends zu", "shutter_id": "bad", "via": "Obergeschoss",
  "first_at": "2026-09-23T19:12:00+02:00", "winner": "r_9" }
```

### Firing history

Each outcome gains `via: [group name, ...]` (empty when direct).
