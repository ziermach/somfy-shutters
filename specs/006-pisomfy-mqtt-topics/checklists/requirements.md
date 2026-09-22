# Specification Quality Checklist: Speaking the radio bridge's current interface

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-22
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

- Decision taken with the user (2026-09-22): build on the **current** Pi-Somfy; older
  versions are not supported (FR-013).
- The spec avoids naming topics; the channel names are in the Assumptions and belong in
  the plan and the MQTT contract. For the record, from Pi-Somfy's `mqtt.py` (master,
  2026-08): `somfy/<id>/command` (OPEN/CLOSE/STOP), `somfy/<id>/set_position` (0–100),
  `somfy/<id>/position`, `somfy/<id>/state` (opening/closing/open/closed/stopped), all
  retained; `somfy/bridge/availability` (online/offline, last will); discovery under
  `homeassistant/cover/<bridge>_<id>/config` when enabled.
- Story 2 is P1 on safety grounds: on the current bridge a position request equal to its
  current belief is a no-op, so the old way of stopping would let the shutter run on.
- Must be implemented **before** feature 005, which depends on it.
