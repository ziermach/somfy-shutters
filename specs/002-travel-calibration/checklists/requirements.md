# Specification Quality Checklist: Travel-time calibration

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-21
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

Two iterations.

**First pass, two failures.** SC-003 originally stated the mid-travel error as "within
about a percentage point", carried over from an early and wrong estimate. The mock's
explainer measured it: two presses leave roughly nine points, verification brings it to
about four. Corrected, and the claim now matches something that was actually computed.
FR-021 said the stored value should "use a rolling median of the last ten"; ten is an
implementation choice, so the requirement now states the property — follow a genuine
change, ignore a single outlier — and leaves the window to the plan.

**Second pass, one failure.** The passive-measurement story had no way to be tested
independently of the wizard, which breaks the rule that each story stands alone. Its
independent test now seeds a deliberately wrong value and drives the shutter through
the ordinary view, so it can be verified without User Story 1 having been used.

Constitution check: the feature touches principle III most directly — a measured value
does not make a position certain, only reaching an end stop does, and nothing here
changes that. Principle IV holds, since measurement is local by nature. FR-030 keeps
measured physical values in inspectable configuration, as the constitution requires.

Two things worth watching in planning:

- **FR-029** (discard a run disturbed from elsewhere) needs the system to notice a
  command it did not issue. For automations that is straightforward; for a physical
  remote it depends on CC1101 receive mode, which is open hardware question 4. The plan
  has to say what happens when that is switched off — most likely the run is recorded
  and later rejected as implausible, which is acceptable but should be deliberate.
- **FR-024 and FR-025 together** mean verification adjusts the shape of travel without
  moving its end points. That is a real modelling decision, not a detail, and it is the
  one place this feature could accidentally reintroduce a lie into the position display.
