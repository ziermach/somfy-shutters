# Phase 1 Data Model: Travel-time calibration

**Date**: 2026-09-21 · **Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

## Where each thing lives

| Where | Holds | Why there |
|---|---|---|
| `config/shutters.toml` | manual travel times, if a person set any | Hand-authored, never rewritten by the app |
| `config/calibration.toml` | the derived value per shutter and direction | App-written, still plain text a person can read and back up |
| SQLite | every run, valid or rejected | History, not configuration |
| Memory | the run in progress | Meaningless after a restart, by design |

### Precedence

```
manual value in shutters.toml   >   measured value in calibration.toml   >   default_travel_seconds
```

Unambiguous on purpose: a person who types a number keeps it, and the interface says
which layer a shown value came from. Nothing the app measures can silently overwrite
something a human wrote.

## `config/calibration.toml`

Written whole whenever a value changes. No comments to preserve — it is the machine's
file.

```toml
# Written by somfy-shutters. Measured values; edit shutters.toml to override.
[wohnzimmer.up]
travel_seconds = 18.12
dead_seconds = 0.74
runs = 3
curve_k = 0.2
updated_at = "2026-09-21T19:14:02Z"

[wohnzimmer.down]
travel_seconds = 16.04
dead_seconds = 0.69
runs = 3
curve_k = 0.2
updated_at = "2026-09-21T19:16:41Z"
```

`curve_k` is the verification adjustment, bounded to ±0.8. Absent or 0 means the
linear behaviour of feature 001.

## Entity: MeasurementRun

| Field | Type | Notes |
|---|---|---|
| `id` | int | |
| `shutter_id` | string | |
| `direction` | `up` \| `down` | never shared between directions (FR-014) |
| `dead_seconds` | float | command to observed start of movement |
| `total_seconds` | float | command to observed arrival |
| `recorded_at` | timestamp | |
| `kind` | `guided` \| `confirmed` | `confirmed` is the one-tap variant, pending the amendment |
| `rejected` | string \| null | the reason, shown to the user; null when it counts |

Rejection reasons, each a testable rule:

| Reason | Rule |
|---|---|
| `dead_after_arrival` | `dead_seconds >= total_seconds` (FR-010) |
| `too_short` | `total_seconds < 1` |
| `implausible` | outside 0.5× to 2× the established value, where one exists (FR-011) |
| `disturbed` | a command or report for this shutter arrived from elsewhere mid-run (FR-029) |
| `abandoned` | no arrival press within twice the expected travel (FR-009) |

A rejected run is stored, not discarded — FR-012 wants it visible with its reason.

## Entity: Calibration

Derived, never hand-maintained. One per shutter and direction.

| Field | Derivation |
|---|---|
| `travel_seconds` | median of `total_seconds` over valid runs (FR-013) |
| `dead_seconds` | median of `dead_seconds` over the same runs |
| `runs` | how many valid runs support it |
| `curve_k` | accumulated verification answers, ±0.8 |
| `updated_at` | when the derived value last changed (FR-022) |
| `source` | `manual` \| `measured` \| `default` — which layer won |

## Entity: ActiveRun

In memory only. A run interrupted by a restart is simply lost, which is correct: its
arrival was never observed.

| Field | Notes |
|---|---|
| `shutter_id`, `direction` | |
| `started_monotonic` | the command instant; monotonic, immune to clock jumps |
| `dead_monotonic` | set by the first press, null until then |
| `phase` | `waiting_for_movement` \| `timing` |
| `disturbed` | set if anything else commands this shutter mid-run |

## Entity: CheckAnswer

| Field | Notes |
|---|---|
| `shutter_id`, `direction` | |
| `answer` | `too_high` \| `about_right` \| `too_low` |
| `recorded_at` | |

Each answer moves `curve_k` by 0.1, bounded. Stored so FR-026 can undo them: dropping
the answers returns `curve_k` to 0 and leaves the measurements untouched.

## The curve

```
position(p) = p − curve_k · sin(2πp) / 2π
```

`p` is elapsed over travel time. Verified: for every `k` in ±0.8 the curve passes
through exactly 0 and 1 and stays monotonic, so end points cannot drift (FR-025) and
the display never runs backwards. One answer shifts mid-travel by 1.6 points; the bound
caps the whole control at 12.7.

**A curve adjustment changes the shape of an estimate, not its confidence.** Position
stays `estimated`, `certain_at` untouched — the rule feature 001 applies to bridge
reports applies here too.
