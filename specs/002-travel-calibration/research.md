# Phase 0 Research: Travel-time calibration

**Date**: 2026-09-21 · **Spec**: [spec.md](./spec.md)

---

## 1. User Story 2 cannot be built as written

**Finding**: Passive recalibration is impossible with this hardware. FR-018 asks the
system to record how long an uninterrupted end-to-end travel took. Nothing in the
system observes when a travel ends.

The chain is circular:

```
expected_arrival = started_at + configured_travel_time   (tracker.py:140)
settle happens when now >= expected_arrival              (tracker.py:164)
```

So "how long the travel took" is, by construction, exactly the number we already had.
Recording it teaches us nothing and would make the value look confirmed while it is
merely repeated.

Everything else that might observe an arrival fails too:

| Candidate | Why it does not work |
|---|---|
| The motor | Somfy RTS is one-way. It has no transmitter at all. |
| Pi-Somfy's `set_state` | Its own dead reckoning from *its* configured travel time. Disagreement tells us the two configurations differ, not which is right. |
| CC1101 receive mode | Hears other remotes' *commands*. Says nothing about arrival. |
| Power monitoring | Would work — current drops at the end stop — but it is extra hardware per window, which constitution principle V rules out. |

**I asserted the opposite earlier in this project**, twice, including in the mock's
wording and in the README: "every uninterrupted end-stop-to-end-stop trip re-measures
for free". That was wrong. There is no free measurement, because there is no observer.

**Decision**: implement User Story 1 and User Story 3 as specified. Replace User Story 2
with something that works and costs almost as little.

### What replaces it: one-tap confirmation

The cheapest real observation is still a person, but it does not have to be two presses
and a wizard. When a travel that ran end to end finishes while somebody has the app
open, ask once, unobtrusively:

> Wohnzimmer sollte jetzt oben sein. Stimmt das? **Ja** · **Noch nicht**

- **Ja** at that moment is a real arrival observation, accurate to their reaction time,
  and yields a measurement exactly like a guided run's second press.
- **Noch nicht** leaves the prompt up; the tap that follows when it does arrive is the
  measurement.
- Ignoring it records nothing.

One tap, no stopwatch, no screen to navigate to. Asked only when it is worth asking —
after a full travel, only while the app is in the foreground, at most once per shutter
per day, and preferentially for shutters whose stored value rests on few runs.

That keeps the property User Story 2 was actually after — the values stay true over
months without anyone deliberately recalibrating — while being honest that a human
observation is required. The acceptance criteria change: SC-004's "with no user
involvement" becomes "with one tap per confirmation", and FR-018 to FR-020 need
rewriting. **This requires a spec amendment**; it is recorded here rather than silently
implemented.

---

## 2. Where measured values live

**Decision**: three layers, with explicit precedence.

| Layer | Written by | Wins over |
|---|---|---|
| Manual value in `shutters.toml` | a person | everything |
| Measured value in `config/calibration.toml` | the app | the default |
| `default_travel_seconds` | a person, once | nothing |

**Rationale**: FR-030 wants measured values inspectable and correctable by hand, but the
app rewrites them as measurements accumulate. Rewriting the hand-edited
`shutters.toml` would destroy its comments and the ordering a person chose. Splitting
the file keeps the human's file human and the machine's file machine-written, and it
gives an unambiguous answer to "I typed 18.2 and the app changed it" — it cannot,
because a manual value wins and the interface says so.

Individual runs stay in SQLite. They are history, not configuration, and nobody hand-
edits a list of measurements.

**Alternatives considered**: one file, rewritten by the app — loses comments and makes
manual correction a race. Everything in SQLite — satisfies the letter of FR-030 only if
a UI exists to inspect it, and makes a backup useless without the app.

---

## 3. Verification without moving the end points (FR-024 and FR-025)

**Decision**: one shape parameter `k` per shutter and direction, applied as

```
position(p) = p − k · sin(2πp) / 2π        p = elapsed / travel_time, k ∈ [−0.8, 0.8]
```

`k = 0` is the linear behaviour of feature 001. For any `k`, `position(0) = 0` and
`position(1) = 1` **exactly** — the end points are invariant by construction, not by a
clamp that could be forgotten. The maximum deviation sits at the quarter points and is
`k / 2π`, so `k = 0.55` moves mid-travel by about 8.8 points.

Each "zu hoch" or "zu tief" nudges `k` by 0.1, which moves mid-travel by 1.6 points —
verified, along with the invariants: for every `k` in the band, `f(0)` is exactly 0,
`f(1)` is exactly 1, and the curve stays monotonic, so the displayed position never runs
backwards. Three or four answers cover the roughly 5 points needed to get from what two
presses leave to what SC-003 asks for; the bound at 0.8 is reached after eight, and
caps the whole control at 12.7 points.

This is the same curve family the simulator uses for its hidden truth. That is a
convenience, not cheating — the simulator's `k` is per window and unknown to the app,
and a correct implementation has to converge on it from answers alone.

**What it must not become**: a curve adjustment changes the *shape* of the estimate. It
does not make the position better known. Confidence stays `estimated` and `certain_at`
is untouched — the same rule feature 001 applies to bridge reports.

**Alternatives considered**: piecewise-linear through a measured midpoint — needs a
third press, which makes accuracy worse here (the curve is symmetric, so a halfway mark
lands where the error is already zero). A polynomial fit — more parameters than three
taps can support.

---

## 4. Noticing that a run was disturbed (FR-029)

**Decision**: detect what is detectable, and let plausibility catch the rest.

| Disturbance | Detected how |
|---|---|
| Another client commands the shutter | In process — the tracker sees every command it issues |
| A scheduled automation | Same |
| A physical remote, with CC1101 receive on | A report stream arrives for a shutter we believe is under measurement |
| A physical remote, receive off | **Not detectable.** The run finishes with an implausible time and is rejected by FR-011 |

The last row is an accepted limitation, not an oversight. It depends on open hardware
question 4, and the failure mode is benign: a disturbed run produces a wrong duration,
the plausibility band rejects it, and the user sees it struck through with a reason.

---

## 5. Guided-run mechanics

Settled, mostly from the mock's explainer:

| Question | Answer |
|---|---|
| Presses per run | Two. A third makes it worse; four is more than anyone will do across eight windows |
| Runs per direction | Three suggested, one accepted, median taken |
| Direction order | Alternating, starting from wherever the shutter already rests |
| Plausibility band | Total between 0.5× and 2× the established value, where one exists |
| Abandon after | Twice the expected travel time |
| Reaction time | Not modelled or subtracted. The median is the mitigation |
| Time source | Monotonic, so a daylight-saving jump mid-run cannot corrupt a measurement |

**On not subtracting reaction time**: a constant offset could be estimated and removed,
and it is tempting because the bias is systematic. It is rejected because the dead-time
press and the arrival press carry the same bias in opposite directions for the travel
duration, which already cancels most of it, and because an unverifiable correction
applied to a measurement is exactly the kind of invented precision this project avoids.
