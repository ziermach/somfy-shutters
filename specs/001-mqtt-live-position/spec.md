# Feature Specification: Live position and movement

**Feature Branch**: `001-mqtt-live-position`

**Created**: 2026-09-21

**Status**: Draft

**Input**: User description: "MQTT bridge with live position and animation"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Move a shutter and watch it move (Priority: P1)

Someone at home opens the app on their phone, sees every shutter in the house with its
current position, and taps open or close on one. The graphic starts moving immediately
and travels at the speed the real shutter travels, arriving when the real one arrives.
Tapping stop halts both.

**Why this priority**: This is the product. Without it there is nothing to show, and
every other story decorates it. It is also the slice that proves the whole path works —
phone to house system to radio bridge to motor.

**Independent Test**: With the radio bridge reachable and one shutter configured, open
the app, tap close, and confirm the shutter closes and the graphic reaches the closed
position at the same moment. Delivers full manual control of the house on its own.

**Acceptance Scenarios**:

1. **Given** a shutter resting fully open, **When** the user taps close, **Then** the
   graphic begins moving within a moment of the tap and reaches closed at the same time
   as the physical shutter, within a small tolerance.
2. **Given** a shutter travelling, **When** the user taps stop, **Then** the physical
   shutter halts and the graphic freezes at the position where it stopped.
3. **Given** a shutter travelling, **When** the user taps the opposite direction,
   **Then** the shutter reverses and the graphic follows without jumping to a new value.
4. **Given** two phones showing the same house, **When** one of them moves a shutter,
   **Then** the other shows the same movement without being refreshed.
5. **Given** the user requests a position between the end stops, **When** the shutter
   reaches it, **Then** movement stops there and the position is shown as an estimate.

---

### User Story 2 - See how much the position can be trusted (Priority: P2)

The same person glances at the app before leaving the house. Next to each position it
says whether that number is certain or an estimate, and how old the estimate is. Where
it is doubtful, the app offers to resolve it by driving to an end stop.

**Why this priority**: The position is dead reckoning, and acting on a stale estimate as
if it were a reading is the failure this project exists to avoid. It is P2 only because
P1 must exist to have something to qualify.

**Independent Test**: Move a shutter to an end stop and confirm it reads as certain;
move it to an intermediate position, wait, and confirm it reads as an estimate with an
age. Delivers honest state on its own.

**Acceptance Scenarios**:

1. **Given** a shutter that has just reached an end stop, **When** the user looks at it,
   **Then** the position is presented as certain.
2. **Given** a shutter stopped between the end stops, **When** the user looks at it,
   **Then** the position is presented as an estimate together with the age of the last
   certain position.
3. **Given** a shutter whose last certain position is long past, **When** the user looks
   at it, **Then** the display is visibly de-emphasised and a resync is offered.
4. **Given** the user accepts the resync, **When** the shutter reaches the end stop,
   **Then** the position becomes certain again.
5. **Given** the house system has restarted and a shutter's position was not certain
   beforehand, **When** the user looks at it, **Then** the position reads as unknown
   rather than as a number.

---

### User Story 3 - Survive the parts that go missing (Priority: P3)

Connections drop. The radio bridge restarts, the phone loses Wi-Fi in the garden, the
house system reboots. The app says what is wrong in plain words and recovers by itself
when the parts come back, without the user reloading anything.

**Why this priority**: It decides whether the app is trusted over months rather than in
a demo, but a system that never loses anything still works without it.

**Independent Test**: Cut the link between the house system and the radio bridge while
the app is open, confirm the app says so and refuses to pretend, then restore it and
confirm the app recovers unprompted.

**Acceptance Scenarios**:

1. **Given** the app is open, **When** the house system becomes unreachable, **Then**
   the app says it is offline and stops presenting positions as current.
2. **Given** the app is offline, **When** the house system returns, **Then** the app
   reconnects on its own and shows current positions without user action.
3. **Given** the radio bridge is unreachable, **When** the user taps a command, **Then**
   the app states the command could not be delivered and does not animate movement that
   is not happening.
4. **Given** the house system restarts while a shutter is travelling, **When** it comes
   back, **Then** that shutter's position reads as unknown rather than as the value it
   had before the restart.

---

### Edge Cases

- A shutter is operated with its physical remote. The app has no way to learn this, so
  its estimate silently drifts; it must keep showing the age of the last certain
  position rather than implying the value is fresh.
- The radio command is not received by the motor — out of range, interference, obstacle.
  The app animates a movement that never happened. The next end stop resolves it; until
  then the position stays an estimate.
- A command arrives while the shutter is already travelling in the same direction.
- A second command arrives before the first has finished.
- The configured travel time is wrong, so the animation finishes early or late relative
  to the real shutter.
- The house system receives a position report from the radio bridge that contradicts its
  own estimate.
- The shutter is obstructed and the motor stops early; nothing reports this.
- Two people command the same shutter in opposite directions at the same moment.
- A shutter is configured with an address no motor answers to.
- The clock jumps (daylight saving, time sync) mid-travel.

## Requirements *(mandatory)*

### Functional Requirements

**Commanding**

- **FR-001**: Users MUST be able to command each shutter to fully open, fully close,
  stop, or travel to a chosen position between the end stops.
- **FR-002**: Users MUST be able to command all shutters at once, and the system MUST
  treat each shutter's movement independently thereafter.
- **FR-003**: The system MUST deliver commands to the radio bridge as the sole route to
  the motors, and MUST NOT transmit radio itself.
- **FR-004**: The system MUST reject or ignore a command for a shutter it does not know,
  and MUST report that to the user rather than failing silently.

**Position**

- **FR-005**: The system MUST maintain a position for every shutter, expressed as a
  percentage, and MUST make clear in the interface which direction 100 % denotes.
- **FR-006**: The system MUST classify every position as one of: certain (the shutter is
  at an end stop it just reached), estimated (computed from travel time), or unknown
  (no trustworthy basis).
- **FR-007**: The system MUST record the moment a position last became certain, and MUST
  expose the age of that moment alongside an estimated position.
- **FR-008**: The system MUST downgrade an estimate to a visibly less confident
  presentation once it is older than a configured threshold.
- **FR-009**: The system MUST offer an action that drives a shutter to an end stop for
  the sole purpose of making its position certain again.
- **FR-010**: The system MUST persist positions and their confidence across a restart,
  and MUST mark as unknown any shutter that was travelling when it stopped.
- **FR-011**: The system MUST NOT present an estimated position as a confirmed reading
  anywhere in the interface.

**Movement and animation**

- **FR-012**: The interface MUST begin animating a shutter as soon as a command is sent,
  without waiting for any report from the radio bridge.
- **FR-013**: The animation MUST run at the travel speed configured for that shutter and
  that direction, so it arrives when the physical shutter arrives.
- **FR-014**: Travel times MUST be read from configuration per shutter and per direction,
  MUST NOT be hardcoded, and MUST be editable by the user.
- **FR-015**: Where no travel time has been configured, the system MUST use a stated
  default, MUST mark that shutter's timing as not measured, and MUST still animate.
- **FR-016**: The system MUST stop the animation at the position where a stop command was
  issued, not at the original target.
- **FR-017**: The system MUST reconcile a position report from the radio bridge with its
  own estimate without the displayed position jumping abruptly.

**Live updates**

- **FR-018**: Every open client MUST reflect a shutter's movement, whoever or whatever
  caused it, without the user reloading.
- **FR-019**: Clients MUST receive state from the house system only, and MUST NOT
  connect to the message bus directly.
- **FR-020**: A client that reconnects after an interruption MUST receive the full
  current state rather than only subsequent changes.

**Failure**

- **FR-021**: The system MUST detect that the radio bridge is unreachable and MUST
  surface that to the user in terms of what cannot be done.
- **FR-022**: A client MUST show when it is not connected to the house system and MUST
  stop presenting its positions as current.
- **FR-023**: The system MUST reconnect to the message bus and the clients MUST
  reconnect to the house system automatically, with backoff, without user action.
- **FR-024**: The whole path MUST function with no internet connection available.

### Key Entities

- **Shutter**: One motorised covering. Has a name, a radio address used to address it,
  travel times per direction, a current position, a confidence, and the moment its
  position last became certain.
- **Position estimate**: A percentage together with its confidence, the time it was
  derived, and whether it came from a command the system issued or a report it received.
- **Movement**: An in-progress travel: which shutter, from where, toward what target,
  in which direction, started when, expected to arrive when.
- **Command**: A request to move a shutter, its target, when it was issued, and whether
  it was accepted for delivery.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tapping a control produces visible movement in the interface within
  200 milliseconds, without waiting for any confirmation from the house.
- **SC-002**: At the end of a full open or close, the animation and the physical shutter
  finish within 1 second of each other, on a shutter whose travel times were measured.
- **SC-003**: A movement started on one device appears on every other open device within
  1 second.
- **SC-004**: Every position shown anywhere in the interface carries its confidence; a
  review of all screens finds no bare number presented as fact.
- **SC-005**: After the house system restarts, the interface shows correct positions and
  confidences within 10 seconds, with no user action.
- **SC-006**: After a client loses its connection for up to 5 minutes, it recovers full
  current state within 5 seconds of the connection returning, without a reload.
- **SC-007**: When the radio bridge is unavailable, a user attempting to move a shutter
  learns within 5 seconds that it did not happen.
- **SC-008**: A person who has not seen the app before can tell, without help, which
  shutters are open and which positions are only estimates.
- **SC-009**: Commanding all shutters at once moves every one of them, with no command
  lost, for a house of at least 10 shutters.
- **SC-010**: The system runs for 7 days without a restart while remaining responsive to
  commands.

## Assumptions

- The radio bridge is already installed, paired with the motors, and reachable; adding
  and pairing shutters is out of scope here.
- Measuring travel times is out of scope. This feature reads them from configuration and
  uses a stated default where they are missing; a later feature measures them.
- Automations, schedules and sun-based triggers are out of scope.
- The house is trusted: everyone on the home network may operate every shutter, and no
  user accounts or permissions are in scope.
- Clients are used on the home network. Remote access from outside is out of scope.
- 100 % denotes fully open and 0 % fully closed in the interface. Which direction the
  radio bridge itself expects is an open hardware question; the system translates
  between the two in one place, and the interface convention does not depend on the
  answer.
- Positions between the end stops are time estimates and will drift. This feature makes
  the drift visible; it does not try to eliminate it.
- A shutter operated by its physical remote cannot be observed. Tracking physical
  remotes is a separate, optional capability and is out of scope.
- A house has on the order of 10 shutters, and a handful of clients are open at once.
