# Feature Specification: Travel-time calibration

**Feature Branch**: `main` (single-developer repository, no feature branches)

**Created**: 2026-09-21

**Status**: Draft

**Input**: User description: "Laufzeit-Kalibrierung"

## User Scenarios & Testing *(mandatory)*

Feature 001 animates a shutter from a travel time someone typed into
configuration. This feature is how that number stops being a guess.

There is no sensor to ask. The motor reports nothing, and the radio bridge's own
position is derived from its own configured travel time, so it cannot be used to
measure ours. The only instrument available is a person watching the window.

### User Story 1 - Measure a shutter by watching it (Priority: P1)

Someone stands at the window with their phone, starts a guided run, and presses a
button twice: once when the shutter actually begins to move, once when it stops at the
end. The app does that in both directions, a few times, and keeps the result. From then
on the animation for that shutter matches what the window does.

**Why this priority**: Without it every travel time is invented, and the animation is
visibly wrong on every shutter. It is also the only part that strictly needs a human, so
it must exist before anything can refine it.

**Independent Test**: Take a shutter with no measurement, run the guided flow once per
direction, and confirm the stored times appear and the live view now finishes together
with the real shutter. Delivers correct animation on its own.

**Acceptance Scenarios**:

1. **Given** a shutter resting at an end stop, **When** the user starts a run, **Then**
   the shutter travels toward the opposite end and the app asks for the two presses in
   order, saying which is expected next.
2. **Given** a run in progress, **When** the user presses at the start of movement and
   again on arrival, **Then** the run is recorded with a dead time and a total time, and
   the next run is offered in the opposite direction.
3. **Given** three recorded runs in one direction, **When** the user looks at the
   result, **Then** the stored value is the median of them, not the mean, and the
   individual runs remain visible.
4. **Given** a run whose total time is wildly different from the others, **When** it
   finishes, **Then** it is marked as discarded with a reason and excluded from the
   result.
5. **Given** the user abandons a run mid-travel, **When** they return, **Then** the app
   states the position is no longer at an end stop and offers to drive to one before
   measuring again.
6. **Given** a measured shutter, **When** the user commands it from the normal view,
   **Then** the animation uses the measured times without any further action.

---

### User Story 2 - Stay accurate without being asked (Priority: P2)

Nobody wants to repeat the wizard. Whenever a shutter happens to travel from one end
stop to the other uninterrupted during normal use, the system quietly records how long
it took and keeps the stored value current. Months later the times still match, even
though the motor has aged and the slats are heavier in winter.

**Why this priority**: This is what keeps the feature true over time; the wizard only
bootstraps it. It is P2 because it cannot be observed until measurements exist and some
normal use has happened.

**Independent Test**: Seed a deliberately wrong travel time, drive the shutter end to
end a few times through the normal view, and confirm the stored value converges toward
the real one without anybody opening the calibration screen.

**Acceptance Scenarios**:

1. **Given** a shutter travelling from one end stop to the other without interruption,
   **When** it arrives, **Then** the elapsed time is recorded as a measurement for that
   direction.
2. **Given** a travel that was stopped, reversed, or started from an intermediate
   position, **When** it ends, **Then** nothing is recorded.
3. **Given** a recorded set of measurements, **When** a new one arrives, **Then** the
   stored value follows the median of the recent ones rather than jumping to the latest.
4. **Given** a measurement far outside the established range, **When** it arrives,
   **Then** it is rejected and does not affect the stored value.
5. **Given** a shutter whose real travel time has genuinely changed, **When** enough new
   measurements accumulate, **Then** the stored value follows the change.
6. **Given** measurements arriving passively, **When** the user opens the calibration
   view, **Then** they can see that the value is being maintained and when it last
   changed.

---

### User Story 3 - Check it without a stopwatch (Priority: P3)

The animation still feels slightly off. Rather than measuring again, the user asks the
app to drive to the middle and simply answers whether the shutter looks about halfway.
A few of those and the middle of the travel matches what they see.

**Why this priority**: Two presses cannot capture that the motor does not travel at a
constant rate, so a residual error in mid-travel remains by design. This resolves it
with one tap instead of four presses. It is genuinely optional — the animation is
already usable without it.

**Independent Test**: With a calibrated shutter, run the check, answer "too high" a few
times, and confirm the mid-travel display shifts in the direction indicated while the
end stops stay exactly right.

**Acceptance Scenarios**:

1. **Given** a calibrated shutter, **When** the user starts a check, **Then** the
   shutter drives to the displayed midpoint and the app asks whether it looks halfway.
2. **Given** the user answers "too high" or "too low", **When** the answer is recorded,
   **Then** the mid-travel display shifts toward what they reported, by a bounded
   amount.
3. **Given** any number of checks, **When** the shutter is driven to an end stop,
   **Then** the display still reaches exactly 0 % or 100 % — a check may never distort
   the end points.
4. **Given** the user answers "about right", **When** the answer is recorded, **Then**
   nothing changes and the check is closed.

---

### Edge Cases

- The user presses the second button late, or misses the moment entirely. Reaction time
  biases every run in the same direction; the median over several runs is what limits
  the damage, and the flow has to make three runs cheap enough that people do them.
- The user presses "it is moving" before anything moves, out of anticipation.
- A run is interrupted by someone commanding the same shutter from another device.
- A run is interrupted by a scheduled automation.
- The shutter is obstructed and stops early; nothing reports this, so the run records a
  short travel that must be rejected as implausible.
- The radio command that starts a run is never received. No movement, no presses, and
  the flow has to time out rather than wait forever.
- A passive measurement is taken while somebody operates the shutter by hand at the same
  time.
- A shutter is measured, then the physical installation changes (new motor, serviced
  roller) and every stored value is suddenly wrong.
- Travel up and travel down differ; a value must never be copied from one direction to
  the other.
- The user re-runs calibration on a shutter that already has good values.
- All measurements are discarded while the shutter is in use.

## Requirements *(mandatory)*

### Functional Requirements

**Guided measurement**

- **FR-001**: Users MUST be able to start a guided measurement for one specific shutter.
- **FR-002**: A measurement run MUST begin from an end stop, and the system MUST refuse
  to start one from an intermediate position.
- **FR-003**: Where the position is not at an end stop, the system MUST offer a
  non-measured drive to one, and MUST NOT record that drive as a measurement.
- **FR-004**: During a run the system MUST collect exactly two user inputs: the moment
  movement was observed to begin, and the moment it was observed to stop.
- **FR-005**: The interface MUST state which input is expected next, and MUST show the
  elapsed time while the run is in progress.
- **FR-006**: Consecutive runs MUST alternate direction, so each run starts from the end
  stop the previous one reached and no travel is wasted on repositioning.
- **FR-007**: A run MUST record a dead time (command to first movement) and a total time
  (command to arrival) for one direction.
- **FR-008**: Users MUST be able to abort a run, and the system MUST then treat the
  position as no longer certain.
- **FR-009**: A run with no arrival input by twice the expected travel time MUST be
  abandoned and not recorded.

**Validity and results**

- **FR-010**: The system MUST reject a run whose observed movement start is not before
  its arrival, and MUST state why.
- **FR-011**: The system MUST reject a run whose total time falls outside half to twice
  the established value for that shutter and direction, and MUST state why.
- **FR-012**: Rejected runs MUST remain visible with their reason rather than
  disappearing.
- **FR-013**: The stored value for a direction MUST be the median of its valid
  measurements, never the mean.
- **FR-014**: The system MUST store and use travel times per shutter **and per
  direction**; a value measured in one direction MUST NOT be applied to the other.
- **FR-015**: Users MUST be able to see the stored values, the runs behind them, and
  when they last changed.
- **FR-016**: Users MUST be able to discard all measurements for a shutter, after which
  it behaves as an uncalibrated one.
- **FR-017**: Measured values MUST take effect immediately for the live view, with no
  restart and no further confirmation.

**Passive maintenance**

- **FR-018**: A travel from one end stop to the other, uninterrupted and initiated by
  the system, MUST be recorded as a measurement for that direction.
- **FR-019**: A travel that was stopped, reversed, started from an intermediate
  position, or not initiated by the system MUST NOT be recorded.
- **FR-020**: Passive measurements MUST be subject to the same plausibility rejection as
  guided ones.
- **FR-021**: The stored value MUST follow the median of a bounded number of recent
  measurements, so a genuine change in the shutter is eventually followed while a single
  outlier is not.
- **FR-022**: The system MUST record when a stored value last changed and MUST make that
  visible.

**Verification**

- **FR-023**: Users MUST be able to run a check that drives a calibrated shutter to its
  displayed midpoint and asks whether it appears halfway.
- **FR-024**: An answer of "too high" or "too low" MUST shift the mid-travel display
  toward what was reported, by a bounded amount per answer.
- **FR-025**: No number of checks may change where the display reaches 0 % or 100 %.
- **FR-026**: Users MUST be able to undo the effect of checks, returning to the measured
  values alone.

**Throughout**

- **FR-027**: A shutter MUST remain fully operable while it has no measurements, using a
  stated default, and the interface MUST mark it as not calibrated.
- **FR-028**: During a guided run the system MUST prevent other commands to that shutter
  from the interface, and MUST state that a measurement is in progress.
- **FR-029**: If a shutter is commanded from elsewhere during a run — an automation, a
  physical remote — the run MUST be discarded rather than recorded.
- **FR-030**: Measured values MUST be recorded as configuration a person can inspect and
  correct by hand.

### Key Entities

- **Measurement run**: One observed travel. Which shutter, which direction, the dead
  time, the total time, when it happened, whether it was guided or passive, and if
  rejected, why.
- **Calibration**: What the system currently believes about one shutter and direction —
  the stored dead time and travel time, how many runs support them, and when they last
  changed.
- **Check answer**: One verification response — which shutter, what the user reported at
  the midpoint, and when.
- **Curve adjustment**: The accumulated effect of check answers on mid-travel display
  for one shutter, bounded, and reversible independently of the measurements.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can calibrate one shutter in both directions, three runs each, in
  under three minutes without instructions beyond what the screen says.
- **SC-002**: After guided calibration, a full open or close finishes within 1 second of
  the animation on the same shutter.
- **SC-003**: Mid-travel, the displayed position is within 10 percentage points of the
  real one after guided calibration alone, and within 4 after verification checks.
- **SC-004**: A deliberately wrong stored value converges to within 5 % of the true
  travel time after at most ten uninterrupted end-to-end travels in normal use, with no
  user involvement.
- **SC-005**: A single implausible measurement, guided or passive, never changes the
  stored value.
- **SC-006**: Every shutter's calibration state — measured, partly measured, never
  measured, or aged — is visible at a glance from one screen.
- **SC-007**: An uncalibrated shutter remains fully operable, and a user can tell from
  the interface that its position display is less trustworthy.
- **SC-008**: A person returning after six months finds travel times still accurate to
  within 1 second on shutters that get daily use, without having recalibrated.

## Assumptions

- Feature 001 is in place: shutters can be commanded, positions are tracked with a
  confidence, and travel times are already read from configuration per direction. This
  feature supplies those values rather than introducing them.
- The person calibrating can see the shutter while holding the device. Remote
  calibration is out of scope and would be meaningless.
- Reaction time is part of the measurement and cannot be eliminated. Taking the median
  of three runs is accepted as the mitigation; the design does not attempt to model or
  subtract it.
- Two presses per run is the deliberate limit. A third mark placed at the midpoint makes
  accuracy *worse*, because the travel curve is symmetric there and the measurement
  lands where the error is already zero; four marks would help but nobody performs four
  presses across every window. This was measured in the mock's explainer and is not
  revisited here.
- The residual mid-travel error after two presses is roughly nine percentage points.
  Reducing it is what User Story 3 is for, and it is optional.
- Motors are not paired yet, so the whole feature is developed and validated against the
  simulated house, whose per-window dead time and travel curve the system cannot see.
- The interface is German, matching feature 001.
- Calibration is not scheduled or automatic. Nothing starts a guided run on its own.
- Adding, pairing and removing shutters is a separate concern and out of scope here.
