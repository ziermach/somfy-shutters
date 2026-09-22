# Feature Specification: Shutter automations

**Feature Branch**: `main` (single-developer repository, no feature branches)

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Automationen mit Zeitplänen und Sonnenstand"

## User Scenarios & Testing *(mandatory)*

Features 001 and 002 made a shutter drivable from a phone and made its animation
honest. This feature is what makes the phone unnecessary most days: the house
opens in the morning and closes in the evening on its own, following either the
clock or the sun.

Two properties of this project shape everything below. The motors report
nothing, so an automation can only *send* a command — it can never confirm the
shutter got there. And the whole system runs on one small computer in the house
with no internet required, which includes knowing what time it is and where the
sun is.

### User Story 1 - Open and close on a schedule (Priority: P1)

Someone creates a rule: on weekdays at 06:45, open all shutters. They pick a name,
a time, the days of the week, which shutters, and what to do — open, close, or a
position. From then on the house does it, whether or not any phone is on, and the
live view shows the shutters moving exactly as if someone had pressed the button.

**Why this priority**: A fixed daily schedule is what most households want first,
and it is the smallest thing that removes the daily chore. Everything else in this
feature refines when a rule fires; this is the rule firing at all.

**Independent Test**: Create a rule for two minutes from now on today's weekday,
close the app, and confirm the chosen shutters move at that minute and the live
view shows the movement when opened again. Delivers a working morning routine on
its own.

**Acceptance Scenarios**:

1. **Given** an enabled rule "weekdays 06:45, all shutters, open", **When** it is
   06:45 on a Tuesday, **Then** every shutter is commanded to open, and every open
   client shows them travelling.
2. **Given** the same rule, **When** it is 06:45 on a Saturday, **Then** nothing
   happens.
3. **Given** a rule targeting two shutters, **When** it fires, **Then** only those
   two are commanded; the others are untouched.
4. **Given** a rule with the action "position 30 %", **When** it fires, **Then** the
   shutters are commanded to 30 % and shown as an estimate, never as confirmed.
5. **Given** no phone or browser is open anywhere, **When** a rule's time comes,
   **Then** it still fires.

---

### User Story 2 - Follow the sun (Priority: P2)

Someone creates a rule: 30 minutes before sunset, close all shutters. The time moves
with the seasons without anyone touching it. Because sunrise in June can be before
five in the morning, a sun rule can also carry a bound — "at sunrise, but not before
06:30" — so the bedroom does not open at dawn.

**Why this priority**: Sunset closing is the second most requested routine, and a
fixed evening time is wrong for most of the year. It depends on story 1's rules
existing, so it comes second.

**Independent Test**: Set the home location, create a rule "sunset −30 min, close",
confirm the rule shows today's computed time, and confirm it fires at that time.
Change the date to midsummer and midwinter and confirm the shown time follows.

**Acceptance Scenarios**:

1. **Given** a home location is set, **When** a user creates a sunset rule with an
   offset of −30 minutes, **Then** the rule shows the concrete time it will fire
   today, and fires then.
2. **Given** a sunrise rule bounded "not before 06:30", **When** sunrise is at
   04:58, **Then** the rule fires at 06:30.
3. **Given** a sunset rule bounded "not after 21:00", **When** sunset is at 21:40,
   **Then** the rule fires at 21:00.
4. **Given** no home location is set, **When** a user tries to create a sun rule,
   **Then** the app explains that a location is needed and offers to set it; time
   rules are unaffected.
5. **Given** the house has no internet connection, **When** a sun rule is due,
   **Then** it fires at the correct time — the sun position is never looked up.

---

### User Story 3 - See and manage what will happen (Priority: P2)

Someone opens the automations screen and sees every rule: its name, when it fires
next (as a concrete time, even for sun rules), what it does, and whether it is on.
They can switch a rule off and on with one tap, edit it, or delete it. For each rule
they can see when it last ran and whether every shutter was reached.

**Why this priority**: Without this, rules are invisible and a surprise is only
discovered when a shutter moves unexpectedly. It ships alongside story 1 in
practice, but story 1 can be tested without it.

**Independent Test**: With three rules, confirm the list shows each next firing time
correctly, toggle one off and confirm it no longer fires, edit another's time and
confirm the next firing time updates, delete the third.

**Acceptance Scenarios**:

1. **Given** several rules, **When** the automations screen opens, **Then** each rule
   shows its next firing as a date and time, or says it will not fire (disabled, no
   days selected, or no shutter left).
2. **Given** an enabled rule, **When** the user switches it off, **Then** it does not
   fire until switched on again, and it keeps all its settings.
3. **Given** a rule that fired this morning with one shutter refused, **When** the
   user looks at it, **Then** it shows the time it ran and which shutter was not
   commanded, with the reason.
4. **Given** a user saves a rule that commands the same shutter in the same minute
   as another enabled rule, but differently, **When** they save, **Then** the app
   warns them and says which of the two will win.

---

### User Story 4 - Not today (Priority: P3)

Someone is on holiday, or wants to sleep in on a public holiday. They pause all
automations at once — until they resume, or until a chosen date — or skip only the
next firing of one rule. The pause is visible everywhere, so nobody wonders why the
shutters stayed shut.

**Why this priority**: Valuable, but a household can live with switching rules off
one by one until it exists.

**Independent Test**: Pause all automations until tomorrow, confirm nothing fires
today and the overview says automations are paused, confirm they resume by
themselves tomorrow. Skip the next firing of one rule and confirm it fires again the
time after.

**Acceptance Scenarios**:

1. **Given** automations are paused until a date, **When** a rule's time comes before
   that date, **Then** it does not fire, and the skipped run is recorded as paused.
2. **Given** a pause ends, **When** the next rule time comes, **Then** rules fire
   again without anyone resuming them by hand.
3. **Given** the user skips the next firing of one rule, **When** that time comes,
   **Then** only that firing is skipped; the rule fires normally afterwards.
4. **Given** automations are paused, **When** anyone opens the app, **Then** the
   overview says so and offers to resume.

---

### Edge Cases

- **The system was off at the rule's time.** A rule that could not fire because the
  system was not running is recorded as missed. It is carried out late only if the
  system comes back within 10 minutes of the planned time; later than that, a
  shutter opening at the wrong hour is worse than one not opening.
- **The clock is not trustworthy.** The home computer has no battery-backed clock.
  After a power cut without a time source it may believe it is a different time.
  Rules MUST NOT fire while the time is known to be unreliable; the app says so.
- **Daylight saving time.** Time rules follow the local wall clock. A time that does
  not exist on the spring-forward day (e.g. 02:30) fires at the first minute that
  does; a time that occurs twice on the fall-back day fires once.
- **A calibration run is in progress on a target shutter.** That shutter is skipped
  and the skip is recorded with the reason; the rule's other shutters are commanded.
- **The radio bridge is unreachable when a rule fires.** The command is not
  delivered and is not queued for later; the run is recorded as failed for those
  shutters. This matches manual commands in feature 001.
- **A target shutter was removed from the configuration.** The rule keeps its other
  shutters. A rule with no shutters left says so and does not fire.
- **No days selected.** The rule can be saved but says it will never fire.
- **No sunrise or sunset on a given day** (only possible far north). The rule does not
  fire that day and the run is recorded as skipped with the reason.
- **A sun offset pushes the time past midnight** (e.g. sunset +5 h). The rule fires at
  the computed time, which belongs to the next calendar day, and the list shows it so.
- **The user moved the shutter by hand shortly before a rule fires.** The rule fires
  anyway. Rules are predictable; they do not guess what the person wanted.
- **Two rules fire in the same minute on the same shutter with different actions.**
  Both are carried out in a fixed, stated order, so the last one determines where the
  shutter goes. The app warns about this when the second rule is saved.

## Requirements *(mandatory)*

### Functional Requirements

**Rules**

- **FR-001**: Users MUST be able to create a rule with a name, a trigger, the days of
  the week it applies to, one or more target shutters (or "all shutters"), and an
  action: open, close, or a position between 0 and 100 %.
- **FR-002**: A trigger MUST be one of: a clock time; sunrise with an offset; sunset
  with an offset. Offsets MUST be whole minutes, before or after, up to 6 hours.
- **FR-003**: A sun trigger MAY carry a "not before" time, a "not after" time, or both;
  the firing time is the sun time with offset, moved into that window.
- **FR-004**: "All shutters" MUST mean every shutter configured at the time the rule
  fires, including ones added after the rule was created.
- **FR-005**: Users MUST be able to edit, enable, disable and delete rules. Disabling
  MUST keep every setting.
- **FR-006**: Rules MUST survive restarts of the system unchanged.
- **FR-007**: Days of the week MUST be selectable individually, with shortcuts for
  weekdays, weekend and every day.

**Firing**

- **FR-008**: An enabled rule MUST fire at its firing time on each selected day,
  whether or not any client is connected.
- **FR-009**: A firing MUST command each target shutter through the same path as a
  manual command, so every rule honours what a manual command honours: refusal during
  a calibration run, refusal when the bridge is unreachable, and the same animation
  and confidence display in every client.
- **FR-010**: A firing MUST NOT be retried or queued when a shutter could not be
  commanded.
- **FR-011**: When several rules fire in the same minute, they MUST be carried out in a
  deterministic order — by firing time, then by the order the rules were created — and
  that order MUST be the one the app states in its conflict warning.
- **FR-012**: A firing that falls in a period when the system was not running MUST be
  carried out if the system is running again within 10 minutes of the firing time,
  and otherwise recorded as missed.
- **FR-013**: Rules MUST NOT fire while the system's time is known to be unreliable.
  The app MUST show that automations are held for this reason, and firings in that
  period MUST be recorded as held, not silently dropped.
- **FR-014**: Time triggers MUST follow local wall-clock time across daylight saving
  changes as described in Edge Cases.

**Sun**

- **FR-015**: Sunrise and sunset MUST be computed on the home computer from the home
  location. No online service may be involved.
- **FR-016**: Users MUST be able to set the home location. Until it is set, sun rules
  cannot be created and existing sun rules do not fire, and the app says why.
- **FR-017**: Every sun rule MUST show the concrete time it will fire today (or next),
  so nobody has to calculate the offset in their head.
- **FR-018**: Computed sun times MUST be accurate to within 2 minutes of published
  times for the home location.

**Visibility**

- **FR-019**: The automations screen MUST show, for each rule, its next firing as a
  date and time, or the reason it will not fire.
- **FR-020**: Every firing MUST be recorded with the rule, the planned and actual time,
  and a per-shutter outcome: commanded, skipped (with reason), or failed (with reason).
  Missed, held and paused firings MUST be recorded too.
- **FR-021**: The record MUST be kept for at least 90 days and MUST be viewable per rule.
- **FR-022**: When a rule is saved that commands a shutter in the same minute as
  another enabled rule with a different action, the app MUST warn and state which rule
  wins.
- **FR-023**: A position action MUST be presented with the same honesty as a manual
  position: the app MUST say that intermediate positions are time estimates.

**Pausing**

- **FR-024**: Users MUST be able to pause all automations, either until they resume
  them or until a chosen date and time, after which rules resume by themselves.
- **FR-025**: Users MUST be able to skip only the next firing of a single rule.
- **FR-026**: While automations are paused or held, the overview MUST say so.

### Key Entities

- **Rule**: A named instruction: trigger, days of the week, targets, action, enabled
  flag, and an optional "skip next" marker. Created by a person, changed only by a
  person.
- **Trigger**: When a rule fires — a clock time, or sunrise/sunset with an offset and
  optional earliest/latest bounds.
- **Home location**: Where the house is, precise enough to compute sun times. One per
  installation.
- **Firing record**: One entry per planned firing: which rule, planned time, actual
  time (if any), overall status (fired, missed, held, paused, skipped), and a per-shutter
  outcome with reason.
- **Pause**: Whether all automations are paused, and until when.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can create a weekday morning rule in under one minute on a
  phone, without reading any help.
- **SC-002**: Rules fire within 5 seconds of their planned time on 99 % of firings
  over a test month on the simulator.
- **SC-003**: The next firing time shown for a sun rule matches the moment it actually
  fires to the minute, on every day of a simulated year for the home location.
- **SC-004**: With the internet disconnected for a week, every rule fires as it would
  with the internet connected.
- **SC-005**: After a restart, a power cut, or a daylight-saving change, no rule fires
  twice for the same planned time, and no rule fires while the clock is unreliable.
- **SC-006**: For any firing in the last 90 days, a person can find out within 30
  seconds which shutters were commanded and why any were not.
- **SC-007**: Nobody using the app ever sees an automated position presented as
  confirmed when it is an estimate.

## Assumptions

- The home location is entered once as coordinates or picked from a small offline list
  of places; it is not detected automatically, because detection would need a network
  service.
- The home computer normally gets its time from the local network (most home routers
  provide a time service). The "clock unreliable" state is for the times it cannot,
  such as a power cut with the router also down.
- Rules are shared by the household. As in features 001 and 002, the home network is
  the trust boundary; there are no user accounts and no per-person rules.
- Rules act on shutters, not rooms or groups. Grouping is a later feature; "all
  shutters" and multi-select cover this one.
- Out of scope: presence simulation (random times while away), weather or temperature
  triggers, triggers from other devices, and a public-holiday calendar. The pause and
  "skip next" cover holidays by hand.
- Manual commands always win in the moment: a person can drive a shutter at any time,
  including right after a rule. Rules do not "lock" a shutter.
- Firings are only as accurate as positions are: an automation to 30 % lands where
  feature 002's calibration puts it, and is shown as an estimate.
- Nothing in this feature has been checked on real hardware, and it does not need to
  be before it can be built: it only issues commands that features 001 and 002
  already issue.
