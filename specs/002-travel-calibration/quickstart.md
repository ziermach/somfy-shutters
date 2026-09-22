# Quickstart: running and proving feature 002

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Everything here runs against the simulated house. That matters more than usual for this
feature: the simulator's per-window dead time and travel curve are exactly what the
calibration has to discover, and the app cannot see them. Convergence on values it was
never told is the whole proof.

**Most of this is now automated.** `backend/tests/integration/test_quickstart.py` walks
C1.1 to C1.8 and C3.1 to C3.4 against the running app, comparing against the simulator's
hidden truth where this document says to. Run it with:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_quickstart.py
```

The scenarios below remain worth doing by hand the first time, and **C4.1 has to be
done by eye whatever the tests say** — colour and wording can imply certainty without a
single field changing.

Setup as in [feature 001's quickstart](../001-mqtt-live-position/quickstart.md).

---

## Story 1 — measuring by watching

**C1.1 A run needs an end stop (FR-002, FR-003)**

Leave a shutter at 40 %, try to start a run. It must refuse with `not_at_end_stop` and
offer the drive there. Take the offer; that drive must not appear in the runs list.

**C1.2 Two presses (FR-004, FR-005, FR-007)**

Start a run on a shutter at an end stop. The screen says which press is expected, and
the elapsed time runs. Press when the graphic starts moving, press again when it stops.
The run appears with a dead time and a total.

**C1.3 Direction alternates (FR-006)**

The next run offered goes the other way, because that is where the shutter now is.
Three runs each way should mean six runs and no repositioning drives in between.

**C1.4 Median, not mean (FR-013)**

Do three runs in one direction, deliberately pressing very late on one of them. The
stored value must be the middle of the three, and the late run must still be listed.

```bash
curl -s localhost:8000/api/calibration | jq '.shutters[] | select(.id=="wohnzimmer")'
```

**C1.5 Implausible runs are rejected and shown (FR-011, FR-012)**

With a value established, do a run and press "arrived" almost immediately. It must come
back `rejected: "implausible"`, appear struck through with the reason, and leave the
stored value unchanged.

**C1.6 Abandoning (FR-008, FR-009)**

Start a run, press "moving", then abort. The shutter's position must become uncertain,
and the calibration screen must offer the drive to an end stop before the next run.

Separately: start a run and press nothing. After twice the expected travel the run must
abandon itself, record the reason, and **let go of the shutter** — until T040 this was
not implemented at all, and an unfinished run held the window hostage: every command
came back `measurement_in_progress` for good. Note that "expected travel" means the
app's current estimate, so an uncalibrated shutter waits twice the stated default.

**C1.7 It takes effect at once (FR-017)**

Without restarting anything, command that shutter from the normal view. The animation
must now finish together with the simulated shutter.

**C1.8 Convergence — the real test**

Take the uncalibrated shutter. Calibrate it with three runs per direction, pressing as a
person would. Then compare against the simulator's hidden truth:

```bash
curl -s localhost:8000/api/sim/truth | jq     # simulator only, never in production
```

The measured travel time should land within about a second of the simulator's, in both
directions, with the difference explained by reaction time rather than by a bug.

---

## Story 3 — verification

**C3.1 The midpoint check (FR-023, FR-024)**

Start a check on a calibrated shutter. It drives to the displayed 50 %. Compare against
the simulator's truth: because two presses cannot capture a non-linear travel, the real
position should be off by several points. Answer in the direction of the error. Repeat
three or four times and watch the gap close.

**C3.2 End points are untouchable (FR-025)**

After any number of answers, drive fully open and fully closed. The display must reach
exactly 100 % and exactly 0 %. This is the invariant that makes the whole control safe;
if it fails, the feature is dangerous, not just imprecise.

**C3.3 Undo (FR-026)**

Discard the verification. `curve_a` returns to 1 and the measured travel times are
unchanged.

**C3.4 The limit**

Keep answering in the same direction. The response must report `at_limit` once the bound
is reached, and the interface must stop inviting an answer that changes nothing.

---

## Story 2 — staying accurate with one tap

The story was amended before implementation. Passive recalibration cannot be built:
nothing observes when a travel ends, so the "measurement" would be the number we already
had — [research.md §1](./research.md) has the argument. What exists instead is a single
question after an ordinary travel.

**C2.1 The question appears after an end-to-end travel**

Drive a shutter fully open from fully closed with the app in the foreground. Once the
app believes it has arrived, it asks once whether it really has.

**C2.2 A partial travel asks nothing (FR-019)**

Drive to 60 %. No question, and nothing recorded — a travel on its own is not evidence.

**C2.3 The tap is the measurement**

Answer **Ja** a second or two after the question appears. The recorded run is longer
than the app's own estimate by roughly that delay, because the moment of the tap is what
counts, not the moment the app guessed.

**C2.4 Silence records nothing (FR-018a)**

Ignore the question. Nothing appears in the runs list, and nothing is inferred.

**C2.5 It does not nag**

Drive end to end again the same day. No second question for that shutter.

---

## Guarding against the thing most likely to go wrong

**C4.1 Calibrated must not read as known (constitution III)**

Calibrate a shutter completely. Then drive it to 50 % and look at the screen.

It must still say the position is an estimate, with the age of the last end stop. If
anything now reads as confirmed — a badge that turned green, the age disappearing,
wording that implies certainty — the feature has reintroduced exactly the lie the
project exists to avoid. This is a walkthrough, not an assertion, and it is the one to
do with your eyes.

**C4.2 Manual values win (precedence)**

Put `travel_up_seconds = 25` into `shutters.toml` for a calibrated shutter and restart.
The calibration screen must show 25 s with source `manual`, must say the measurement is
being overridden, and must not silently discard the measurement.

---

## Automated suite

```bash
cd backend && .venv/bin/python -m pytest      # includes the quickstart walkthrough
cd frontend && npm test                       # the wording in front of the user
```

The tests press with **jittered** reaction times, not at the exact right instant.
Pressing perfectly proves a precision no person will reproduce, and would hide the
whole reason the median is there.

What the frontend tests cover is narrow and deliberate: the phrases a person reads, and
a structural check that no screen shows a percentage without the confidence beside it.
They do not render anything.
