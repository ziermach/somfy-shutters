# Quickstart: running and proving feature 001

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

This is the validation guide — how to run the thing and how to convince yourself each
user story actually works. It assumes the implementation exists; it does not contain
implementation.

Everything here runs **without hardware**, against the simulator. The hardware
scenarios at the end are marked separately and need the Pi.

---

## Prerequisites

| | |
|---|---|
| Python | 3.11+ |
| Node | 20+ |
| Broker | only for the hardware and integration scenarios — not for the simulator |

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cd ../frontend && npm install
```

## Run against the simulated house

```bash
cp config/shutters.example.toml config/shutters.toml   # bridge.kind = "sim"
cd backend && uvicorn somfy_shutters.main:app --reload --host 0.0.0.0
cd frontend && npm run dev                              # proxies /api to the backend
```

Open the dev server's URL. Four simulated shutters, each with its own hidden
characteristics — soft-start dead time, a non-linear travel curve, different speeds up
and down, and one deliberately uncalibrated.

Point `bridge.kind = "mqtt"` at a real broker and nothing else changes.

---

## Story 1 — move a shutter and watch it move

**S1.1 Command and arrival (FR-001, FR-012, FR-013, SC-002)**

Tap close on a calibrated shutter. The graphic must start moving immediately, not after
a round trip. Stopwatch the graphic against the simulator's own log line: the two must
finish within a second of each other.

```bash
curl -s -XPOST localhost:8000/api/shutters/wohnzimmer/command \
     -H 'content-type: application/json' -d '{"action":"close"}' | jq
```

The response carries `movement.started_at` and `expected_arrival`. Everything the
animation needs is in that one response — confirm no further request is made while it
travels.

**S1.2 Stop mid-travel (FR-016)**

Send `close`, wait a few seconds, send `stop`. The graphic must freeze where it is, not
snap to 0 and not continue. Afterwards the position is an estimate, not certain.

**S1.3 Reverse mid-travel**

Send `close`, then `open` before it arrives. The shutter reverses from where it is; the
position must not jump to 100 first.

**S1.4 Two clients (FR-018, SC-003)**

Open two browser windows. Command from one. The other animates within a second, from
the same timestamps — compare the two screens side by side, they should be in step.

**S1.5 All at once (FR-002, SC-009)**

```bash
curl -s -XPOST localhost:8000/api/shutters/command \
     -H 'content-type: application/json' -d '{"action":"open"}' | jq
```

Every shutter moves. Each arrives on its own schedule, because the travel times differ.

**S1.6 Intermediate position (FR-001)**

Command `{"action":"position","target_percent":30}`. It stops at 30 and the position is
reported as an estimate — never certain, because 30 is not an end stop.

---

## Story 2 — confidence

**S2.1 End stop makes it certain (FR-006)**

Drive fully open. The position reads certain. Drive to 50. It reads estimated, with an
age counting from the moment it left the end stop.

**S2.2 Age is shown (FR-007)**

Check the uncalibrated shutter and one seeded with an old `certain_at`. The interface
must state the age, not just the number.

**S2.3 Stale de-emphasis (FR-008)**

Set `stale_after_hours = 0.01` in the config and restart. Move a shutter to an
intermediate position, wait a minute. The display must visibly de-emphasise and offer a
resync.

**S2.4 Resync (FR-009)**

Trigger it. The shutter drives to an end stop and the position becomes certain again.

```bash
curl -s -XPOST localhost:8000/api/shutters/buero/resync | jq
```

**S2.5 Restart mid-travel (FR-010)**

Start a long movement, kill the backend while it travels, restart it. That shutter must
come back as **unknown** — not as the position it was heading for, and not as the one it
left.

**S2.6 Restart at rest**

Drive fully closed, restart the backend. Still certain, still 0 — an end stop survives a
reboot.

**S2.7 No bare numbers (FR-011, SC-004)**

Walk every screen. Each position must carry its confidence. This one is read by eye;
there is no assertion for it.

---

## Story 3 — failures

**S3.1 Bridge goes away (FR-021, SC-007)**

With the simulator, `POST /api/sim/bridge/offline` (simulator-only endpoint). The UI
must show the bridge as unreachable within 5 s, and commands must fail with
`bridge_unreachable` and start no animation.

**S3.2 Client loses the server (FR-022, SC-006)**

Stop the backend with the UI open. Within a couple of seconds the UI says it is offline
and stops presenting positions as current. Restart; it reconnects on its own, takes the
snapshot, and is correct within 5 s. No reload.

**S3.3 Lost radio command**

Set `loss_rate = 0.5` in the simulator config. Roughly half the commands never reach the
motor. The app animates anyway — it cannot know — and the discrepancy resolves at the
next end stop. This scenario exists to confirm the app does not pretend to detect it.

**S3.4 Reconnect backoff (FR-023)**

Leave the backend down for a few minutes with the UI open. Reconnect attempts must space
out rather than hammer, and recovery must still be automatic.

---

## FR-017 — the reconciliation rules

Each row of the table in [research.md §5](./research.md) gets a scenario. The simulator
can inject reports directly:

```bash
curl -s -XPOST localhost:8000/api/sim/report \
     -H 'content-type: application/json' -d '{"shutter_id":"wohnzimmer","percent":40}'
```

| Inject | While | Expect |
|---|---|---|
| 40 | travelling | ignored, animation unbroken |
| 0 | idle | position becomes 0 and **certain** |
| 63 (local is 62) | idle | ignored, difference too small |
| 48 (local is 62) | idle | `correction` frame, graphic glides over ~400 ms |
| 30, 40, 50 in sequence | idle | treated as external movement, stays estimated, age refreshed |
| any, unknown address | — | dropped, logged once |

---

## Offline check (Principle IV, FR-024)

With the app loaded, disconnect the machine from the internet entirely — leave only the
local network. Everything must keep working, and a hard reload must still render:

```bash
grep -rEn "https?://(?!localhost)" frontend/dist/ || echo "no external origins"
```

No CDN, no Google Fonts, no analytics. The mock's font link must not have survived into
the real frontend.

---

## Automated suite

```bash
cd backend && pytest                       # unit + integration against the simulator
cd frontend && npm test                    # logic; the animation is judged by eye
```

The contract tests assert that payloads match [contracts/](./contracts/) exactly. If a
shape changes, the contract changes first.

---

## With real hardware

Only once at least one shutter is paired and `operateShutters.conf` has its address.

**H1 — direction of `level/cmd`** ([open question 1](../../CLAUDE.md)). Send
`{"action":"close"}` and watch the window. If it opens, set `invert_level = true` in
`[bridge]` and repeat. Nothing else may need changing — that is the acceptance criterion
for [contracts/mqtt.md](./contracts/mqtt.md).

**H2 — travel times** (open question 2). Stopwatch a full open and a full close, put
them in `shutters.toml`, and re-run S1.1. The animation should now land within a second.

**H3 — stop behaviour**. Confirm that a level command to the current position actually
halts the motor crisply. If it does not, the button-press topic is needed and the MQTT
contract changes — noted there.

**H4 — range** (open question 3). Command the furthest window repeatedly. Lost commands
show up as the S3.3 case in real life.
