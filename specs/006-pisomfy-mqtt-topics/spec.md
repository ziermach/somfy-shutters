# Feature Specification: Speaking the radio bridge's current interface

**Feature Branch**: `main` (single-developer repository, no feature branches)

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Umstellung auf neue Pi-Somfy MQTT-Topics"

## User Scenarios & Testing *(mandatory)*

The app never touches the radio. It asks the radio bridge (Pi-Somfy) to move shutters and
listens to what the bridge reports, over a message channel. Features 001–004 were built
against the bridge's interface as it was documented when the project started. In March
2026 the bridge replaced that interface: commands, positions and movement now travel on
different channels with different contents, the bridge announces whether it is running,
and it announces each shutter it knows. The old channels no longer exist.

As things stand, an app installed next to a current bridge would not move a single
shutter and would never hear a position. This feature makes the app speak the current
interface — and takes the three things the new interface offers that the old one did not:
a real stop, a real "the bridge is running" signal, and a report when a shutter starts and
stops moving, including when somebody used a physical remote.

Nothing a person sees should change, except that things which were guesses before become
facts where the bridge now says so.

### User Story 1 - Shutters move again (Priority: P1)

Someone sets up the app next to a current radio bridge. They tap "zu" on the living room,
and the living room closes. They drive it to 30 %, and it goes to 30 %. Every command the
app has — open, close, stop, a position, all at once, from an automation, during
calibration — reaches the shutter.

**Why this priority**: Without it the app does nothing at all against a current bridge.

**Independent Test**: Against a bridge speaking the current interface, send open, close,
stop and a position to one shutter and "all open" to every shutter; confirm each command
arrives at the bridge in the form it expects and the shutter moves.

**Acceptance Scenarios**:

1. **Given** a shutter at 100 %, **When** the person taps "zu", **Then** the bridge receives a
   close command for that shutter, and the app animates as before.
2. **Given** a shutter at 0 %, **When** the person drives it to 30 %, **Then** the bridge
   receives a request for position 30 — after the travel-curve conversion of feature 002 —
   and the shutter lands where calibration says 30 % is.
3. **Given** automations, calibration runs, groups and "Alle zu", **When** any of them
   commands a shutter, **Then** it goes through the same path and reaches the bridge.

---

### User Story 2 - Stop actually stops (Priority: P1)

A shutter is closing and the cat is on the windowsill. The person taps "stop". The shutter
stops where it is.

**Why this priority**: On the current bridge, the way the app stopped a shutter until now
— asking it to go to where it currently is — does nothing at all, so the shutter would
keep closing. That is a safety issue, not a nicety.

**Independent Test**: Start a travel, send stop halfway; confirm the bridge receives a stop
command, and the app settles the shutter where it was as an estimate (feature 001).

**Acceptance Scenarios**:

1. **Given** a shutter travelling, **When** the person taps "stop", **Then** the bridge
   receives an explicit stop, and the app freezes the graphic where it is.
2. **Given** a calibration run is aborted, or a check drive is interrupted, **When** the app
   halts the shutter, **Then** it uses the same explicit stop.

---

### User Story 3 - Positions and movements the bridge reports are understood (Priority: P1)

The bridge reports each shutter's position and whether it is opening, closing or
standing. The app understands both. When somebody uses a physical remote and the bridge
hears it, the app sees the shutter start moving and stop, instead of inferring it from a
series of positions.

**Why this priority**: Every rule of feature 001's reconciliation — end stops become
certain, a disagreeing report corrects the estimate, a physical remote is recognised —
depends on reading what the bridge says.

**Independent Test**: Have the bridge report a position while idle, a position during the
app's own travel, an end stop, and an opening/closing/stopped sequence caused by a
physical remote; confirm each lands as features 001 and 002 describe.

**Acceptance Scenarios**:

1. **Given** the shutter is idle at an estimated 62 %, **When** the bridge reports 48,
   **Then** the app corrects to 48 and glides there, as in feature 001.
2. **Given** the bridge reports "opening" for a shutter the app did not command, **When**
   the app hears it, **Then** it treats the shutter as moved by someone else from that
   moment, not after several position reports.
3. **Given** the bridge reports a fully open or fully closed position, **When** the app
   hears it, **Then** the position becomes certain.
4. **Given** the app connects and the bridge's last known positions are delivered at once,
   **When** the app hears them, **Then** they are used to fill in positions the app does
   not know, and they do not cause corrections, glides or "someone used a remote" for
   positions the app already knows — they are old news, not movement.

---

### User Story 4 - The app knows when the bridge itself is down (Priority: P2)

The bridge's process crashes while the message broker keeps running. Until now the app
could not tell: the broker answered, so commands looked delivered. With this feature the
app shows "Funkbrücke nicht erreichbar" as soon as the bridge says it is gone, and refuses
commands honestly, exactly as when the broker is unreachable.

**Why this priority**: Without it the app claims to send commands into a bridge that is not
there. Feature 001 already handles "bridge unreachable"; this makes it true in one more
case.

**Independent Test**: Stop the bridge while the broker stays up; confirm the app shows the
bridge as unreachable within 5 seconds and commands fail with that reason; restart the
bridge and confirm the app recovers without a reload.

**Acceptance Scenarios**:

1. **Given** the broker is up and the bridge announces it has gone offline, **When** a
   person looks, **Then** the app shows "Funkbrücke nicht erreichbar" and disables commands.
2. **Given** the bridge comes back and announces it is online, **When** the app hears it,
   **Then** commands are offered again.

---

### User Story 5 - Nothing to reconfigure (Priority: P2)

Someone who set up the app before this change updates it. Their shutters, names, travel
times, calibration, groups and rules keep working with the current bridge without editing
anything, and a setting that no longer means anything is ignored with a clear note rather
than silently changing behaviour.

**Why this priority**: A migration that makes people redo their setup would be worse than
the old interface.

**Independent Test**: Start the updated app with a configuration and database from before
this feature; confirm every shutter is addressed on the current interface and every
setting is kept.

**Acceptance Scenarios**:

1. **Given** a configuration listing shutters by their radio addresses, **When** the app
   starts, **Then** each shutter is addressed on the current interface under the identity
   the bridge uses for it.
2. **Given** a configuration that sets the old direction switch, **When** the app starts,
   **Then** it logs that the current bridge defines 100 as open, ignores the switch, and
   the behaviour is correct.

---

### Edge Cases

- **A report for a shutter the app does not know.** Ignored and logged once per shutter,
  as in feature 001.
- **A malformed report** (not a number, out of range, unknown movement word). Ignored and
  logged; never crashes the connection.
- **The bridge reports "stopped" at an intermediate position after the app's own travel.**
  Consistent with the app's estimate within tolerance: nothing changes. Clearly different:
  it is a correction, as in feature 001.
- **The bridge answers a command with no movement** (the requested position is where it
  already believes the shutter is). The app's own animation still runs from its estimate,
  as before; the next report reconciles.
- **Retained reports from a shutter that has since been deleted in the bridge.** They are
  handled like any report for a shutter the app does not know. Showing the shutter as
  forgotten is feature 005's business.
- **The bridge announces "online" while its messages are still arriving from before a
  restart.** The app does not treat the flood of re-announced positions as movement
  (story 3, scenario 4).
- **The broker is down.** Unchanged from feature 001: bridge unreachable, commands refused.

## Requirements *(mandatory)*

### Functional Requirements

**Commands**

- **FR-001**: The system MUST send open, close and stop as the bridge's explicit commands,
  and positions as the bridge's position request, on the channels the current bridge
  listens to.
- **FR-002**: A stop MUST be sent as the bridge's explicit stop command — never as a
  position request.
- **FR-003**: Positions sent MUST keep feature 002's conversion (travel curve, the bridge's
  own counter) and the full-open and full-closed commands MUST be used for the end stops.
- **FR-004**: Every command source — single shutter, all shutters, groups, automations,
  calibration, check drives — MUST use the same path, as today.

**Reports**

- **FR-005**: The system MUST understand the bridge's position reports and apply feature
  001's reconciliation rules to them unchanged.
- **FR-006**: The system MUST understand the bridge's movement reports (opening, closing,
  open, closed, stopped) and use an "opening"/"closing" it did not cause as the start of an
  external movement.
- **FR-007**: Reports delivered all at once when the app connects MUST only fill in unknown
  positions; they MUST NOT correct known positions, animate, or count as external movement.
- **FR-008**: Malformed reports and reports for unknown shutters MUST be ignored and logged
  without disturbing anything else.

**Bridge health**

- **FR-009**: The system MUST treat the bridge's own "offline" announcement as "bridge
  unreachable" with everything feature 001 attaches to it, and "online" as reachable.
- **FR-010**: The bridge MUST count as reachable only when both the message broker and the
  bridge itself are.

**Migration**

- **FR-011**: Existing configurations and stored data MUST keep working without edits; each
  configured shutter MUST be addressed under the identity the current bridge uses for it.
- **FR-012**: The old direction switch MUST be ignored with a logged note, since the current
  bridge defines 100 as fully open.
- **FR-013**: The system MUST NOT use the old channels at all. Older bridge versions are not
  supported.

**The simulated house**

- **FR-014**: The simulator MUST speak the current interface in both directions — commands
  in, positions, movements and availability out, including the burst on connect — so that
  every test against it exercises the same behaviour as a real bridge.

**Governance**

- **FR-015**: The project's constitution MUST be amended so that its integration principle
  names the current channels instead of the old ones. The principle itself — the message
  channel is the only integration point; the bridge's web interface and files are off
  limits — stays as it is.

### Key Entities

- **Command**: open, close, stop, or a position 0–100, for one shutter identity.
- **Position report**: a shutter identity and a position 0–100, as the bridge believes it.
- **Movement report**: a shutter identity and one of opening, closing, open, closed, stopped.
- **Bridge availability**: online or offline, announced by the bridge itself.
- **Shutter identity**: how the bridge names a shutter on the channel; the app maps its
  configured shutters to it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Against a current bridge, 100 % of commands from every source in the app reach
  it in a form it acts on — measured on the simulator speaking the current interface and
  confirmed on real hardware.
- **SC-002**: A stop sent during travel halts the shutter; the graphic and the shutter end
  within a few percentage points of each other.
- **SC-003**: The bridge going offline while the broker stays up is shown within 5 seconds,
  and no command is presented as sent while it is offline.
- **SC-004**: Connecting to a bridge that has just re-announced every shutter produces zero
  corrections, glides or "external movement" events for positions the app already knew.
- **SC-005**: A setup from before this feature works after the update with zero edits.
- **SC-006**: Every existing test scenario of features 001–004 passes against the simulator
  speaking the current interface.

## Assumptions

- The current bridge interface is the one Pi-Somfy introduced in v3.1 (2026-03-27) and
  still ships: an explicit command channel (open, close, stop), a position request
  channel, position and movement reports kept for late joiners, a bridge availability
  announcement, and per-shutter announcements for home-automation discovery. Movement
  reports cover physical remotes only when the bridge's receiver is enabled.
- A position request equal to the bridge's current belief makes the bridge do nothing; that
  is why stop must be the explicit command (story 2).
- The identity the bridge uses for a shutter on the channel corresponds to its radio
  address, which is what the app's configuration already holds. If hardware bring-up shows
  otherwise, the mapping is configuration, not code (constitution: measured values live in
  configuration).
- Using the per-shutter announcements to learn shutters is feature 005, not this one. This
  feature only stops ignoring what the bridge says about itself and its shutters' state.
- Constitution amendment: the integration principle names specific channels; changing the
  names without changing the principle is a minor amendment.
- Verification on real hardware remains required for the command path (constitution); it
  joins the pending hardware tasks.
