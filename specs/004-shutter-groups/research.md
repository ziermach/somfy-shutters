# Research: Shutter groups

Decisions taken while planning feature 004, each with what was weighed against it.

## 1. Groups live in the app database, not in `shutters.toml`

**Decision**: two new tables in the existing SQLite database, managed over REST.

**Rationale**: FR-007 says groups are managed in the app. The household changes them
(a new "Südseite" in summer) far more often than the hardware, and `shutters.toml` is a
hand-edited, gitignored file of measured values — mixing the household's vocabulary
into it would mean editing a config file on the Pi to rename a room.

**Alternatives considered**: a `[[group]]` block in `shutters.toml` (rejected: violates
FR-007, needs a restart per change); seeding groups from config once, as `[location]`
does (rejected as scope: nobody asked for it, and it adds a "which one wins" rule).

## 2. RTS group channels are not used

**Decision**: a group command is N individual commands, one per member, through
`commands.apply`.

**Rationale**: an RTS group means pairing one extra remote channel to several motors at
the windows — physical work per group, a second kind of address in
`operateShutters.conf`, and Pi-Somfy would move several motors on one frame while the
app could no longer tell which ones it reached. Per-member commands reuse the one
command path (measurement lock, travel curve, animation, estimate) unchanged and keep
group membership editable without a ladder. Constitution I and II are untouched.

**Alternatives considered**: RTS group channel per group (rejected above); a group
channel only for "all" (rejected: same pairing cost, no benefit the "Alle zu" loop
does not already give).

## 3. One helper for commanding many shutters

**Decision**: `commands.apply_many(state, ids, action, percent)` returns one result per
shutter (`commanded` / `measurement_in_progress` / `bridge_unreachable`). The existing
"Alle auf/zu" route, the new group route and the automation engine all call it.

**Rationale**: today the loop-and-catch exists twice (`api/rest.py::command_all` and
`automation/engine.py::_command`). A third copy for groups is where the three would
start to disagree about what a partial failure is. The helper does not change
`apply`; it only owns the loop and the exception mapping.

**Alternatives considered**: a third copy in a group route (rejected: drift); making the
engine call the REST route (rejected: layering backwards).

## 4. Command order and pacing

**Decision**: members are commanded sequentially, in **configuration order**, with no
added delay. A group of 12 is expected to be fully handed to the bridge well within the
5 s of FR-021.

**Rationale**: `bridge.send_level` is an MQTT publish; Pi-Somfy serialises
transmission on its side. Configuration order is what feature 003 firings already use,
so a rule targeting a group commands its shutters in the same order as a rule listing
them — no second ordering rule to explain. Member order is a display choice only.

**Alternatives considered**: member order (rejected: two orders, and a rule reaching one
shutter through two groups would need a tie-break); concurrent `gather` (rejected: the
radio is serial anyway, and concurrency would make the order — and so the animation
start times — nondeterministic).

**Open on hardware**: whether Pi-Somfy drops or merges commands published back-to-back.
"Alle zu" already does this for 4 shutters in the simulator only. A hardware task
verifies it with a real group; if frames are lost, a small configurable inter-command
gap (`bridge.command_gap_ms`, default 0) is the fallback, recorded in config as a
measured value.

## 5. How a rule names groups

**Decision**: `targets` becomes `"all"` or `{"shutters": [...], "groups": [...]}`. Stored
rows written by feature 003 (`"all"` or a plain list) are read as
`{"shutters": list, "groups": []}`. Group targets are resolved at firing time;
membership is taken at that instant (FR-023). The union is deduplicated (FR-024).

**Rationale**: an explicit object keeps "all" distinct from "a group that happens to hold
every shutter" (spec edge case). Reading the old shape in place avoids a migration step
on the Pi. The API always returns the new shape, so the frontend has one case.

**Alternatives considered**: prefixed ids in one list (`"group:abc"`) — rejected, a
shutter id could in principle start with `group:` and every consumer would parse
strings; a migration that rewrites rows — rejected as unnecessary, reading both is four
lines.

## 6. Deleting a group that rules target

**Decision**: the delete route removes the group, then removes its id from every rule's
`targets` (FR-026) and publishes `rules_changed`. Independently, the engine ignores
group ids it cannot resolve, so a crash between the two steps leaves a rule that
behaves correctly and is tidied on the next delete or edit.

**Rationale**: the two stores use separate connections to the same file; a cross-store
transaction would couple them for one rare operation. Tolerant resolution makes the
non-atomic sequence safe.

## 7. Where "via" is recorded in firing history

**Decision**: `Outcome` gains `via: list[str]` — the **names** of the groups a shutter was
reached through at firing time, empty for a direct target or `"all"`.

**Rationale**: FR-027. Names, not ids, because history must stay readable after a group
is renamed or deleted; the record describes what happened then. Old rows without `via`
read as empty.

## 8. Shutters leaving the configuration

**Decision**: on startup, memberships whose shutter id is not configured are deleted.

**Rationale**: FR-009 says a removed shutter drops out and a newly added one starts in no
group. Filtering on read alone would let a shutter that is removed and later re-added
with the same id silently rejoin its old groups. Pruning at startup — the only moment
the configuration can change — is exact.

## 9. Group summary wording and confidence

**Decision**: a pure function `summarize(members, now)` in `frontend/src/lib/groups.ts`
buckets each member as moving / open (100) / closed (0) / between / unknown, using the
same live percent the cards show, and returns a phrase plus the **lowest** tone of any
member (`sure` < `estimated` < `unsure`, from `lib/confidence.ts`).

- All in one bucket → one word: "offen", "zu", "fährt", "Position unbekannt".
- Otherwise counts, most informative first: "2 von 3 offen · 1 fährt".
- Never an average percent (FR-013): an average of 0 and 100 is 50, which no window is.

**Rationale**: Constitution III — the summary is derived, so it can be no more confident
than its least confident member (FR-013, SC-006). Keeping it pure makes it table-testable.

## 10. View preference per device

**Decision**: grouped/flat and the set of collapsed groups are kept in `localStorage`,
every access wrapped in try/catch; without storage the defaults apply (grouped if any
group exists, nothing collapsed).

**Rationale**: FR-014 wants it per device and it is a convenience, not shared state —
the one place in the app where browser storage is the right tool.

## 11. Reordering on a phone without a drag library

**Decision**: up/down buttons in the group editor (members) and the group list (groups).
Order is persisted as an explicit `position` column, rewritten in full on each reorder.

**Rationale**: no new frontend dependency (Constitution V); drag-and-drop on touch
screens is fiddly and needs a library to be done well. With ≤ 15 groups, buttons are fast
enough (SC-001 is about creating, not sorting).
