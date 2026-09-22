# Feature Specification: Shutter groups

**Feature Branch**: `worktree-004-shutter-groups` (designed in a separate worktree, merged to `main`)

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Rollläden gruppieren: Der Nutzer kann mehrere Rollläden zu einer Gruppe zusammenfassen, z.B. alle Rollläden in einem Raum (Wohnzimmer, Schlafzimmer, Obergeschoss). Eine Gruppe lässt sich als Ganzes bedienen (öffnen, schließen, auf Position fahren) und als Ziel in Automationen verwenden. Die Oberfläche zeigt Rollläden nach Gruppe geordnet."

## User Scenarios & Testing *(mandatory)*

Features 001–003 treat every shutter on its own: the overview is one flat list, and a
rule names shutters one by one or says "all shutters". A house does not think that
way. The living room has two windows and a terrace door that always move together;
upstairs closes before anyone goes to bed; the south side comes down on hot
afternoons. This feature lets the household say so once, by name, and then use that
name everywhere.

Groups are the household's own words for sets of shutters. They are deliberately
free-form: a shutter can belong to "Wohnzimmer", "Erdgeschoss" and "Südseite" at the
same time. A group owns nothing and changes nothing about its shutters — it is a
label and a shortcut. The motors still report nothing, so a group's state is only
ever the sum of its members' estimates, and is shown as such.

### User Story 1 - Name a set of shutters (Priority: P1)

Someone creates a group called "Wohnzimmer" and picks the three shutters in that
room. They create "Obergeschoss" with the four shutters upstairs, and "Südseite"
with the living-room window and both bedroom windows — some shutters are in two
groups, which is fine. They can rename a group, change its members, change the order
of groups, and delete a group without touching any shutter.

**Why this priority**: Nothing else in this feature exists without groups to act on.
On its own it already gives the overview structure (story 2 builds on it directly).

**Independent Test**: Create three groups, two of which share a shutter; restart the
system; confirm all three groups are still there with the same members and order.
Delete one and confirm its shutters are unaffected and still in the other groups.

**Acceptance Scenarios**:

1. **Given** four configured shutters, **When** a user creates a group "Wohnzimmer"
   with two of them, **Then** the group exists with exactly those two members.
2. **Given** a shutter already in "Wohnzimmer", **When** the user adds it to
   "Südseite", **Then** it is a member of both.
3. **Given** a group "Wohnzimmer" exists, **When** a user tries to create another
   group named "wohnzimmer", **Then** the app refuses and says the name is taken.
4. **Given** a group, **When** the user deletes it, **Then** its shutters remain
   configured, controllable, and members of any other groups.
5. **Given** groups were created, **When** the system restarts, **Then** every group,
   its members and the order of groups are unchanged.

---

### User Story 2 - See the house by group (Priority: P1)

Someone opens the app and sees the shutters sorted under their groups, in the order
the household chose, each group with a short summary of where its shutters are — "all
open", "all closed", "2 of 3 open", "moving". A shutter in two groups appears under
both, and moving it animates in both places at once. Shutters in no group are listed
under their own heading, so none disappears. Someone who prefers the old flat list
can switch to it.

**Why this priority**: This is the change people see every time they open the app,
and it is what makes a house with a dozen windows usable on a phone. It needs no
group commands to be valuable.

**Independent Test**: With groups set up, open the overview; confirm each group lists
its members, a shared shutter appears in both groups, an ungrouped shutter appears
under "Ohne Gruppe", and moving a shared shutter animates in every place it is shown.

**Acceptance Scenarios**:

1. **Given** groups exist, **When** the overview opens, **Then** shutters are shown
   under each group they belong to, groups in the chosen order, members in the
   group's chosen order.
2. **Given** a shutter in no group, **When** the overview opens, **Then** it appears
   in a section for ungrouped shutters, after all groups.
3. **Given** a shutter in two groups, **When** it moves, **Then** both places show
   the same animation and the same position estimate at the same moment.
4. **Given** a group whose members are at different positions, **When** it is shown,
   **Then** its summary states how many members are open, closed, in between,
   moving or of unknown position, and never shows a single position as if the group were one shutter.
5. **Given** any member's position is an estimate of reduced confidence, **When** the
   group summary is shown, **Then** the summary says so too — it is never more
   confident than its least confident member.
6. **Given** no groups exist, **When** the overview opens, **Then** it looks as it did
   before this feature, with a hint that groups can be created.
7. **Given** the user switches to the flat list, **When** they reopen the app on the
   same device, **Then** it is still the flat list.

---

### User Story 3 - Move a whole group (Priority: P2)

Someone taps "close" on "Obergeschoss" and all four upstairs shutters go down. They
can open, close, stop, or send the group to a position — the same actions a single
shutter offers. If one member cannot be commanded (it is being calibrated, or the
radio bridge is unreachable), the others still move and the person is told which one
did not and why.

**Why this priority**: The most frequent reason people ask for groups, but it depends
on groups existing (story 1). A household with groups and the grouped overview can
already tap members one by one.

**Independent Test**: Close a group of three; confirm all three are commanded and
animate. Start a calibration on one member and close the group again; confirm the
other two move and the app names the skipped one with the reason.

**Acceptance Scenarios**:

1. **Given** a group of three open shutters, **When** the user taps "close" on the
   group, **Then** all three are commanded to close and every open client shows each
   of them travelling from the moment its own command was sent.
2. **Given** a group, **When** the user sends it to 30 %, **Then** every member is
   commanded to 30 % and each is shown as an estimate, never as confirmed.
3. **Given** a group is moving, **When** the user taps "stop" on the group, **Then**
   every member is commanded to stop.
4. **Given** one member is being calibrated, **When** the group is commanded, **Then**
   the other members are commanded, and the user sees that one member was skipped
   and why.
5. **Given** the radio bridge is unreachable, **When** a group is commanded, **Then**
   no member is shown as moving, and the user sees that the command failed.
6. **Given** a group with no members, **When** it is shown, **Then** its commands are
   unavailable and the group says it is empty.

---

### User Story 4 - Automate a group (Priority: P2)

Someone edits the evening rule and, instead of ticking six shutters, picks the groups
"Erdgeschoss" and "Obergeschoss". Later they buy a new shutter for the guest room and
add it to "Obergeschoss" — the evening rule now closes it too, without anyone editing
the rule.

**Why this priority**: Makes rules survive changes to the house, but automations
already work with individually picked shutters, so this is an improvement rather
than a missing capability.

**Independent Test**: Create a rule targeting one group, fire it, confirm exactly the
group's members move. Add a shutter to the group, fire again, confirm the new member
moves too. Delete the group and confirm the rule says it has no shutters left.

**Acceptance Scenarios**:

1. **Given** a rule targeting group "Obergeschoss", **When** it fires, **Then** every
   shutter that is a member of "Obergeschoss" at that moment is commanded.
2. **Given** a rule targeting two groups that share a shutter, **When** it fires,
   **Then** the shared shutter is commanded once.
3. **Given** a rule targeting a group and, separately, one shutter, **When** it
   fires, **Then** the group's members and that shutter are commanded, each once.
4. **Given** a rule's only target is a group that is then deleted, **When** the user
   looks at the rule, **Then** it says it has no shutters left and will not fire.
5. **Given** a rule targeting a group, **When** the automations screen shows it,
   **Then** the group is shown by name, and the user can see which shutters it
   currently means.
6. **Given** two rules fire in the same minute on the same shutter with different
   actions — one through a group, one directly — **When** the second is saved,
   **Then** the conflict warning from feature 003 appears as it would for two direct
   targets.

---

### Edge Cases

- **A shutter is removed from the configuration.** It drops out of every group. A group
  left with no members stays, says it is empty, and can be refilled or deleted.
- **A shutter is added to the configuration.** It is in no group until someone puts it
  in one; it appears under ungrouped shutters.
- **A group is renamed.** Rules that target it keep targeting it and show the new name.
- **A group contains every shutter.** Allowed. It is still a group and is not the same
  as "all shutters": a shutter added to the configuration later does not join it.
- **A group command while members are already moving.** Each member is commanded as if
  it had been tapped individually; the newest command wins, as for a single shutter.
- **A member is commanded individually right after a group command.** The individual
  command wins for that member; the rest of the group continues.
- **Many members at once.** The radio can only send one command at a time, so members
  start moving one after another, not at the same instant. Each member's animation
  starts when its own command is sent, never before.
- **A group command is interrupted by the bridge going away mid-way.** Members already
  commanded keep moving and are shown as such; the rest are reported as failed.
  Nothing is retried or queued.
- **Two people edit groups at the same time from different phones.** The last save
  wins; every client shows the saved result within a moment.
- **A group change creates a new conflict.** Adding a shutter to a group can make two
  enabled rules command it in the same minute, differently, although neither rule was
  edited. Saving the group then shows the same warning as saving a rule would, naming
  both rules and which wins. It is a warning, not a refusal: the group is saved.
- **A group with one member.** Allowed; it behaves exactly like that shutter.
- **The same shutter added to a group twice.** Impossible — membership is a set.

## Requirements *(mandatory)*

### Functional Requirements

**Groups**

- **FR-001**: Users MUST be able to create a group with a name and one or more member
  shutters, chosen from the configured shutters.
- **FR-002**: A shutter MAY be a member of any number of groups, including none.
- **FR-003**: Group names MUST be non-empty, at most 40 characters, and unique ignoring
  case and surrounding whitespace.
- **FR-004**: Users MUST be able to rename a group, add and remove members, reorder the
  members within a group, reorder the groups, and delete a group.
- **FR-005**: Deleting a group MUST NOT change any shutter, any other group, or any
  shutter's position, calibration or history.
- **FR-006**: Groups, their members and both orders MUST survive restarts unchanged.
- **FR-007**: Groups MUST be managed in the app. They MUST NOT require editing a
  configuration file.
- **FR-008**: Groups MUST be shared by everyone using the app on the home network, and
  a change MUST reach every open client without a reload.
- **FR-009**: A shutter removed from the configuration MUST drop out of every group; a
  shutter added to the configuration MUST start in no group.

**Overview**

- **FR-010**: The overview MUST show shutters under each group they belong to, in the
  household's chosen order, followed by a section for shutters in no group.
- **FR-011**: A shutter shown in several places MUST show the same state, animation and
  confidence in each at the same moment.
- **FR-012**: Each group MUST show a summary of its members: counts of open, closed,
  in-between, moving and unknown-position members, in that order, or a single word
  when all agree ("open", "closed", "moving", "position unknown").
- **FR-013**: A group summary MUST NOT present a combined position as confirmed, and
  MUST indicate reduced confidence when any member's estimate has reduced confidence.
- **FR-014**: Users MUST be able to switch between the grouped view and a flat list of
  all shutters; the choice MUST be remembered on that device.
- **FR-015**: Users MUST be able to collapse a group in the overview; collapsed groups
  still show their summary and commands.

**Group commands**

- **FR-016**: Users MUST be able to open, close, stop, or send to a position every member
  of a group with one action.
- **FR-017**: A group command MUST command each member through the same path as a
  manual command to that shutter, so it honours everything a manual command honours:
  refusal during calibration, refusal when the bridge is unreachable, animation from
  the moment of sending, and estimate display.
- **FR-018**: When some members cannot be commanded, the others MUST still be commanded,
  and the user MUST be told which members were not commanded and why.
- **FR-019**: A group command MUST NOT be retried or queued for members that could not be
  commanded.
- **FR-020**: A group with no members MUST offer no commands and MUST say it is empty.
- **FR-021**: All members of a group MUST have been commanded within 5 seconds of the
  user's action for a group of up to 12 shutters.

**Automations**

- **FR-022**: A rule's targets MUST be any combination of groups and individual shutters,
  or "all shutters" as before.
- **FR-023**: A group target MUST be resolved to its members at the moment the rule
  fires, so membership changes apply to existing rules without editing them.
- **FR-024**: A shutter reached through several targets of one rule MUST be commanded
  exactly once per firing.
- **FR-025**: The conflict warning of feature 003 MUST take group membership into
  account, using membership at the time of saving, and MUST name the group through
  which the shutter is reached.
- **FR-026**: A deleted group MUST be removed from every rule's targets; a rule left with
  no targets MUST behave as feature 003 prescribes for a rule with no shutters left.
- **FR-027**: The firing record MUST list outcomes per shutter, as in feature 003, and
  MUST show which group each shutter was reached through.
- **FR-028**: Saving a group MUST warn, without refusing, when the new membership creates
  a same-minute conflict between enabled rules that did not exist before, in the terms
  of FR-025.

### Key Entities

- **Group**: A named, ordered set of shutters defined by the household. Has a name, an
  ordered list of member shutters, and a place in the order of all groups. Owns no
  state of its own; its displayed state is derived from its members.
- **Membership**: The relation "shutter S is in group G". Many-to-many: a shutter can be
  in several groups, a group holds several shutters.
- **Rule target** (extended from feature 003): "all shutters", or a set of individual
  shutters and groups.
- **View preference**: Per device — grouped or flat, and which groups are collapsed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can create a group of three shutters in under 30 seconds on a
  phone, without reading any help.
- **SC-002**: Closing every shutter on one floor takes one tap instead of one per
  shutter.
- **SC-003**: FR-021's 5-second budget holds on the simulator, measured from the tap to
  the last member's command.
- **SC-004**: After a shutter is added to a group, the next firing of every rule that
  targets that group includes it, in 100 % of cases, with no rule edited.
- **SC-005**: Across a simulated month of firings with overlapping group targets, no
  shutter is ever commanded twice by one firing.
- **SC-006**: Nobody using the app ever sees a group's state presented as more certain
  than its least certain member.
- **SC-007**: With 20 shutters in 6 groups, a person finds a named shutter in the
  overview within 5 seconds.

## Assumptions

- Groups are purely an app concept. Each member is commanded individually through
  Pi-Somfy. RTS's own group channels (one remote channel paired to several motors)
  are not used: they would need re-pairing at the windows and a second kind of
  address, and the app could no longer tell the members apart.
- Commands to members are sent one after another, because the bridge transmits one
  frame at a time. A few hundred milliseconds between members is expected and
  acceptable; the animation reflects each member's own send time.
- Groups are flat. There is no nesting ("Obergeschoss contains Schlafzimmer"); a floor
  is simply a group whose members are that floor's shutters. The model was chosen
  over rooms-within-floors because the household wants overlapping groups such as
  "Südseite" as well.
- As in features 001–003, the home network is the trust boundary: no user accounts, no
  per-person groups. Only the view preference (grouped/flat, collapsed groups) is per
  device.
- Nothing is migrated: existing rules keep their individual shutters and "all shutters"
  targets unchanged. No groups exist until someone creates one.
- A reasonable household has at most around 30 shutters and 15 groups; the overview
  and the group commands are designed for that scale.
- Out of scope: groups defined in the configuration file, nested groups, icons or
  colours per group, and group-specific settings such as travel times — travel times
  stay per shutter.
- Nothing in this feature depends on open hardware questions: it only issues commands
  that features 001–003 already issue, just several at once.
