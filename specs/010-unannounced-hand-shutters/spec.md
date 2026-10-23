# Feature Specification: Hand-listed shutters the bridge never announces

**Feature Branch**: `main` (single-developer repository)

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: "Hand-listed shutters the bridge never announces. Problem seen on
a real Pi: the installation's shutters.toml was copied from an old example that contained four
sample shutters (Wohnzimmer, Küche, Schlafzimmer, Büro) at made-up RTS addresses
0x279621–0x279624. After switching from the simulator to the real bridge, the app showed them
as normal household shutters; commands to them reach no motor, and nothing warned.
Requirements: (1) Live operation (real bridge) must never carry sample/example shutters: a
shutter listed by hand whose address the bridge does not announce must be noticed and shown to
the person — in the app and in the log — as not known to the bridge, instead of looking like a
working shutter. Same erring rule as feature 005's "forgotten" marking: decide only when the
bridge has actually announced something live. (2) The person must be told how to resolve it
(remove the entry from shutters.toml, or fix the address to the one Pi-Somfy shows); the app
never writes shutters.toml. (3) The known sample addresses 0x279621–0x279624 from the old
example, if present while running against the real bridge, should be called out specifically
as leftovers from the example. (4) The simulator keeps working with hand-listed shutters as
before. (5) Upgrading installations whose shutters.toml still contains the sample block must
see the problem on first start against the real bridge."

## User Scenarios & Testing *(mandatory)*

Shutters reach the app two ways: the radio bridge announces them and a person names them in
the app (feature 005), or someone writes them into the configuration file by hand. A
hand-written entry is trusted completely today. If its address is wrong — mistyped, or never
real — the radio bridge ignores every command for it, and because the radio is one-way
nothing ever reports back. The app animates a shutter that never moves.

This happened for real. Until 2026-09-23 the example configuration contained four sample
shutters with invented addresses, and the setup guide told people to copy that example.
Every installation from that time carries them. In the simulator they behave perfectly; on
the real bridge they are four dead buttons that look alive.

Feature 005 deliberately left hand-written shutters alone ("the app does not mark
hand-configured shutters as forgotten"). This feature replaces that edge case: a
hand-written shutter the bridge demonstrably does not know is shown as such.

### User Story 1 - Leftover sample shutters are called out on first live start (Priority: P1)

A household switches its installation from the simulator to the real bridge. Its
configuration still holds the four sample shutters. On that first start the app shows each
of them as a leftover from the example configuration, not as a working shutter: its buttons
are unavailable, automations skip it with that reason, and the app says what to do — delete
the entry from the configuration file and restart. The log says the same, naming each entry.

**Why this priority**: It is the failure that actually happened, it affects every
installation set up before the example was fixed, and it needs no cooperation from the
bridge: the sample addresses are known to be invented.

**Independent Test**: Start the app against the real bridge with a configuration holding
the sample block; confirm the four shutters are flagged as example leftovers in the app and
the log, cannot be commanded, and the message names the fix. Start it against the simulator
with the same file; confirm nothing is flagged.

**Acceptance Scenarios**:

1. **Given** a configuration listing a shutter at one of the sample addresses, **When** the
   app starts against the real bridge, **Then** that shutter is marked as an example
   leftover, its commands are unavailable, and automations skip it with that reason.
2. **Given** that state, **When** the person opens the shutter or the overview, **Then** the
   app tells them in plain words that the entry comes from the old example and must be
   deleted from the configuration file, followed by a restart.
3. **Given** that state, **When** the app starts, **Then** the log contains one warning per
   such entry naming its id, name and address and the same fix.
4. **Given** the same configuration, **When** the app runs against the simulator, **Then**
   the shutters behave exactly as before this feature.
5. **Given** the person deletes the entries and restarts, **When** the app comes up,
   **Then** no example leftover is shown and nothing else about the household changed.

---

### User Story 2 - A hand-listed shutter the bridge does not know is shown as unknown (Priority: P2)

Someone listed a real window by hand and mistyped one digit of its address. The bridge
announces its shutters when it connects. The app compares: this hand-listed address is not
among them. It marks the shutter as unknown to the bridge — buttons unavailable, automations
skip it with that reason — and tells the person to either correct the address to the one the
bridge shows, or delete the entry. Shutters the bridge does announce are offered as new in the
usual way, so the person can see the right address next to the wrong one.

**Why this priority**: The general case behind story 1. It needs the bridge's live
announcements, so it cannot help a bridge with announcements switched off — story 1 covers
the known-bad addresses without that.

**Independent Test**: With the real bridge announcing shutters A and B, list A and a
non-existent C by hand; confirm C is marked unknown within the decision window and A is not.
Repeat with only old (retained) announcements and with announcements switched off; confirm
nothing is marked.

**Acceptance Scenarios**:

1. **Given** the bridge announces live after connecting, **When** a hand-listed shutter's
   address is not among those announcements by the end of the decision window, **Then** it
   is marked as unknown to the bridge, with commands unavailable and automations skipping it
   with that reason.
2. **Given** such a shutter, **When** the person looks at it, **Then** the app explains the
   two ways out — correct the address to the one the bridge announces, or delete the entry —
   and that both are done in the configuration file followed by a restart.
3. **Given** such a shutter, **When** the bridge later announces its address live, **Then**
   it returns to normal with every setting intact, without a restart.
4. **Given** the app receives only old, stored announcements, or none at all, **When** the
   window ends, **Then** no hand-listed shutter is marked.
5. **Given** the bridge is unreachable, **When** it stays silent, **Then** that is shown as
   "Funkbrücke nicht erreichbar" (feature 001), not as hand-listed shutters being unknown.

---

### Edge Cases

- **Announcements switched off in the bridge.** No live announcement ever arrives, so story 2
  never decides; only sample addresses (story 1) are flagged. That is the deliberate trade:
  marking wrongly disables a working window.
- **A sample address that the bridge really announces.** The bridge decides: an address the
  bridge announces live is a real shutter and is not flagged, even if it matches a sample
  address.
- **The bridge restarts.** It re-announces; a correct hand-listed shutter is never marked in
  between, and a marked one stays marked until its address is announced.
- **A hand-listed shutter is in a group or a rule.** The group and rule stay as they are; the
  shutter is skipped with its reason, like a forgotten one (feature 005).
- **A hand-listed shutter and a confirmed one share an address.** Unchanged from feature 005:
  the configuration file wins.
- **Every hand-listed shutter is flagged and nothing else exists.** The overview still shows
  them with their state and the fix; it does not look like an empty house.
- **The simulator.** It announces every configured shutter by construction, so nothing is
  ever flagged there, sample addresses included.

## Requirements *(mandatory)*

### Functional Requirements

**Example leftovers**

- **FR-001**: Running against the real bridge, a hand-listed shutter whose address is one of
  the addresses from the old example configuration (0x279621, 0x279622, 0x279623, 0x279624)
  MUST be marked as an example leftover from startup, unless the bridge announces that
  address live.
- **FR-002**: The list of sample addresses MUST be fixed to those that appeared in a
  published example; it MUST NOT be extended by guessing at "suspicious" addresses.

**Unknown to the bridge**

- **FR-003**: Running against the real bridge, a hand-listed shutter whose address the bridge
  does not announce live within the decision window after it comes online MUST be marked as
  unknown to the bridge.
- **FR-004**: The decision MUST follow the same rule as feature 005's forgotten marking: a
  window without any live announcement decides nothing, old stored announcements never
  count, and an unreachable bridge never marks anything.
- **FR-005**: A marked shutter whose address the bridge later announces live MUST return to
  normal immediately, with its settings, calibration, groups and rules intact.

**What marking means**

- **FR-006**: A shutter marked as example leftover or unknown to the bridge MUST NOT offer
  commands, MUST NOT be commanded by automations or group commands, and every skip MUST
  record the reason.
- **FR-007**: The app MUST show the marking with the shutter wherever the shutter appears,
  and in the one place where new, set-aside and forgotten shutters are listed (feature 005,
  FR-019).
- **FR-008**: The app MUST tell the person how to resolve the marking: for an example
  leftover, delete the entry; for an unknown shutter, correct the address to the one the
  bridge announces or delete the entry — in both cases in the configuration file, followed
  by a restart.
- **FR-009**: The app MUST NOT write, rewrite or comment out the configuration file.
- **FR-010**: The log MUST contain one warning per marked shutter when it is marked, naming
  its id, name, address, which marking applies, and the fix.
- **FR-011**: A marked shutter MUST NOT be presented as confirmed or working anywhere; its
  last known position, if any, MUST be shown as stale.

**Unchanged**

- **FR-012**: In the simulator, hand-listed shutters MUST behave exactly as before this
  feature, sample addresses included.
- **FR-013**: Hand-listed shutters the bridge announces MUST behave exactly as before.
- **FR-014**: Installations upgraded with the sample block still in their configuration MUST
  see the example-leftover marking on their first start against the real bridge, with no
  migration step.

### Key Entities

- **Hand-listed shutter**: A shutter written into the configuration file by a person. Has an
  id, name and address; the app reads it but never writes it.
- **Sample address**: One of the four invented addresses from the old example configuration.
  A fixed, closed list.
- **Marking of a hand-listed shutter**: none, example leftover, or unknown to the bridge.
  Derived at runtime from the configuration, the bridge kind and the bridge's live
  announcements; not stored.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the first start against the real bridge with the sample block in the
  configuration, all four sample shutters are shown as example leftovers within 5 seconds of
  the app answering, and none of them can be commanded.
- **SC-002**: A hand-listed shutter with an address the bridge does not announce is marked
  within 60 seconds of the bridge coming online, provided the bridge announces live.
- **SC-003**: Across any number of bridge and app restarts, a correctly hand-listed shutter is
  never marked, and a bridge with announcements switched off never causes a marking.
- **SC-004**: A person who sees the marking can resolve it from the app's explanation alone,
  without consulting the setup guide.
- **SC-005**: Zero commands are sent for a marked shutter, from the app, automations or groups.

## Assumptions

- A hand-listed address the bridge does not announce while announcing others is useless: the
  bridge only listens for commands to shutters it knows, so disabling its commands loses
  nothing.
- The decision window is feature 005's (live announcements arrive together on connect; 60 s
  in all).
- Sample addresses are flagged without waiting for announcements because they are known to
  be invented; the exception for a live-announced sample address exists only for the
  vanishingly unlikely real collision.
- The example configuration no longer contains active sample shutters (commit 83c6731); this
  feature is about installations made before that and about mistyped addresses.
- Creating, renaming or deleting shutters in the bridge from the app is feature 009's, not
  this one's.
