# Feature Specification: Adding and removing shutters

**Feature Branch**: `main` (single-developer repository, no feature branches)

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Rolladen hinzufügen und entfernen"

## User Scenarios & Testing *(mandatory)*

Today a shutter exists in the app because somebody copied its radio address by hand from
the radio bridge's configuration into ours. That is error-prone — a mistyped address is
completely silent, because the radio never answers — and it means nobody without a
text editor can add a window.

Two facts bound what this feature can do:

- **The radio bridge owns the radio.** Only it may teach a motor a new sender ("anlernen")
  or create a new shutter with a new address. The app must not do either, and must not
  operate the bridge's own web pages on the person's behalf (constitution I and II). The
  person does those steps in the bridge's interface; the app guides them there and back.
- **The radio bridge announces its shutters.** Every shutter it knows is announced, with
  its name and identity, on the same message channel the app already listens to. So the
  app does not need anybody to copy anything: a shutter set up in the bridge simply
  appears.

This feature depends on the app speaking the radio bridge's current interface. The
bridge changed that interface in 2026; bringing features 001–004 onto it is a separate
feature that has to land first (see Assumptions).

### User Story 1 - Take over the shutters the bridge already knows (Priority: P1)

Someone installs the app next to a radio bridge that already has five shutters set up.
They open the app and see the five shutters, named as in the bridge, ready to use. No
file was edited, no address was typed.

**Why this priority**: It replaces the most fragile step of the whole setup — hand-copied
addresses — and every later story builds on the app learning shutters from the bridge.

**Independent Test**: Start with an app that has no shutters and a bridge that announces
three. Confirm the three appear with the bridge's names, can be driven, and are marked as
not yet measured. Delivers a working app without touching a configuration file.

**Acceptance Scenarios**:

1. **Given** the bridge announces three shutters and the app knows none, **When** the app
   starts, **Then** the three appear on the overview, drivable, each marked "Laufzeit nicht
   gemessen".
2. **Given** a shutter was set up by hand in the app's configuration before this feature,
   **When** the bridge announces the same shutter, **Then** it appears once, not twice, and
   keeps its name, travel times, calibration, groups and rules.
3. **Given** the app and bridge disagree about a shutter's name, **When** the person has
   renamed it in the app, **Then** the app keeps the person's name.

---

### User Story 2 - Add a new shutter, guided (Priority: P1)

Someone has a new window with a SIMU motor and its original remote. In the app they choose
"Rolladen hinzufügen". The app explains, step by step, what to do in the radio bridge —
create the shutter there, hold the PROG button on the old remote until the shutter jogs,
press "Program" in the bridge, then restart the bridge so it announces the new shutter and
starts accepting commands for it — and offers to open the bridge's page. When the bridge
announces the new shutter, the app notices by itself, says so, and asks for a name. It then
offers to measure the travel time.

**Why this priority**: Adding a window is the reason this feature exists. It is P1 together
with story 1 because the "notice by itself" half is story 1's mechanism.

**Independent Test**: Follow the guide against a bridge that then announces a new shutter.
Confirm the app detects it without a reload, the person names it, and it is drivable and
offered for calibration. Delivers a new window, end to end, without a text editor.

**Acceptance Scenarios**:

1. **Given** the person starts "Rolladen hinzufügen", **When** they read the guide, **Then**
   each step says what to do, where (app, bridge, remote, window), and how to tell it
   worked ("der Rolladen wackelt kurz").
2. **Given** the guide is open, **When** the bridge announces a shutter the app has not
   seen before, **Then** the guide moves on by itself: "Neuer Rolladen gefunden: …", with a
   name field prefilled from the bridge.
3. **Given** the person names and confirms the new shutter, **When** they finish, **Then**
   it appears on the overview, marked "Laufzeit nicht gemessen", and the app offers to go
   straight to measuring it.
4. **Given** the guide is open and nothing new appears within ten minutes, **When** the
   person looks, **Then** the app says what usually went wrong (bridge not restarted after
   adding, PROG not held long enough, learning mode timed out, announcements switched off in
   the bridge) and lets them keep waiting or cancel.
5. **Given** a shutter appears while nobody is running the guide, **When** anyone opens the
   app, **Then** it shows "Neuer Rolladen gefunden" with the same naming step — it is not
   silently added to automations that target all shutters until a person has confirmed it.

---

### User Story 3 - Remove a shutter (Priority: P2)

A window is replaced, or a motor is moved to another room. The person chooses "Rolladen
entfernen" on that shutter. The app asks once, says what will go with it — its rules
lose it as a target, it drops out of its groups, its measured travel times are deleted —
and explains how to also remove it from the bridge and, if wanted, make the motor forget
the bridge. After confirming, the shutter is gone from the app.

**Why this priority**: Less frequent than adding, and a stale shutter is an annoyance, not
a risk — but without it the list can only grow.

**Independent Test**: Remove a shutter that is in a group, targeted by two rules and
calibrated. Confirm it disappears from the overview, the group and both rules, that a rule
left with no targets says so, and that the app did not send anything to the bridge.

**Acceptance Scenarios**:

1. **Given** a shutter in a group and targeted by rules, **When** the person asks to remove
   it, **Then** the app lists those consequences by name before asking to confirm.
2. **Given** the person confirms, **When** removal completes, **Then** the shutter is gone
   from overview, groups and rule targets; a rule with no target left says "kein Rolladen
   mehr".
3. **Given** the shutter still exists in the bridge, **When** the person removes it from the
   app, **Then** the app says that the bridge still knows it and explains how to delete it
   there — and does not bring it back as "new" while the bridge keeps announcing it.
4. **Given** a removed shutter, **When** the person changes their mind, **Then** they can add
   it back from the list of shutters the bridge announces but the app has put aside.

---

### User Story 4 - The bridge forgets a shutter (Priority: P2)

Someone deletes a shutter in the bridge's own interface and restarts the bridge. The app
notices that the bridge no longer announces it, marks the shutter "Funkbrücke kennt diesen Rolladen nicht mehr", stops
offering commands for it, and offers to remove it from the app too.

**Why this priority**: Without it, a shutter deleted in the bridge would look perfectly
drivable in the app while every command vanishes into the air.

**Independent Test**: Restart the bridge without one of its shutters. Confirm the app marks it
within a minute of the restart, disables its buttons, keeps its settings, and offers removal.

**Acceptance Scenarios**:

1. **Given** the bridge stops announcing a shutter, **When** the app notices, **Then** the
   shutter is marked as unknown to the bridge, its buttons are disabled, and automations
   skip it with that reason.
2. **Given** such a shutter, **When** the bridge announces it again, **Then** it returns to
   normal with every setting intact.
3. **Given** the bridge is merely unreachable, **When** it stops sending anything at all,
   **Then** that is shown as "Funkbrücke nicht erreichbar" (feature 001) — not as every
   shutter being forgotten.

---

### User Story 5 - Adding without a working remote (Priority: P3)

The old remote is lost or broken. The guide offers the other way to put a motor into
learning mode: switch off power to that motor for a few seconds and back on. It warns
that every motor on the same circuit enters learning mode at once, and then continues as
in story 2.

**Why this priority**: Common in practice (remotes get lost), but story 2 must exist first,
and this only changes one step of the guide.

**Independent Test**: Walk the guide choosing "keine Fernbedienung"; confirm the
power-cycle steps and the shared-circuit warning appear, and the flow continues to
detection as in story 2.

**Acceptance Scenarios**:

1. **Given** the person chooses "keine Fernbedienung mehr", **When** the guide continues,
   **Then** it describes the power cycle, with timing, before the programming step.
2. **Given** that path, **When** the guide shows it, **Then** it warns prominently that all
   motors on the same circuit enter learning mode and would learn the same sender.

---

### Edge Cases

- **Two new shutters appear at once.** Each gets its own naming step; neither is lost.
- **A new shutter's name from the bridge is already used in the app.** The prefilled name
  is made unique ("Küche 2"); the person can change it.
- **The bridge restarts.** It re-announces everything. Nothing is duplicated, nothing is
  marked forgotten, and no "new shutter" prompt appears for shutters the app already has.
- **The app was off while a shutter was added in the bridge.** It is found on the next
  start, as new.
- **A shutter is removed in the app while a calibration run is in progress on it.** Removal
  is refused until the run ends or is aborted.
- **A shutter is removed while travelling.** Removal is allowed; the app sends nothing, and
  the motor finishes its travel on its own.
- **A shutter was set up by hand in the configuration and the bridge never announces it.**
  It keeps working as before; the app does not mark hand-configured shutters as forgotten.
- **The bridge's page cannot be opened from the app** (unknown address, other network).
  The guide still works as text; the link is a convenience.

## Requirements *(mandatory)*

### Functional Requirements

**Learning shutters from the bridge**

- **FR-001**: The system MUST learn the set of shutters from the radio bridge's own
  announcements, including each shutter's identity and name.
- **FR-002**: A shutter announced by the bridge and not yet known to the app MUST be
  presented as "new" and MUST NOT become part of the household's shutters — overview,
  "all shutters" in commands and automations, groups — until a person confirms it.
- **FR-003**: A shutter the app already knows MUST be matched to its announcement by its
  identity, never duplicated; the person's name, travel times, calibration, groups and
  rules MUST be kept.
- **FR-004**: Shutters configured by hand before this feature MUST keep working, whether or
  not the bridge announces them.
- **FR-005**: The bridge's announcements MUST be the only source of shutter identities; the
  app MUST NOT invent or alter an identity or address.

**Adding**

- **FR-006**: Users MUST be able to start a guided "add a shutter" flow that explains every
  step in the bridge, on the remote and at the window, with how to recognise success.
- **FR-007**: The system MUST NOT send any programming signal, create a shutter in the
  bridge, or operate the bridge's web interface. It MAY offer a link that opens the
  bridge's page for the person.
- **FR-008**: While the guide is open, a newly announced shutter MUST be detected within
  5 seconds of the bridge announcing it, without a reload, and the guide MUST continue to
  naming. The guide MUST include restarting the bridge, since the bridge announces a new
  shutter — and accepts commands for it — only after a restart.
- **FR-009**: On confirming, the person MUST give the shutter a name (prefilled from the
  bridge, made unique); it then appears marked as not yet measured, with an offer to
  measure it.
- **FR-010**: After 10 minutes without a new shutter the guide MUST say what commonly went
  wrong and let the person keep waiting or cancel.
- **FR-011**: The guide MUST offer the power-cycle route for a motor without a working
  remote, with the warning about shared circuits.

**Removing**

- **FR-012**: Users MUST be able to remove a shutter from the app after one confirmation that
  names its consequences: the groups it leaves, the rules that lose it, the measurements
  deleted.
- **FR-013**: Removal MUST take the shutter out of every group and every rule target, as
  features 003 and 004 already require for a shutter that disappears.
- **FR-014**: Removal MUST be refused while a calibration run on that shutter is in
  progress, with the reason.
- **FR-015**: Removal MUST NOT send anything to the bridge. The app MUST explain how to
  delete the shutter in the bridge and, optionally, how to make the motor forget it.
- **FR-016**: A removed shutter that the bridge still announces MUST be kept aside, not
  offered as "new" again, and MUST be restorable by a person.

**The bridge forgetting**

- **FR-017**: A shutter learned from the bridge that the bridge no longer announces after its
  next restart MUST be marked as unknown to the bridge within 60 seconds of that restart, with commands disabled and
  automations skipping it with that reason; its settings MUST be kept.
- **FR-018**: A bridge that is unreachable MUST NOT make shutters count as forgotten.

**Visibility**

- **FR-019**: New, set-aside and forgotten shutters MUST each be visible with their state in
  one place, so nothing the bridge knows is hidden from the person.

### Key Entities

- **Announced shutter**: What the bridge says exists — identity, name. Comes and goes with
  the bridge's announcements; never edited by the app.
- **Household shutter**: A shutter the household has confirmed. Has the app's name, travel
  times, calibration, group memberships and rule targets. Linked to at most one announced
  shutter by identity; may also come from the hand-written configuration.
- **Shutter state in the app**: new (announced, not confirmed), active, set aside (removed
  by a person while still announced), forgotten (active, no longer announced).
- **Setup guide**: The steps of adding, with the chosen route (existing remote or power
  cycle) and whether it is waiting for a new announcement.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person with no text editor and no knowledge of radio addresses can add a
  new window, from "Rolladen hinzufügen" to driving it from the app, in under 10 minutes,
  given a working remote and a bridge already running.
- **SC-002**: On first start next to a bridge with N shutters, all N are listed as new within
  5 seconds, and none appears twice after any number of bridge or app restarts.
- **SC-003**: A newly programmed shutter is noticed by an open guide within 5 seconds.
- **SC-004**: After a removal, the shutter appears in no screen, group or rule of the app,
  and no message was sent to the bridge.
- **SC-005**: A shutter deleted in the bridge is marked forgotten in the app within 60
  seconds of the bridge's next restart, and no command is offered for it from then on.
- **SC-006**: Zero shutter addresses are typed by a person for a household set up entirely
  after this feature.

## Assumptions

- **Prerequisite — the bridge's current interface.** In 2026 the radio bridge (Pi-Somfy)
  replaced the message topics the app was built on with a new scheme: separate command and
  position topics, a state topic, a bridge-availability topic, and per-shutter
  announcements. Features 001–004 have to be moved onto it first, with an amendment to
  constitution principle II, which names the old topics. That is its own feature; this one
  assumes it is done.
- The bridge's announcements carry, per shutter, a stable identity and a display name, and
  are kept available for anyone who connects later. **Corrected during planning** (from the
  bridge's code): the bridge announces its shutters only when it connects to the message
  channel, so a shutter added in the bridge appears — and becomes commandable — only after
  the bridge restarts; and deleting a shutter withdraws nothing, its old announcement stays
  kept. A deletion is therefore visible as a shutter missing from the fresh announcements
  after a restart.
- The bridge's announcements define 100 as fully open and 0 as fully closed. That settles
  the direction question for bridges on the current interface.
- Programming a motor, creating a shutter and deleting it in the bridge are only possible in
  the bridge's own interface. If a later bridge version offered them on the message
  channel, using them would be a separate decision against constitution principle I.
- The household is one trust zone, as in features 001–004: anybody on the home network may
  add or remove shutters.
- Out of scope: pairing additional remotes to a motor, changing a shutter's identity,
  importing travel times from the bridge, and devices other than RTS shutters.
