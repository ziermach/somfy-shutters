# Quickstart: validating the switch to Pi-Somfy's current interface

Scenarios mapped to [spec.md](./spec.md). Topic shapes: [contracts/mqtt.md](./contracts/mqtt.md).

## A — Against the simulator (no broker)

```bash
cd backend && .venv/bin/python -m pytest          # every feature 001–004 scenario must pass (SC-006)
.venv/bin/uvicorn somfy_shutters.main:app --host 0.0.0.0
cd frontend && npm run dev
```

**A1 Commands (story 1).** Tap auf / zu / a position / Alle zu / a group / an automation.
Every shutter moves as before.

**A2 Stop (story 2).** Start a close, tap stop halfway. The simulated motor halts
(`GET /api/sim/truth` stops changing) and the card settles as an estimate.

**A3 External movement (story 3).** With a shutter idle,
`POST /api/sim/movement {"shutter_id":"kueche","state":"closing"}` then
`POST /api/sim/report {"shutter_id":"kueche","percent":40}`. The card shows the correction at
once and the age is refreshed — no second report needed.

**A4 Reconnect burst (story 3, SC-004).** Restart the backend with positions known. The
simulator replays every position as retained on start. No correction frame, no glide.

**A5 Bridge down (story 4).** `POST /api/sim/bridge/offline` — the simulator announces
`offline`. Banner within 5 s, commands refused; `online` brings them back.

## B — Against a real Mosquitto on the laptop (optional, closest to hardware)

```bash
brew install mosquitto && mosquitto -v            # or any broker on localhost:1883
# config/shutters.toml: [bridge] kind = "mqtt", host = "localhost"
.venv/bin/uvicorn somfy_shutters.main:app --host 0.0.0.0
```

Impersonate Pi-Somfy with the Mosquitto clients:

```bash
# the bridge announces itself; without this the app must show it unreachable
mosquitto_pub -t somfy/bridge/availability -m online -r

# watch what the app sends
mosquitto_sub -v -t 'somfy/+/command' -t 'somfy/+/set_position'
```

**B1** Tap zu on Wohnzimmer → `somfy/0x279621/command CLOSE`. Drive to 30 % →
`somfy/0x279621/set_position <n>` (n after the travel curve). Stop → `command STOP`, never a
`set_position`.

**B2** `mosquitto_pub -t somfy/0x279621/position -m 100 -r` → the card becomes certain at 100.

**B3** `mosquitto_pub -t somfy/bridge/availability -m offline -r` → banner, commands refused.

**B4** Publish a position as retained, restart the backend → the position fills in only if
it was unknown; no correction if the app knew it.

**B5** Case: `mosquitto_pub -t somfy/0X279621/position -m 50` → matched to Wohnzimmer; the
next command is published to `somfy/0X279621/…`.

## C — On the Pi (pending hardware, joins T061–T064 / T042–T044 / T052)

Install current Pi-Somfy, enable MQTT, pair one shutter. Tap zu, a position, stop. Confirm
the motor does each, and that a physical remote press appears as external movement when the
receiver is enabled.
