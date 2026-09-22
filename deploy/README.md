# Deploying on the Raspberry Pi

Everything runs on one Pi: Pi-Somfy, Mosquitto and this app. That is a constitutional
choice, not an accident — see [the constitution](../.specify/memory/constitution.md),
principle IV. The app only needs to reach the broker over TCP, so it *can* run
elsewhere on the LAN, but then a second box has to be awake for every schedule and the
SQLite state travels with it. Put it on the Pi.

> **Nothing here has driven a real motor yet.** Feature 001 is proven against the
> simulator only. Deploy with `bridge.kind = "sim"` first, confirm the app works, and
> switch to `"mqtt"` as a separate step.

```mermaid
flowchart LR
  B["Browser / PWA<br/>any LAN device"] -- "HTTP + WS :8000" --> A["somfy-shutters<br/>uvicorn"]
  A -- "MQTT :1883 loopback" --> M[["Mosquitto"]]
  M --> P["Pi-Somfy"]
  P -- SPI --> C["CC1101"]
  C -. "433.42 MHz" .-> W["motors"]
```

Clients never speak MQTT. The browser talks to the backend; the backend talks to the
broker. Nothing in this path leaves the house.

## 0. What you need first

| | |
|---|---|
| Pi | Pi 3 or newer, Raspberry Pi OS Bookworm (64-bit). A Zero 2 W works but see [building the frontend](#3-build-the-frontend). |
| Radio | CC1101 (E07-M1101D-SMA) wired to the SPI header, **3.3V only — Pi pin 1 or 17. 5V destroys the module.** |
| Pi-Somfy | Installed, paired with every window, publishing to MQTT. This project does not install or configure it. |
| Network | Static lease or reserved IP for the Pi, so the PWA's bookmark keeps working. |

Pi-Somfy owns the radio and the rolling-code counters. Never run a second transmitter
against the same motors — resynchronising means walking to every window and
re-pairing by hand.

## 1. Mosquitto

```bash
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
```

Bind it to loopback and require a password. Both the app and Pi-Somfy are local, so
the broker has no reason to be on the network at all:

```bash
sudo tee /etc/mosquitto/conf.d/local.conf >/dev/null <<'CONF'
listener 1883 127.0.0.1
allow_anonymous false
password_file /etc/mosquitto/passwd
CONF

sudo mosquitto_passwd -c /etc/mosquitto/passwd somfy      # prompts for a password
sudo systemctl enable --now mosquitto
```

Point Pi-Somfy at the same credentials, then check that it actually publishes. With a
shutter moved by its physical remote, or by Pi-Somfy's own UI:

```bash
mosquitto_sub -h 127.0.0.1 -u somfy -P '<password>' -t 'somfy/#' -v
```

If nothing appears here, nothing will appear in the app either — fix it at this layer.

> If you keep the app off the Pi, the broker has to listen on the LAN instead
> (`listener 1883 0.0.0.0`). Keep 1883 off the internet regardless: no TLS is
> configured here, and the credentials go over the wire in the clear.

## 2. Install the app

```bash
sudo apt install -y git python3.11 python3.11-venv
git clone https://github.com/ziermach/somfy-shutters.git /home/pi/somfy-shutters
cd /home/pi/somfy-shutters/backend

python3.11 -m venv .venv          # or: uv venv --python 3.11 .venv
.venv/bin/pip install -e .        # production needs no ".[dev]"
```

The unit file expects exactly `/home/pi/somfy-shutters`. A different path means
editing the four places it appears in `somfy-shutters.service`.

## 3. Build the frontend

The backend serves `frontend/dist` itself, so production is one process on one port.

```bash
cd /home/pi/somfy-shutters/frontend
npm ci && npm run build
```

On a Pi Zero 2 W or a 1 GB Pi 3 the Vite build can run out of memory. Build on a
workstation instead and copy the result over — `dist` is static, nothing in it is
architecture-specific:

```bash
# on your machine
cd frontend && npm ci && npm run build
rsync -a dist/ pi@somfy.local:/home/pi/somfy-shutters/frontend/dist/
```

Without a build the API still works, and the log says
`no built frontend at … — run npm run build`.

## 4. Configure

```bash
cd /home/pi/somfy-shutters
cp config/shutters.example.toml config/shutters.toml
```

`config/shutters.toml` is gitignored — it holds the real RTS addresses and this
repository is public. Copy each `address` by hand out of Pi-Somfy's
`operateShutters.conf`. A wrong address is completely silent: the radio never
answers, so the app cheerfully animates a shutter that never moved.

```toml
[bridge]
kind = "sim"          # start here; switch to "mqtt" in step 6
host = "127.0.0.1"
port = 1883
user = "somfy"
password = "…"
invert_level = false  # open hardware question 1 — flip if 0 turns out to mean "open"
```

Validation is strict and startup fails loudly with the offending line. Leave travel
times out of the file for any window you have not measured: the shutter still
animates on `default_travel_seconds`, marked uncalibrated, and the calibration flow
fills it in.

## 5. Run it as a service

```bash
sudo cp deploy/somfy-shutters.service /etc/systemd/system/
sudo systemctl enable --now somfy-shutters
systemctl status somfy-shutters
```

The unit starts after `mosquitto.service`, restarts on failure, and is confined with
`ProtectSystem=strict` — `config/` is the only writable path, because that is where
the database and the measured calibration live.

Check it:

```bash
curl -s localhost:8000/api/health
# {"status":"ok","bridge":{"connected":true,"kind":"sim"},"shutters":4}
```

`status` is `ok` even when the bridge is down: the service is up and correctly
reporting a broken dependency. Read `bridge.connected` for the broker.

Then open `http://<pi-ip>:8000` from a phone on the same network and install it as a
PWA. There is no authentication — anyone on the LAN can move the shutters. Do not
port-forward it; reach it from outside over a VPN (WireGuard, Tailscale) if you need
to.

## 6. Switch to the real radio

Only after the simulator works end to end:

```bash
sudo -u pi sed -i 's/^kind = "sim"/kind = "mqtt"/' /home/pi/somfy-shutters/config/shutters.toml
sudo systemctl restart somfy-shutters
journalctl -u somfy-shutters -f
```

Expect `ready: N shutters, bridge=mqtt`. Move one shutter from the app and watch the
window. Two things are worth knowing before you trust it:

- **The direction may be inverted.** If "open" closes the shutter, set
  `invert_level = true` and restart. That single setting is the only place the wire
  direction is known.
- **A lost command looks exactly like a delivered one.** RTS is one-way. If the
  furthest window misses commands, that is radio range, not software — check the
  antenna before changing anything here.

Measure travel times per window through the calibration flow rather than guessing;
anything you type into `shutters.toml` overrides a measurement and is never
overwritten.

## Operating it

```bash
journalctl -u somfy-shutters -f                     # logs
journalctl -u somfy-shutters -p warning --since today
sudo systemctl restart somfy-shutters
```

`LOG_LEVEL=DEBUG` in the unit's `Environment=` turns up the detail.

**State lives in three files under `config/`:**

| File | What it is | Backup |
|---|---|---|
| `shutters.toml` | hand-written: addresses, names, measured overrides | yes — it is not in git |
| `calibration.toml` | written by the app: measured travel times | yes — re-measuring costs eight windows of button presses |
| `state.db` | SQLite: last known positions and history | optional — positions go stale on restart anyway |

```bash
sudo systemctl stop somfy-shutters
tar czf ~/somfy-backup-$(date +%F).tar.gz -C /home/pi/somfy-shutters config
sudo systemctl start somfy-shutters
```

Stop the service first: SQLite is in WAL mode and a live copy can catch a torn write.

**Updating:**

```bash
cd /home/pi/somfy-shutters
sudo systemctl stop somfy-shutters
git pull
backend/.venv/bin/pip install -e backend
cd frontend && npm ci && npm run build
sudo systemctl start somfy-shutters
```

## When it does not work

| Symptom | Where to look |
|---|---|
| Service will not start | `journalctl -u somfy-shutters -n 50`. A config error prints the offending field and exits. |
| `no configuration at …` | `config/shutters.toml` is missing, or the unit's `SHUTTERS_CONFIG` points elsewhere. |
| `bridge.connected` stays `false` | Broker down, wrong credentials, or the app is not on the Pi and Mosquitto is bound to loopback. Reconnect backs off 1 → 30s and logs each attempt. |
| App works, shutters do not move | Prove the broker path outside the app: `mosquitto_pub -h 127.0.0.1 -u somfy -P '…' -t 'somfy/0x279621/level/cmd' -m 50`. If that moves nothing, it is Pi-Somfy or the radio, not this app. |
| Positions never become "sicher" | Expected until a shutter reaches an end stop. Only the end stops are certain. |
| Unknown address warnings | An address in `shutters.toml` does not match `operateShutters.conf`. Copy it again. |
| Blank page, API responds | The frontend was never built, or `dist` landed in the wrong place. |

## Environment

Set in the unit file; all optional except where the default is wrong for your layout.

| Variable | Default | Meaning |
|---|---|---|
| `SHUTTERS_CONFIG` | `<repo>/config/shutters.toml` | which shutters exist |
| `SHUTTERS_DB` | `<repo>/config/state.db` | persisted positions |
| `SHUTTERS_CALIBRATION` | next to the database | measured travel times |
| `LOG_LEVEL` | `INFO` | |
