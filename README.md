# somfy-shutters

![Status: work in progress](https://img.shields.io/badge/status-work_in_progress-E8A33D?style=for-the-badge)
![Runs against: simulator](https://img.shields.io/badge/runs_against-simulator_only-8A8276?style=for-the-badge)

# 🚧 WORK IN PROGRESS 🚧

> **It runs, but it has never moved a real shutter.** Feature 001 is implemented and
> tested against a simulated house; no motor in this project has been paired yet, so
> the MQTT path to Pi-Somfy is written and unit-tested but unproven on hardware.
>
> Clone it to read it or to try the simulator. Do not put it in front of your windows
> and expect it to be right yet.

---

Self-hosted control for SIMU/Somfy RTS roller shutters through
[Pi-Somfy](https://github.com/Nickduino/Pi-Somfy): a live animated view of where every
shutter stands, and automations that run on the house's own network.

## What works today

| | |
|---|---|
| ✅ | Open, close, stop and drive to a position, on one shutter or all of them |
| ✅ | Animation at the shutter's real travel speed, starting the moment you tap |
| ✅ | Every position states whether it is certain, estimated or unknown, and how old that is |
| ✅ | Live updates to every open client; reconnect with backoff after any interruption |
| ✅ | A simulated house with soft start and non-linear travel, so it develops without hardware |
| ⬜ | **Travel-time calibration** — feature 002, currently the times come from configuration |
| ⬜ | Automations and schedules |
| ⬜ | Anything confirmed on a real motor |

74 tests, all against the real API surface or the tracker's rules.

## The problem this project takes seriously

Somfy RTS is **one-way radio**. The motor has no transmitter: it never reports its
position, never acknowledges a command, and cannot be queried. The only certain
positions are the two mechanical end stops, because the motor physically stops there.

Everything in between is dead reckoning — a known start, a sent command, and elapsed
time. So this app does not pretend to read the shutter. It shows how confident it is:

| State | Meaning |
|---|---|
| **sicher** | just reached an end stop — the only thing the system actually knows |
| **geschätzt** | computed from travel time, shown with the age of the last sync |
| **unsicher** | stale or lost after a restart; dimmed, with a resync offered |

A shutter graphic that silently lies is worse than none, because people act on it.

## Architecture

```mermaid
flowchart LR
  App["PWA<br/>(animated)"] <--> BE["Backend<br/>(automations, history)"]
  BE <--> MQTT[["Mosquitto"]]
  MQTT <--> PS["Pi-Somfy"]
  PS --> CC["CC1101<br/>SPI"]
  CC -. "433.42 MHz RTS" .-> M["SIMU motors"]
```

Pi-Somfy stays the only process that holds rolling-code counters and transmits. This
project never touches the radio — it publishes to `somfy/<address>/level/cmd` and
subscribes to `somfy/<address>/level/set_state`, nothing else. That keeps the
transmitter swappable: moving to ESPSomfy-RTS would change an endpoint, not the app.

| Layer | Choice |
|---|---|
| Radio bridge | Pi-Somfy with CC1101 (E07-M1101D-SMA) over SPI |
| Message bus | Mosquitto |
| Backend | Python + FastAPI (REST + WebSocket) |
| Scheduling | APScheduler for clock triggers, `astral` for sun triggers, offline |
| Storage | SQLite |
| Frontend | Web app installable as a PWA |

Backend, broker and Pi-Somfy all run on the same Raspberry Pi. No extra hardware, no
container orchestrator, no database server.

## Non-negotiables

From [the constitution](.specify/memory/constitution.md), which planning is checked
against:

- **Pi-Somfy owns the radio.** A second transmitter desynchronizes the rolling codes and
  forces physical re-pairing at every window.
- **MQTT is the only integration point.** Pi-Somfy's web UI is not an API.
- **Positions are estimates, not feedback**, and the interface has to say so.
- **Offline by default.** No cloud service between a tap and a shutter moving.
- **Measured physical values** — travel times, addresses, direction — live in
  configuration, never in code.

## Running it

No broker and no hardware needed — `bridge.kind = "sim"` runs a simulated house.

```bash
cp config/shutters.example.toml config/shutters.toml

cd backend
uv venv --python 3.11 .venv && uv pip install -e ".[dev]"
.venv/bin/uvicorn somfy_shutters.main:app --reload --host 0.0.0.0

cd ../frontend && npm install && npm run dev     # proxies /api to the backend
```

Point `bridge.kind` at `"mqtt"` and nothing else changes. Details in
[`backend/README.md`](backend/README.md); the validation scenarios, including the
reconciliation cases, are in
[`specs/001-mqtt-live-position/quickstart.md`](specs/001-mqtt-live-position/quickstart.md).

The simulator is not a stub. It gives each window a soft-start dead time, a non-linear
travel curve and different speeds up and down — none of it visible through the port the
app talks to. An app that could see those would prove nothing by passing.

## The mock

[`mocks/rolladen-ui.html`](mocks/rolladen-ui.html) opens in any browser, no build step.
Four screens in German: overview, detail, automations, and calibration, including
adding and removing a shutter and the power-cycle reset for when every remote is lost.

It predates the real frontend and is **throwaway**. Where the two disagree, the code
wins. It survives for one reason: it holds the calibration flow that feature 002 will
build, which is not implemented yet.

### Calibration, once it exists

Travel times cannot be read off the motor, so the user is the sensor: two button presses
per trip, one when the shutter starts moving, one when it arrives. Runs alternate
direction, so every trip starts from an end stop and none is wasted.

Two presses leave about 9 percentage points of error mid-travel, because the motor does
not move linearly; perfect presses would leave 8.8. A third press makes it *worse* —
the curve is symmetric, so a halfway mark lands where the error is already zero. Four
presses reach 3.7. Not worth it across eight windows, so two it is.

Staying accurate afterwards costs one tap: after an end-to-end travel the app asks once
whether the shutter has arrived, and that answer is a measurement. It cannot do this by
itself, because **nothing in the system observes when a travel ends** — the motor is
silent, the bridge reports its own dead reckoning, and receive mode hears commands
rather than arrivals. Every number here ultimately comes from somebody looking at a
window.

## Development

Work is spec-driven with [GitHub Spec Kit](https://github.com/github/spec-kit):

```
/speckit-constitution → /speckit-specify → /speckit-plan → /speckit-tasks → /speckit-implement
```

Feature code is not written before its spec exists. Feature 001 is specified, planned,
broken into tasks and implemented under
[`specs/001-mqtt-live-position/`](specs/001-mqtt-live-position/) — the plan's
[research.md](specs/001-mqtt-live-position/research.md) is where the non-obvious
decisions are argued. See [CLAUDE.md](CLAUDE.md) for conventions and build commands.

```bash
cd backend && .venv/bin/python -m pytest       # 74 tests
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
```

## Open hardware questions

None of these has been answered yet, which is why nothing here is proven on a motor.
The software is built so that answering them changes configuration, not code:

1. **Direction of `level/cmd`** — is 0 fully open or fully closed? One setting,
   `invert_level`, applied in a single file; a test asserts nothing else knows about it.
2. **Per-window travel times**, up and down separately. Read from `shutters.toml`; a
   shutter with none still animates, on a stated default, and is marked uncalibrated.
3. **Radio range** to the furthest window, antenna attached. A command lost in the air
   is indistinguishable from one delivered — the simulator can reproduce that with a
   loss rate.
4. Whether **CC1101 receive mode** gets enabled, which tracks physical remotes. Without
   it, drift from manual use is invisible and the age of the estimate is all the app can
   offer.
5. **Rolling-code pairing** per window, addresses recorded in `operateShutters.conf` and
   copied into ours.

One more, found by reading Pi-Somfy rather than by measuring: `stop` is sent as a level
command at the current position, because `level/cmd` is the only topic this project
speaks. Whether a motor halts crisply that way is unverified; if not, the button-press
topic is the fix and the MQTT contract changes.

**The CC1101 runs on 3.3V only** (Pi pin 1 or 17). 5V destroys the module.

## Credits

- [Pi-Somfy](https://github.com/Nickduino/Pi-Somfy) — the RTS bridge this builds on, and
  the source for how shutters are added, paired and removed.
- [Spec Kit](https://github.com/github/spec-kit) — the spec-driven workflow.

Not affiliated with Somfy or SIMU. "Somfy", "SIMU" and "RTS" belong to their owners.

## License

[MIT](LICENSE).
