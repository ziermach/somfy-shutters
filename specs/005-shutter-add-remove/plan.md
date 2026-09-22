# Implementation Plan: Adding and removing shutters

**Branch**: `main` (single-developer repository, no feature branches) | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-shutter-add-remove/spec.md`

## Summary

The set of shutters stops being a hand-copied list. The MQTT adapter reads Pi-Somfy's own
announcements (Home Assistant discovery); a new `Roster` service keeps what the bridge
announces apart from what the household has confirmed, and mutates the one list every part of
the app already reads (`settings.shutter`) when a shutter is confirmed or removed. Adding is a
guided walk through Pi-Somfy's interface — which, as its code shows, announces a new shutter
only after a restart, so the guide includes one. Removing names its consequences, cascades
through groups, rules, calibration and state, and sends nothing to the bridge. A shutter the
bridge no longer announces after its next restart is marked forgotten and refused commands.
Hand-configured shutters keep working unchanged.

## Technical Context

**Language/Version**: Python 3.11, TypeScript/Svelte 5 — unchanged

**Primary Dependencies**: none new

**Storage**: existing SQLite database; one new table, `household_shutter`

**Testing**: pytest (adapter parsing without a broker; roster unit tests; integration against
the simulator, which gains sim-only endpoints modelling the bridge's own interface); vitest
for guide wording; the local-Mosquitto walk from feature 006 extended with announcements

**Target Platform**: Raspberry Pi next to Pi-Somfy v3.1+ with discovery enabled (its default)

**Project Type**: web application — backend and frontend

**Performance Goals**: an announced shutter visible in an open guide within 5 s (FR-008);
forgotten marked within 60 s of a bridge restart (FR-017)

**Constraints**: never publish to the bridge's topics beyond `command`/`set_position`; never
request the bridge's web pages (a link the person opens is fine); never write `shutters.toml`;
new shutters invisible to "all shutters", groups and automations until confirmed

**Scale/Scope**: ≤ 20 shutters; a handful of announcements

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. Pi-Somfy owns the radio** | The app never sends PROG, never creates or deletes shutters in the bridge. The person does those in Pi-Somfy's interface; the app only explains. |
| **II. MQTT is the only integration boundary** | Still MQTT only, and nothing is published beyond `command`/`set_position`. **But** the principle lists the inbound topics exhaustively, and the discovery topic `homeassistant/cover/+/config` is not among them. → **Amendment 1.1.0 → 1.2.0**: add the bridge's discovery announcements as an inbound topic; rule and rationale unchanged. A link to Pi-Somfy's web interface that the *person* opens is not the app calling its routes. |
| **III. Honest position state** | New shutters start unknown; a forgotten shutter is shown as such and cannot be commanded — no graphic pretending a deleted shutter still works. |
| **IV. Local-first** | Announcements come over the local broker. |
| **V. Single-Pi simplicity** | No new component or dependency. |
| **Interface rule "RTS addresses … referenced by the app, never invented"** | Addresses are read from the bridge's announcements (or `shutters.toml`), never generated. The amendment clarifies that learning them from announcements is how they are referenced. |
| **Measured values in configuration** | Addresses learned from the bridge are stored in the app's database, which is configuration state the app owns — not logic. `shutters.toml` stays untouched and wins on conflict. |

**Result**: pass, conditional on the amendment (task-listed first). No complexity to justify.

## Project Structure

### Documentation (this feature)

```text
specs/005-shutter-add-remove/
├── plan.md
├── research.md          # what the bridge announces and when; roster design
├── data-model.md        # household_shutter, announcements, roster state, removal cascade
├── quickstart.md        # simulator, local Mosquitto, Pi
├── contracts/
│   ├── rest.md          # /api/roster, confirm, rename, removal preview, remove, restore; WS
│   └── mqtt.md          # the discovery topic, inbound only
└── tasks.md
```

### Source Code

```text
.specify/memory/constitution.md          # principle II: discovery inbound (1.2.0)

backend/src/somfy_shutters/
├── roster.py              # NEW — Roster: announcements, new/active/set-aside/forgotten, confirm, remove
├── roster_store.py        # NEW — household_shutter table
├── bridge/base.py         # Report kind "announcement" (address, name, web_url)
├── bridge/mqtt.py         # subscribe homeassistant/cover/+/config; parse command_topic
├── bridge/sim.py          # announce on start and on reconnect; add/delete/restart as the bridge
├── tracker.py             # add_shutter / remove_shutter
├── commands.py            # ShutterForgotten
├── automation/store.py    # remove_shutter from rule targets
├── automation/engine.py   # skipped: forgotten
├── api/roster_routes.py   # NEW — contracts/rest.md
├── api/rest.py            # sim endpoints; PATCH rename; forgotten → 409
├── api/serialize.py       # forgotten, origin
├── api/ws.py              # roster frame; snapshot on roster change
├── config.py              # optional bridge.web_url
└── main.py                # wire Roster; build settings.shutter from config + table

frontend/src/
├── lib/roster.svelte.ts          # NEW — roster store
├── lib/roster.ts                 # NEW — guide steps and wording (testable)
├── routes/Shutters.svelte        # NEW — manage: active, new, set aside, forgotten
├── routes/AddShutter.svelte      # NEW — the guide, with the power-cycle route
├── components/RemoveShutter.svelte  # NEW — consequences + confirm
├── components/ShutterCard.svelte, routes/Detail.svelte  # forgotten state, remove entry
└── routes/Overview.svelte, App.svelte                    # "Neuer Rolladen gefunden" hint, navigation
```

**Structure Decision**: existing layout. Roster logic in its own module because it owns a
cross-cutting lifecycle (add/remove across tracker, groups, rules, calibration); the adapter
change stays inside `bridge/`.

## Design notes

- **Order**: amendment → announcements in the adapter and the simulator → roster store and
  service, building `settings.shutter` at start → confirm (US1/US2 share it) → guide UI →
  removal cascade → forgotten → power-cycle route → docs.
- **The 30-second window** after each bridge `online` decides forgotten (research §2). A
  bridge that restarts while the app is down is seen as an `online` transition when the app
  connects; its announcements then arrive retained, so nothing is marked forgotten until a
  restart the app witnesses — deliberately erring towards "still known".
- **Snapshot after roster changes** keeps every open client's overview right without new
  client code (research §9).
- **Guide text** lives in `lib/roster.ts`, tested, and names Pi-Somfy's own labels ("Add
  shutter", "Program") as its current interface shows them.

## Complexity Tracking

None.

## Risks

- **Stale retained announcements** of shutters deleted in the bridge long ago appear as new on
  a fresh app. Mitigated by "set aside" and a guide hint; clearing them is the bridge's job.
- **Discovery switched off** in the bridge: nothing is announced. `announcements_seen: false`
  lets the guide say exactly that; hand configuration keeps working.
- **Bridge versions that start announcing on add** would simply make the guide's restart step
  unnecessary; the flow still works.
- **Hardware**: the restart requirement and the id spelling are confirmed from code, not on a
  device; quickstart C.
