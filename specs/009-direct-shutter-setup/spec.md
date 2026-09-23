# Feature Specification: Setting up shutters directly in the app

**Feature Branch**: `009-direct-shutter-setup` (a separate branch at the owner's request, so
`main` can be tested as it is while this is built)

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Rolladen direkt aus der App anlegen und anlernen (Weg A): die App
verwaltet Rolladen über Pi-Somfys Befehlsschnittstelle (anlegen mit Adressvergabe durch
Pi-Somfy, PROG senden, umbenennen, löschen), geführter Ablauf wie im Mock (Name + geschätzte
Laufzeit → PROG an alter Fernbedienung halten → PROG senden → „Hat gewackelt?"; Stromreset mit
Stoppuhr ohne Fernbedienung), Pi-Somfys eigene Oberfläche wird nicht mehr gebraucht. Pi-Somfy
bleibt einziger Sender."

## User Scenarios & Testing *(mandatory)*

Feature 005 made the app notice shutters the radio bridge announces, but setting one up still
means leaving the app: creating it in the bridge's own web interface, pressing "Program"
there, restarting the bridge. That interface is technical, in English, and does not explain
what happens at the window. The household wants the app to be *the* interface — the bridge
becomes an invisible box.

One fact does not change: **the radio bridge stays the only sender.** It holds the rolling
codes; a second sender desynchronises every motor. So the app never transmits. It *asks the
bridge* to create a shutter, to send the programming signal, to rename or delete — and the
bridge does it. What this feature changes is only who presses the buttons: the person, in
the app, instead of in the bridge's interface.

### User Story 1 - Add and pair a shutter with its old remote, entirely in the app (Priority: P1)

A new window has a SIMU motor and its original remote. In the app the person chooses
"Rolladen hinzufügen", types a name and a rough travel time. The bridge creates the shutter
and gives it an address; the app shows it. The app then says: take the old remote, hold PROG
on its back until the shutter jogs — then press "PROG senden" here. The person does; the app
has the bridge send the programming signal and asks: "Hat der Rolladen gewackelt?" Yes: the
shutter is set up, on the overview, drivable at once, and the app offers to measure its
travel time. No: the app explains what usually went wrong and lets them try again.

**Why this priority**: This is the reason for the feature. Everything else is the same flow
for other situations.

**Independent Test**: With a bridge that accepts management requests, walk the flow: name,
travel time, "PROG senden", "Hat gewackelt". Confirm the bridge created the shutter with an
address it chose, received exactly one programming request per press, and that the new
shutter is drivable from the app immediately — without anybody opening the bridge's
interface or restarting it.

**Acceptance Scenarios**:

1. **Given** the person starts "Rolladen hinzufügen", **When** they enter a name and a travel
   time and continue, **Then** the bridge creates the shutter, the app shows the address the
   bridge assigned, and the pairing step opens.
2. **Given** the pairing step, **When** the person reads it, **Then** it tells them, in order,
   to take a remote that already controls this shutter, hold its PROG button until the
   shutter jogs, and only then press "PROG senden" — and that the motor listens for about two
   minutes.
3. **Given** the person presses "PROG senden", **When** the bridge has sent it, **Then** the
   app asks "Hat der Rolladen gewackelt?" with "Hat gewackelt" and "Nichts passiert".
4. **Given** "Hat gewackelt", **When** the person confirms, **Then** the shutter appears on the
   overview, drivable immediately, marked "Laufzeit nicht gemessen", and the app offers to
   measure it now.
5. **Given** "Nichts passiert", **When** the person answers, **Then** the app explains that the
   learning mode was not active or has expired, asks them to hold PROG again, lets them send
   again, and counts the attempts.
6. **Given** the person abandons the flow after the shutter was created but before it was
   paired, **When** they come back later, **Then** the shutter is shown as "nicht angelernt"
   with "Anlernen fortsetzen" and "Löschen" — never as a working shutter.

---

### User Story 2 - Pair without a working remote, with the power-cycle stopwatch (Priority: P2)

The remote is lost. From the pairing step the person chooses "Keine Fernbedienung mehr
vorhanden?". The app explains the power-cycle sequence and warns prominently. It cannot
switch the power itself, so it does the one thing it can: it times each step. The person
presses a button as they switch the circuit off, on, off and on again; the app shows a
stopwatch and whether each step landed inside its time window. When the motor jogs, the
flow continues with "PROG senden" as in story 1.

**Why this priority**: Common (remotes get lost) and error-prone by hand, because the
timing windows are narrow — but story 1 must exist first.

**Independent Test**: Walk the sequence, deliberately holding one step too short. Confirm the
app marks that step as outside its window, says to start again, and after a correct run
continues to "PROG senden".

**Acceptance Scenarios**:

1. **Given** the power-cycle route, **When** it opens, **Then** it warns that every motor on
   the same circuit enters learning mode at once and would learn the same sender, and that
   only the one circuit for this shutter may be switched.
2. **Given** the sequence runs, **When** the person presses the button at each switch, **Then**
   the app shows the elapsed time per step and each step's allowed window (off 2–8 s, on
   10–15 s, off 2–8 s, on).
3. **Given** a step outside its window, **When** the sequence ends, **Then** the app names that
   step and asks to start again; it does not offer "PROG senden" as if it had worked.
4. **Given** a correct sequence, **When** the motor jogs, **Then** the app continues to "PROG
   senden" and the question from story 1.

---

### User Story 3 - Remove a shutter everywhere at once (Priority: P2)

A window is replaced. The person removes the shutter in the app. As in feature 005 the app
names what goes with it (groups, rules, measurements). In addition it can now also delete the
shutter in the bridge, and — if wanted, with the old remote at hand — first make the motor
forget the bridge, so that no stale pairing is left behind.

**Why this priority**: Without it, removing still means a trip into the bridge's interface,
which is exactly what this feature ends.

**Independent Test**: Remove a paired shutter with "also forget in the motor". Confirm the
bridge sent one programming request while the motor was in learning mode, the bridge no
longer knows the shutter, and the app no longer lists it anywhere — not even as set aside.

**Acceptance Scenarios**:

1. **Given** a shutter set up in the bridge, **When** the person removes it, **Then** the
   confirmation offers "auch in der Funkbrücke löschen" (on by default) and "Motor soll die
   Funkbrücke vergessen" (off by default).
2. **Given** "Motor soll die Funkbrücke vergessen", **When** the person continues, **Then** the
   app guides them to put the motor into learning mode with a remote that controls it, then
   has the bridge send the programming signal, which removes the bridge from that motor.
3. **Given** removal with "auch in der Funkbrücke löschen", **When** it completes, **Then** the
   bridge no longer knows the shutter, and the app neither lists it as set aside nor offers it
   as new again.
4. **Given** the bridge refuses or cannot be reached, **When** the removal runs, **Then** the
   app removes nothing half-way silently: it says what was done and what was not, and offers
   to retry the bridge part.

---

### User Story 4 - One name, in the app and in the bridge (Priority: P3)

The person renames a shutter in the app; the bridge's name follows. Nobody has to keep two
lists in step.

**Why this priority**: Convenience. A mismatched name in a box nobody opens any more matters
little, but it should not drift.

**Independent Test**: Rename "Bad" to "Bad oben" in the app; confirm the bridge's entry for
that address now carries a corresponding name.

**Acceptance Scenarios**:

1. **Given** a shutter known to the bridge, **When** the person renames it in the app, **Then**
   the bridge's name for it is updated.
2. **Given** a name the bridge cannot store as typed (spaces, commas, umlauts), **When** it is
   saved, **Then** the bridge gets an acceptable form of it, and the person only ever sees the
   name they typed.

---

### User Story 5 - Still works when the bridge cannot be managed (Priority: P3)

The bridge is an older version, or its management access is not configured, or it is
temporarily unreachable. The app says so and falls back to feature 005's guide — the steps
in the bridge's own interface — rather than failing.

**Why this priority**: A safety net. It keeps the app usable on bridges this feature cannot
drive.

**Independent Test**: Run the app without management access to the bridge; confirm
"Rolladen hinzufügen" opens feature 005's guide with a note why.

**Acceptance Scenarios**:

1. **Given** no management access, **When** the person adds a shutter, **Then** the app explains
   that it cannot manage this bridge directly and shows the step-by-step guide of feature 005.
2. **Given** management access that stops working mid-flow, **When** a request fails, **Then**
   the app keeps what was done, says what failed, and offers retry or the guide.

---

### Edge Cases

- **PROG pressed with no motor in learning mode.** Nothing happens at the window; "Nichts
  passiert" leads to the retry path. The bridge's counter advanced, which is harmless.
- **Two motors in learning mode at once** (shared circuit, or a remote that controls several).
  Both would learn the same sender. The app warns before every "PROG senden" to have exactly
  one motor in learning mode.
- **PROG sent twice to an already paired motor while it is in learning mode** removes the
  pairing again. After "Hat gewackelt" the app does not offer another "PROG senden" for that
  shutter unless the person starts pairing again.
- **The bridge restarts or disconnects during the flow.** The created shutter persists in the
  bridge; the flow resumes at the pairing step when the bridge is back.
- **A name already used in the app** is refused at the first step, before anything is created
  in the bridge.
- **Hand-configured shutters** (from the configuration file) are never created, renamed or
  deleted in the bridge by the app.
- **A shutter created in the bridge's own interface anyway** is still noticed as new, as in
  feature 005.
- **Several people set up shutters at the same time.** Each flow addresses the shutter it
  created; programming requests never go to another flow's shutter.

## Requirements *(mandatory)*

### Functional Requirements

**The bridge stays the only sender**

- **FR-001**: The system MUST NOT transmit radio signals itself. Creating, programming,
  renaming and deleting are requests to the radio bridge, which performs them.
- **FR-002**: Addresses MUST be assigned by the bridge; the app MUST NOT choose or invent one.
- **FR-003**: Every management request to the bridge MUST be recorded in the audit record of
  feature 008, with who asked.
- **FR-004**: Managing shutters MUST require the "configure" ability of feature 008; a device
  without it sees no management actions.
- **FR-005**: Whatever credential the bridge needs for management MUST stay on the server and
  never reach a client.

**Adding and pairing (US1)**

- **FR-006**: The person MUST be able to add a shutter by entering a name (1–40 characters,
  unique in the household) and an estimated travel time (1–600 seconds, default 20); the bridge
  then creates it and the app shows the address the bridge assigned.
- **FR-007**: The pairing step MUST instruct, in order: take a remote that controls this
  shutter, hold PROG until the shutter jogs, then press "PROG senden"; it MUST state that the
  learning mode lasts about two minutes and that exactly one motor may be in learning mode.
- **FR-008**: "PROG senden" MUST cause exactly one programming request to the bridge for this
  shutter per press, followed by the question "Hat der Rolladen gewackelt?".
- **FR-009**: "Nichts passiert" MUST explain the likely cause, allow another attempt, and show
  the attempt count.
- **FR-010**: After "Hat gewackelt", the shutter MUST be part of the household and drivable
  from the app immediately, without anybody restarting the bridge or opening its interface,
  and MUST be offered for travel-time measurement.
- **FR-011**: A shutter created but not confirmed as paired MUST be shown as "nicht angelernt",
  MUST NOT be part of "all shutters", groups or automations, and MUST offer "Anlernen
  fortsetzen" and "Löschen".

**Without a remote (US2)**

- **FR-012**: The pairing step MUST offer the power-cycle route, with the warning about shared
  circuits shown before the sequence can start.
- **FR-013**: The power-cycle route MUST time each step the person marks, show each step's
  window (off 2–8 s, on 10–15 s, off 2–8 s, on), flag any step outside it, and offer "PROG
  senden" only after a sequence with every step inside its window.

**Removing (US3)**

- **FR-014**: Removing a bridge shutter MUST offer to delete it in the bridge too (default on)
  and to make the motor forget the bridge first (default off), in addition to what feature 005
  already names.
- **FR-015**: "Motor soll die Funkbrücke vergessen" MUST guide the person to put the motor in
  learning mode and then send one programming request for that shutter.
- **FR-016**: A removal whose bridge part fails MUST report which parts were done and which were
  not, and MUST offer to retry the bridge part; it MUST NOT leave the shutter looking removed
  from the bridge when it is not.

**Renaming (US4)**

- **FR-017**: Renaming a bridge shutter in the app MUST rename it in the bridge; names the
  bridge cannot store MUST be translated to an acceptable form, invisible to the person.

**Fallback (US5)**

- **FR-018**: Without working management access to the bridge, adding MUST fall back to feature
  005's guide, with a note why; the app MUST say which management actions are unavailable.

### Key Entities

- **Bridge shutter record**: What the bridge stores per shutter — its address (chosen by the
  bridge), its own name, its travel time. Created, renamed and deleted only through requests.
- **Setup session**: One person adding one shutter — the shutter it created, the chosen route
  (remote or power cycle), the attempts, whether pairing was confirmed. Resumable.
- **Pairing state of a household shutter**: not paired (created, never confirmed) or paired.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With a working remote, a person can go from "Rolladen hinzufügen" to driving the
  new shutter in under 5 minutes, without opening the bridge's interface or restarting it.
- **SC-002**: Zero visits to the bridge's own interface are needed to add, pair, rename or
  remove a shutter on a bridge with management access.
- **SC-003**: Every programming signal that reaches a motor is sent by the bridge; the app
  transmits nothing, verifiable by the absence of any radio component in the app.
- **SC-004**: Each "PROG senden" results in exactly one programming request, and each is
  visible in the audit record with the person who asked.
- **SC-005**: A power-cycle sequence with a step outside its window is flagged in 100% of runs
  and never leads straight to "PROG senden".
- **SC-006**: After removal with "auch in der Funkbrücke löschen", the shutter appears nowhere —
  not in the app, not as set aside, not as new — including after a bridge restart.

## Assumptions

- **Constitution change needed.** Principle II today allows only the bridge's message topics
  and forbids calling its web interface. This feature needs an amendment that allows the
  bridge's management requests (create, program, rename, delete) from the server side.
  Principle I — the bridge is the only sender — stays untouched.
- **The bridge is our own fork.** Today's Pi-Somfy offers creating, programming, renaming and
  deleting only through its web interface, and announces a new shutter only after a restart.
  The household therefore runs a fork of Pi-Somfy that offers these on the same message channel
  the app already uses, and announces a new shutter at once. The changes are meant to be offered
  upstream. An unforked bridge falls back to story 5.
- **The power-cycle timings** (off 2–8 s, on 10–15 s, off 2–8 s, on) are the usual SIMU/Somfy
  sequence and come from the mock; they are to be confirmed on the actual motors. Whether the
  sequence also erases the motor's other senders depends on the motor model and is stated as
  a caution, not a certainty.
- The travel time entered at creation is given to the bridge as its own travel time. Keeping
  it in step with later measurements (feature 002) is out of scope here.
- Feature 005 stays: announcements are still how shutters created elsewhere are noticed, and
  its guide is the fallback.
- Out of scope: pairing additional remotes, factory-resetting a motor, setting end stops or the
  "my" position, and changing a shutter's address.
