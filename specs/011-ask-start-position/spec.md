# Feature Specification: Asking where a new shutter stands

**Feature Branch**: `main` (single-developer repository)

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: "Wenn ein neuer Rolladen hinzugefügt wird, geht das Tool davon aus,
dass er zu ist — frag doch einfach am Anfang den User."

## User Scenarios & Testing *(mandatory)*

When a person names a shutter the radio bridge announced (feature 005), the app does not know
where it stands. It then takes the first position it hears from the bridge — and for a shutter
the bridge has just created, that is the bridge's own starting value, "closed", which nobody
observed. The overview shows a closed window that may be wide open. Worse, the bridge believes
the same thing, and a later "go to 50 %" is computed from that wrong belief, so the shutter
stops somewhere else.

The person standing at the window knows. The app should ask them, once, while naming the
shutter — and where the answer cannot be trusted, offer one drive to an end stop, which is
the only position the radio system can know for sure.

### User Story 1 - The person says where the new shutter stands (Priority: P1)

While naming a new shutter, the app asks "Wo steht der Rolladen gerade?" with three answers:
"Ganz offen", "Ganz zu", "Irgendwo dazwischen / weiß nicht". The answer becomes the shutter's
starting position in the app, marked as given by the person rather than observed. Nothing is
sent to the bridge by answering.

**Why this priority**: It removes the visible error — a window shown closed that is open —
with one tap, at the moment the person is looking at the window anyway.

**Independent Test**: Confirm a new shutter answering "Ganz offen"; the overview shows it
open as an estimate, not as observed. Answer "weiß nicht"; it shows as position unknown.
Check that no message reached the bridge in either case.

**Acceptance Scenarios**:

1. **Given** a new shutter is being named, **When** the naming step is shown, **Then** it
   asks for the current position with the three answers, and naming cannot finish without
   one of them.
2. **Given** the person answers "Ganz offen" or "Ganz zu", **When** the shutter joins the
   household, **Then** its position is that end, shown as an estimate given by the person.
3. **Given** the person answers "weiß nicht", **When** the shutter joins, **Then** its
   position is shown as unknown — never as a number.
4. **Given** any answer, **When** it is recorded, **Then** nothing is sent to the bridge.
5. **Given** the shutter has joined, **When** the bridge's stored starting value arrives,
   **Then** it does not overwrite the person's answer.

---

### User Story 2 - One drive to an end stop makes app and bridge agree (Priority: P2)

The bridge keeps its own belief of each shutter's position and computes intermediate targets
from it. If the person's answer differs from the bridge's belief, or the person does not
know, the app offers right after naming: "Einmal ganz öffnen" / "Einmal ganz schließen" —
one full travel, after which app and bridge both know the position for sure. The person can
skip it; the app then keeps telling them, on that shutter, that intermediate positions may
be off until it has travelled to an end once.

**Why this priority**: Story 1 fixes what the app shows; this fixes what the shutter does.
It needs a deliberate movement at the window, so it is offered, never automatic.

**Independent Test**: Name a shutter answering "Ganz offen" while the bridge believes
"closed"; the offer appears. Accept "Einmal ganz öffnen"; afterwards app and bridge agree and
the hint is gone. Repeat and skip; the hint stays until the shutter reaches an end by any
command.

**Acceptance Scenarios**:

1. **Given** the answer differs from the bridge's belief, or is "weiß nicht", **When** naming
   finishes, **Then** the app offers one full opening or closing, explaining why.
2. **Given** the answer matches the bridge's belief, **When** naming finishes, **Then** no
   offer is shown.
3. **Given** the person accepts, **When** the travel completes, **Then** the position counts
   as reached at that end, exactly as any full open or close does today.
4. **Given** the person skips, **When** they open that shutter, **Then** a hint says
   intermediate positions may be off until it has once gone fully open or closed; the hint
   disappears after the first full travel by any means.
5. **Given** the bridge is unreachable, **When** naming finishes, **Then** the offer is not
   shown and the hint is.

---

### Edge Cases

- **The bridge's belief is not known yet** (no stored value arrived). Treat it as differing:
  offer the drive.
- **A shutter restored from "set aside"** (feature 005) keeps its previous position and is not
  asked again.
- **Hand-listed shutters** (configuration file) are not named in the app, so they are not asked;
  they behave as today.
- **The person answers wrongly.** The first full open or close corrects it, as it corrects any
  estimate today.
- **A calibration run starts right after naming.** Calibration begins from an end stop
  (feature 002) and makes the drive offer redundant; the offer is not shown when the person
  chose to calibrate at once.
- **Several shutters named in a row.** Each is asked on its own.
- **The simulator.** Same questions; the simulated bridge's belief is used for the comparison.

## Requirements *(mandatory)*

### Functional Requirements

**Asking**

- **FR-001**: Naming a new shutter MUST include the question of where it stands, with exactly
  three answers: fully open, fully closed, unknown.
- **FR-002**: Naming MUST NOT complete without an answer.
- **FR-003**: Answering MUST NOT send anything to the bridge.

**What the answer does**

- **FR-004**: "Fully open" and "fully closed" MUST set the shutter's position to that end as an
  estimate whose source is the person, never as observed or certain.
- **FR-005**: "Unknown" MUST leave the position unknown and shown without a number.
- **FR-006**: A stored (old) position report from the bridge MUST NOT overwrite a position the
  person gave. Live reports keep their existing rules.

**Bringing the bridge along**

- **FR-007**: When the answer differs from the bridge's belief, or is "unknown", or the
  bridge's belief is not known, the app MUST offer one full opening or closing right after
  naming, with a one-sentence reason. It MUST NOT start it without the person's choice.
- **FR-008**: When the answer matches the bridge's belief, the offer MUST NOT be shown.
- **FR-009**: If the offer is skipped or cannot be shown, the shutter MUST carry a visible hint
  that intermediate positions may be off, until its first full opening or closing by any means.

**Unchanged**

- **FR-010**: Hand-listed shutters, restored shutters and all existing shutters MUST behave as
  before.

### Key Entities

- **Starting answer**: The person's statement at naming time — fully open, fully closed or
  unknown. Becomes the first position estimate; not kept as history beyond that.
- **Bridge belief**: The position the bridge last stored for the shutter. Read, never written,
  by this feature.
- **Out-of-step hint**: Per shutter, set when app and bridge may disagree, cleared by the first
  full travel to an end.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A newly named shutter never appears closed in the app unless the person said so
  or it was observed closed.
- **SC-002**: Naming a shutter including the position question takes one extra tap.
- **SC-003**: After accepting the offered drive, the first intermediate target the person
  chooses ends within the usual estimate tolerance of that target.
- **SC-004**: Zero messages reach the bridge from answering the question.

## Assumptions

- The bridge sets a shutter it has just created to "closed" in its own records, and that value
  reaches the app as stored old news; this is what made new shutters appear closed. To be
  confirmed on the real bridge.
- The bridge offers no way to correct its belief without moving the shutter, so a full travel
  is the only way to make both agree (constitution: only end stops are reliable).
- The naming step is feature 005's; this feature adds one question to it.
