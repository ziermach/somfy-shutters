# Implementation Plan: Shutter groups

**Branch**: `worktree-004-shutter-groups` (designed in a separate worktree, merged to `main`) | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-shutter-groups/spec.md`

## Summary

Free, overlapping, flat groups of shutters, managed in the app. A **group store** keeps
groups and ordered memberships in the existing SQLite database; a **group API**
creates, edits, orders, deletes and commands them and pushes the full list over the
WebSocket. Every group command goes through a new `commands.apply_many`, which the
existing "Alle auf/zu" route and the automation engine are moved onto, so all three
treat a partial failure the same way. Rule targets grow from `"all" | [ids]` to
`"all" | {shutters, groups}`, resolved at firing time, deduplicated, with the group
names recorded per outcome. The overview gains grouped sections with an honest
summary, collapse, and a per-device grouped/flat switch; the rule form gains group
chips.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript + Svelte 5 (frontend) — unchanged

**Primary Dependencies**: none new, backend or frontend.

**Storage**: the existing SQLite database; two new tables; one JSON shape extended in
place ([data-model.md](./data-model.md)).

**Testing**: pytest + pytest-asyncio (unit: store, resolution, apply_many; contract:
groups REST, changed automation REST; integration: quickstart A–D); vitest for
`lib/groups.ts` (summary, sectioning, view preference).

**Target Platform**: Raspberry Pi OS alongside Pi-Somfy; macOS for development.

**Project Type**: web application — `backend/` and `frontend/`, as in features 001–003.

**Performance Goals**: a group of 12 fully handed to the bridge within 5 s (FR-021,
SC-003); group list changes visible on other clients within one WebSocket round trip.

**Constraints**: offline; no new transmitter path; group state never more confident
than its least confident member; no queueing or retry for unreachable members.

**Scale/Scope**: ≤ 30 shutters, ≤ 15 groups per household.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. Pi-Somfy owns the radio** | A group is N calls to `commands.apply`, which publishes `level/cmd`. RTS group channels are deliberately not used (research §2): no pairing, no new frames. |
| **II. MQTT is the only integration boundary** | Unchanged. Nothing new talks to Pi-Somfy. |
| **III. Honest position state** | Groups hold no state; the summary is derived per member, never averaged, and takes the lowest member confidence (research §9, FR-013). Each member animates from its own send time. |
| **IV. Local-first operation** | Everything is local; no new service. |
| **V. Single-Pi simplicity** | No new dependency, no new process; two tables in the existing database. Reordering uses buttons, not a drag library (research §11). |
| **Stack table** | Unchanged. |
| **Command path verified on hardware** | `apply` is not changed. The loop around it is consolidated into `apply_many`; contract tests for "Alle auf/zu" and engine tests prove equivalence. Back-to-back commands to real motors are verified in quickstart E1 with the pending hardware bring-up. |
| **Measured values in config** | None introduced. The fallback inter-command gap (research §4), if bring-up needs it, is a measured value and goes in `[bridge]`. |

**Result**: pass, before and after design. No complexity to justify.

## Project Structure

### Documentation (this feature)

```text
specs/004-shutter-groups/
├── plan.md              # this file
├── research.md          # Phase 0 — decisions and why
├── data-model.md        # Phase 1 — tables, targets shape, outcome.via
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/
│   ├── rest.md          # /api/groups, changed automation targets and conflicts
│   └── websocket.md     # snapshot.groups, groups frame
└── tasks.md             # Phase 2 — /speckit-tasks
```

### Source Code

```text
backend/src/somfy_shutters/
├── groups.py                # NEW — Group, GroupDraft (Pydantic), GroupStore (tables, prune, order)
├── commands.py              # + apply_many(): the loop and exception mapping, shared
├── api/
│   ├── group_routes.py      # NEW — contracts/rest.md §groups
│   ├── rest.py              # command_all → apply_many; position needs target_percent
│   ├── automation_routes.py # targets validation (unknown_group), conflict via, preview
│   ├── serialize.py         # snapshot gains groups
│   └── ws.py                # "groups" frame passthrough
├── automation/
│   ├── models.py            # Targets model; Outcome.via; legacy list accepted
│   ├── store.py             # read legacy targets; drop_group(gid)
│   ├── engine.py            # targets(): resolve groups, dedupe, via; _command → apply_many
│   └── conflicts.py         # resolve through groups; report via
└── main.py                  # GroupStore wiring, prune at startup, groups in app.state

backend/tests/
├── unit/test_group_store.py          # uniqueness, order, cascade, prune
├── unit/test_apply_many.py           # partial, none, stop, order
├── unit/test_target_resolution.py    # all / groups / union / dedupe / via / unknown group / legacy
├── unit/test_conflicts.py            # + a group case
├── contract/test_groups_rest.py
├── contract/test_automation_rest.py  # + targets object, unknown_group, via
└── integration/test_groups_quickstart.py  # quickstart A–D

frontend/src/
├── lib/types.ts                 # Group, targets object, frames
├── lib/groups.ts                # summarize(), sections(), view preference (pure, tested)
├── lib/groups.test.ts
├── lib/groups.svelte.ts         # store: groups from snapshot/frames; CRUD; command()
├── lib/shutters.svelte.ts       # routes the snapshot's groups and the groups frame
├── components/GroupSection.svelte   # header: name, summary, collapse, auf/zu/stopp/position
├── routes/Overview.svelte       # grouped/flat switch, sections, ungrouped, hint
├── routes/Groups.svelte         # list, reorder, delete, "+ Neue Gruppe"
├── routes/GroupForm.svelte      # name, member chips, member order
├── routes/RuleForm.svelte       # group chips + shutter chips + "Alle"; resolved members line
├── components/RuleCard.svelte   # targets text with group names
├── components/FiringHistory.svelte  # "über <Gruppe>"
└── App.svelte                   # navigation to Groups
```

**Structure Decision**: the existing layout. Groups get a single backend module
(`groups.py`) rather than a package — model and store are small and have no
cooperating parts like the automation engine had.

## Design notes

- **apply_many.** `async def apply_many(state, ids, action, percent) -> list[Result]`
  iterates in the given order, calls `apply`, maps `MeasurementInProgress` and
  `BridgeUnreachable` to results, and keeps going. `UnknownShutter` cannot occur
  (callers pass configured ids) and is allowed to raise. Callers sort into
  configuration order before calling (research §4).
- **Status codes** for many-shutter routes stay those of "Alle auf/zu": 200 all, 207
  some, 503 none.
- **Resolution** lives in `AutomationEngine.targets(rule)` and returns
  `(resolved: list[(shutter_id, via_names)], removed: list[shutter_id])`. Conflicts use
  the same function with the draft, so the warning and the firing can never disagree
  about who is reached.
- **Group delete** → `group_store.delete(id)` → `automation_store.drop_group(id)` →
  `engine.reschedule()` → publish `groups`, then `rules_changed` if any rule changed.
- **Frontend state.** `groups.svelte.ts` holds `groups = $state<Group[]>`; the shutters
  store hands it the snapshot's `groups` and every `groups` frame. Sections are derived:
  `sections(groups, shutters)` → `[{group, members: Shutter[]}] + ungrouped`. Because a
  card reads the one shutter object from the shutters store, a shutter in two sections
  animates identically by construction (FR-011).
- **Group header** follows the card's visual language: name, summary line with the
  confidence tone colour, a chevron to collapse, and three buttons *auf / zu / stopp*
  with a *Position…* sheet reusing Detail's slider. Buttons are disabled with the same
  rules as "Alle auf/zu": bridge disconnected, or no member that the action would move.
  A 207 result shows a short inline notice naming the members not reached and why.
- **Rule form.** Target chips in three rows: *Alle*, then groups, then shutters. Picking
  *Alle* clears the rest. Below the chips, "Betrifft jetzt: Wohnzimmer, Küche, Bad" — the
  live resolution, so the user sees what a group currently means (US4 scenario 5).

## Complexity Tracking

None. The constitution check passes without exceptions.

## Risks

- **Back-to-back commands on real hardware.** Four is exercised today by "Alle zu" only in
  the simulator. If Pi-Somfy drops frames under a burst, a measured `command_gap_ms`
  goes into `[bridge]` (research §4); the 5 s budget allows ~400 ms per member for 12.
- **Duplicate cards and screen length.** Overlapping groups show a shutter several times;
  with many overlaps the page grows. Collapse (FR-015) and the flat list (FR-014) are the
  mitigations; if it still annoys, a spec change could hide duplicates.
- **Non-atomic group delete.** Covered by tolerant resolution (research §6).
- **Old clients during rollout.** A cached PWA from before feature 004 receives the new
  `targets` object and an unknown `groups` frame. The frame is ignored by the existing
  `switch`; the rule list would mis-render targets until the service worker updates,
  which the fix in `eb3f6b0` now does on the next load.
