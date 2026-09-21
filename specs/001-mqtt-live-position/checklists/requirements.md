# Specification Quality Checklist: Live position and movement

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

Two iterations were needed.

**First pass, three failures.** The spec named MQTT topics, WebSocket and SQLite
directly, which is technology, not requirement — those belong in `plan.md`. FR-012 said
the animation must not wait for `set_state`, naming a protocol detail; it now says it
must not wait for any report from the radio bridge. SC-002 was stated as a millisecond
budget on an internal message path rather than as something a person can observe; it now
measures the gap between the animation finishing and the physical shutter finishing.

**Second pass, one failure.** The direction of travel was carried as a
[NEEDS CLARIFICATION] marker, but a reasonable default exists: the interface fixes
100 % as fully open, and translating to whatever the radio bridge expects is a single
point of implementation. Recorded in Assumptions instead, so the spec does not block on
an open hardware question.

Constitution check: the spec asserts the radio boundary (FR-003), the confidence
language (FR-006, FR-007, FR-011), animation from configured travel time (FR-012,
FR-013), travel times in configuration (FR-014), clients never on the bus (FR-019) and
offline operation (FR-024). No conflicts found.

One item worth watching in planning: FR-017 requires reconciling an incoming position
report with the local estimate "without jumping". That is a real design problem, not a
detail — the report is itself an estimate produced by the radio bridge from its own
configured travel time, so it is not more authoritative than the local one.
