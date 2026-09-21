# Phase 0 Research: Live position and movement

**Date**: 2026-09-21 · **Spec**: [spec.md](./spec.md)

Five questions had to be settled before a design could be written. Four were open
choices; the fifth (FR-017) is the one genuine design problem in this feature.

---

## 1. MQTT client library

**Decision**: `aiomqtt`, pinned to the 2.5.x line, driven from a FastAPI `lifespan`
context manager.

**Rationale**: The backend is async anyway because it serves WebSockets, and the
guidance is consistent — async application, async client. `aiomqtt` wraps paho in
`async with` plus an async iterator over messages, so the subscriber is an ordinary
task rather than a callback thread that then has to hand work back to the event loop.
Pinned to 2.x because 3.x swapped the underlying protocol library from paho to a sans-io
implementation; that is a change worth adopting deliberately, not on a first build.

**Alternatives considered**:

- **paho-mqtt 2.x directly** — the callback API runs in its own thread, so every message
  needs `run_coroutine_threadsafe` to reach the event loop. Extra machinery for no gain
  here.
- **gmqtt** — capable, but less active and the API is callback-shaped again.

**Correction to a common claim**: several older write-ups say FastAPI cannot take a
lifespan context manager and that dependency injection is the workaround. That has not
been true since FastAPI 0.93 — `FastAPI(lifespan=...)` is the supported way and is what
this plan uses.

---

## 2. Frontend framework

**Decision**: Svelte 5 with Vite, built to static files and served by the backend.

**Rationale**: The constitution allows either. Three things decide it here. The app is
small — four screens — so React's ecosystem advantage buys little, while its boilerplate
is paid on every component. The animation drives one number per shutter at 60 fps
straight into an SVG attribute, which Svelte does as a direct DOM write with no
reconciliation in between. And the bundle is served from a Raspberry Pi to phones on
home Wi-Fi, where a smaller payload is felt. There is also no team to hire into, which
is React's strongest argument.

**Alternatives considered**:

- **React** — the safe default, and the right call with more developers or a longer-lived
  team. Rejected on boilerplate-per-value for a solo home project.
- **No framework, plain DOM** — genuinely viable, and the mock proves it. Rejected
  because the rule editor's form state is where hand-rolled DOM code starts to rot.

**Consequence for Principle IV**: the mock pulls fonts from Google Fonts. The real
frontend must **self-host every font and asset** — no external origin may sit in the
load path, or the app breaks exactly when the internet does.

---

## 3. Where commands and state each travel

**Decision**: commands go over REST, state comes back over a WebSocket.

**Rationale**: They have different shapes. A command is a one-shot request that wants a
status code and an error message; `curl` should be able to issue one during bring-up.
State is a continuous push to every open client. Forcing commands through the socket
would mean inventing request/response correlation on top of it for no benefit.

**Alternatives considered**:

- **Everything over WebSocket** — fewer moving parts, but needs hand-rolled correlation
  ids and makes the system hard to poke at from a shell.
- **Server-Sent Events instead of WebSocket** — simpler and sufficient today, since the
  channel is one-directional. Rejected narrowly: a later feature will likely want the
  client to speak (live drag of a position slider), and SSE cannot.

---

## 4. The simulator, and where the seam goes

**Decision**: one port, `ShutterBridge`, with two adapters — `MqttBridge` for the real
Pi-Somfy and `SimBridge` for a simulated house. The backend never imports either
directly; the adapter is chosen at startup by configuration.

**Rationale**: The feature cannot be developed against real hardware for most of its
life — rolling codes, neighbours, night time, and the fact that the shutters are not
paired yet. The simulator is therefore not scaffolding but a first-class component, and
it is what makes the hard cases reachable at all: drift, a command lost in the air, a
restart mid-travel, a report that contradicts the estimate.

The simulator models what the real motor does and the app does not know: a soft-start
dead time, a non-linear travel curve, different speeds per direction, and an optional
"command lost" rate. That asymmetry is the point — if the app could see the simulator's
internals it would prove nothing.

**Alternatives considered**:

- **Mock the MQTT client in tests only** — tests would pass while the app remained
  undevelopable without hardware.
- **Run a real Mosquitto with a fake Pi-Somfy script** — closer to production and worth
  having as one integration test, but too slow and stateful to develop against.

---

## 5. FR-017 — reconciling a bridge report with the local estimate

This is the real problem. Pi-Somfy publishes a position on `set_state`, but **that
number is not a measurement**. It is Pi-Somfy's own dead reckoning, computed from the
travel time in *its* configuration. So the incoming value is a second estimate of
unknown quality, not ground truth, and "just take the report" is wrong.

**Decision**: a precedence rule based on who knows more about the *cause* of the
movement, not on who spoke last.

| Situation | Who wins | Why |
|---|---|---|
| We issued a command and it is still travelling | **local estimate**, reports ignored | We know the exact moment we sent it; the bridge's timer started later and rounds |
| Idle, report says 0 % or 100 % | **report**, and the position becomes *certain* | An end stop is the one thing that is mechanically true |
| Idle, report differs by ≤ 3 pp | local estimate kept | Noise between two estimates; moving the graphic would be churn |
| Idle, report differs by > 3 pp | **report**, eased in over ~400 ms | Something happened we did not cause |
| Reports arrive in sequence while we are idle | **report stream**, confidence stays *estimated*, timestamp refreshed | A physical remote was used; the bridge heard the command and we did not, so its clock is fresher than ours |
| Report arrives for an unknown address | ignored, logged | Not ours |

Two details that are easy to get wrong:

- **Easing is display-only.** The underlying value jumps; the rendered one glides, so the
  graphic never teleports (FR-017) while the model stays honest.
- **Accepting a report does not refresh the certainty clock**, except in the end-stop and
  external-movement rows. Taking a second estimate and calling the position freshly known
  would be exactly the lie Principle III forbids.

**Alternatives considered**:

- **Bridge always wins** — simplest, and wrong: it discards our better knowledge of our
  own commands and makes the animation stutter on every report during travel.
- **Weighted blend of both estimates** — sounds principled, produces a number that is
  neither, and cannot be explained to a user.
- **Ignore reports entirely** — defensible while RX is off, but throws away the one
  signal that catches physical-remote use, which is the main source of drift.

---

## Settled defaults

| Question | Answer |
|---|---|
| Python | 3.11, matching Raspberry Pi OS bookworm |
| Backend tests | pytest, with `httpx` ASGI transport and the simulator adapter |
| Frontend tests | Vitest for logic; the animation is judged by eye, not asserted |
| Which shutters exist | our own config file, not Pi-Somfy's `operateShutters.conf` |
| Runtime state | SQLite, one small file |
| Stale threshold | 12 hours before an estimate is de-emphasised (FR-008), configurable |

**On not reading `operateShutters.conf`**: addresses have to be written down twice, which
is mild duplication. Reading Pi-Somfy's file instead would couple this project to another
project's on-disk format and break the boundary Principle II draws. The duplication is
the cheaper mistake.
