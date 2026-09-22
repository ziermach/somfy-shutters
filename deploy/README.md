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
| Pi | Pi 3 or newer, Raspberry Pi OS **Lite** (64-bit), Bookworm or Trixie. A Zero 2 W works but see [building the frontend](#4-build-the-frontend). |
| Radio | CC1101 (E07-M1101D-SMA) wired to the SPI header — see [wiring the radio](#wiring-the-radio). **3.3V only.** |
| Pi-Somfy | Installed, paired with every window, publishing to MQTT. This project does not install or configure it. |
| Network | Ethernet, WiFi or a phone hotspot — see [network](#1-network). |

Use Lite, not the desktop image. On a 1 GB Pi 3 booting over USB 2.0 the desktop image
can start so slowly that `systemd-logind`, `accounts-daemon` and cloud-init's final
stage time out on first boot — and when cloud-init fails, the user, SSH and WiFi you
set in Raspberry Pi Imager are never applied. Lite starts a fraction of the services
and a shutter controller has no screen anyway.

Nothing below assumes a particular login name. The app gets its own system user,
`somfy`, and lives in `/opt/somfy-shutters`; you run the commands as whatever user
you created in Imager, with `sudo`.

Pi-Somfy owns the radio and the rolling-code counters. Never run a second transmitter
against the same motors — resynchronising means walking to every window and
re-pairing by hand.

### Wiring the radio

Fixed by the [constitution](../.specify/memory/constitution.md); module pin numbers are
from Ebyte's [E07-M1101D-SMA manual](https://www.scribd.com/document/708471606/E07-M1101D-SMA-Usermanual-EN-v1-30).

| Module pin | Signal | Pi physical pin | Pi GPIO |
|---|---|---|---|
| 1 | GND | 39 | GND |
| 2 | VCC | **17** (or 1) | **3.3V** |
| 3 | GDO0 | 37 | GPIO26 |
| 4 | CSN | 36 | GPIO16 |
| 5 | SCK | 40 | GPIO21 |
| 6 | MOSI | 38 | GPIO20 |
| 7 | MISO/GDO1 | 35 | GPIO19 |
| 8 | GDO2 | — | not connected |

**Interactive diagram:** [open in Cirkit Designer](https://app.cirkitdesigner.com/project/c0b9f439-d559-4c61-9f5f-2cd1cb531f8d?view=interactive_preview)
— the table above is the source of truth; if the two ever disagree, the table wins.

<!-- GitHub strips iframes; this renders only in viewers that allow them. The link above always works. -->
<div style="position: relative; width: 100%; padding-top: calc(max(56.25%, 400px));">
  <iframe src="https://app.cirkitdesigner.com/project/c0b9f439-d559-4c61-9f5f-2cd1cb531f8d?view=interactive_preview" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none;"></iframe>
</div>

Everything but VCC sits in the last three rows of the header, the end nearest the USB
ports:

```
         inner  outer
  35 MISO  ●     ●  36 CSN
  37 GDO0  ●     ●  38 MOSI
  39 GND   ●     ●  40 SCK
```

> **VCC to 3.3V — pin 17 or 1 — never 5V.** Pins 2 and 4 carry 5V and sit right next
> to pin 1; the module's absolute maximum is about 3.6V and 5V destroys it. Wire with
> the Pi unplugged and check VCC twice before powering on.
>
> **Screw the antenna on before anything transmits.** Transmitting into an open SMA
> connector can damage the module.

Pins 35, 38 and 40 are the Pi's *second* SPI bus (SPI1), not the one `raspi-config`
switches on (SPI0). Which overlay is needed depends on how Pi-Somfy's CC1101 support
drives the module — follow its installation instructions rather than assuming SPI is
already set up. [pinout.xyz](https://pinout.xyz) shows every pin interactively.

## 1. Network

Wired Ethernet is the least trouble. WiFi works; it needs one setting changed. A phone
hotspot works for bring-up, with limits worth knowing before you rely on it.

The app never needs the internet. It needs a network so that phones can reach it.

### WiFi: turn off power saving

The Pi's WiFi driver saves power by default, and a sleeping radio delays or drops
*incoming* packets. The symptoms look like a software bug: commands arrive seconds late,
the live feed stutters and reconnects, a remote tunnel stalls until the Pi happens to
send something. Turn it off, permanently:

```bash
nmcli -t -f NAME,TYPE connection show --active      # find the WiFi connection name
sudo nmcli connection modify "<connection>" 802-11-wireless.powersave 2
sudo nmcli connection up "<connection>"
iw dev wlan0 get power_save                          # expect: Power save: off
```

`2` means "disable"; it survives reboots because it is stored on the connection, not
set on the interface. Re-run it if you ever connect to a different network.

Give the Pi a DHCP reservation on the router so its address stays put, and put it
where the signal is steady — stability matters here, speed does not. A Pi 3B only
speaks 2.4 GHz; the 3B+ also does 5 GHz. The CC1101 is on 433 MHz and does not
interfere with either.

### Phone hotspot

Works, and is a reasonable way to bring the system up in a flat with no internet yet.
Know what it costs:

- **The network leaves with the phone.** When the hotspot phone leaves the house, the
  Pi is on no network at all: nobody can reach the app, from inside or outside. The
  shutters still respond to their physical remotes, and the backend keeps running. A
  spare phone, an old one, or a cheap LTE router left at home fixes this.
- **Phones switch hotspots off.** Android has a "turn off hotspot automatically" setting
  — disable it. iOS only shows the hotspot to *new* devices while the Personal Hotspot
  screen is open, and may stop it after a while with nothing connected; a Pi that has
  joined once reconnects on its own, but check it is still online after a night.
- **iPhone: enable "Maximize Compatibility"** under Personal Hotspot. Without it the
  hotspot may run on 5 GHz only, which a Pi 3B cannot see at all.
- **No DHCP reservation.** The Pi's address can change between sessions. Use the name
  instead: `http://<hostname>.local:8000` (Raspberry Pi OS advertises it via mDNS; the
  hostname is whatever you set in the imager, `raspberrypi` by default).
- **Client isolation.** Some hotspots stop connected devices from reaching each other.
  If the hotspot phone can open the app but a second device cannot, that is why.
- **The clock.** A Pi 3 has no battery-backed clock and sets its time over the
  internet at boot. Booted without internet it starts with a stale time and jumps
  forward when a connection appears. Positions show odd ages until then; once sun-based
  automations exist, they will fire at wrong times. Make sure the hotspot is up before
  the Pi boots, or check `timedatectl` shows `System clock synchronized: yes`.
- **Data use is small.** Commands and state updates are bytes. The expensive part is
  installing — `apt`, `pip`, `npm` — so build the frontend elsewhere (step 4) and do
  big installs on a better connection if you can.

Apply the power-saving fix above to the hotspot connection too; it is a WiFi
connection like any other.

### Reaching it from outside, later

Remote access is not part of this deployment yet. When it arrives it will be a
WireGuard tunnel that the Pi dials *out* to a server with a public address — so no port
forwarding on the home router, and it works behind a mobile carrier's NAT, hotspot
included. The Pi's side of that tunnel will need `PersistentKeepalive = 25`: without it
the router or carrier forgets the mapping after a minute or two of silence, and the
server can no longer reach back in until the Pi next sends something.

## 2. Mosquitto

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

## 3. Install the app

A system user with no login shell, and its own home for pip and npm caches so they do
not land inside the checkout:

```bash
sudo apt install -y git python3 python3-venv
sudo useradd --system --user-group --create-home --home-dir /var/lib/somfy \
             --shell /usr/sbin/nologin somfy
sudo install -d -o somfy -g somfy /opt/somfy-shutters
sudo -u somfy git clone https://github.com/ziermach/somfy-shutters.git /opt/somfy-shutters

cd /opt/somfy-shutters/backend
sudo -u somfy python3 -m venv .venv
sudo -u somfy .venv/bin/pip install -e .      # production needs no ".[dev]"
```

`python3` is 3.11 on Bookworm and 3.13 on Trixie; the app needs 3.11 or newer, so
either works.

Everything from here on that touches `/opt/somfy-shutters` runs as `somfy` —
`sudo -u somfy …`. The code belongs to that user so updating needs no root; the unit's
`ProtectSystem=strict` still keeps the running service from writing anywhere but
`config/`. The unit expects exactly `/opt/somfy-shutters`.

## 4. Build the frontend

The backend serves `frontend/dist` itself, so production is one process on one port.

```bash
sudo apt install -y nodejs npm                    # Vite needs Node 18 or newer
cd /opt/somfy-shutters/frontend
sudo -u somfy npm ci && sudo -u somfy npm run build
```

On a Pi Zero 2 W or a 1 GB Pi 3 the Vite build can run out of memory. Build on a
workstation instead and copy the result over — `dist` is static, nothing in it is
architecture-specific:

```bash
# on your machine
cd frontend && npm ci && npm run build
rsync -a --rsync-path="sudo -u somfy rsync" \
      dist/ <you>@<hostname>.local:/opt/somfy-shutters/frontend/dist/
```

`--rsync-path` makes the far end write as `somfy`, so the files end up owned by the
app user rather than by your login.

Without a build the API still works, and the log says
`no built frontend at … — run npm run build`.

## 5. Configure

```bash
cd /opt/somfy-shutters
sudo -u somfy install -m 600 config/shutters.example.toml config/shutters.toml
sudo -u somfy nano config/shutters.toml
```

Mode `600`: the file will hold the broker password, and nobody but the app needs to
read it.

`config/shutters.toml` is gitignored — it holds the real RTS addresses and this
repository is public. Copy each `address` by hand out of Pi-Somfy's
`operateShutters.conf`. A wrong address is completely silent: the radio never
answers, so the app cheerfully animates a shutter that never moved.

```toml
[bridge]
kind = "sim"          # start here; switch to "mqtt" in step 7
host = "127.0.0.1"
port = 1883
user = "somfy"
password = "…"
```

Validation is strict and startup fails loudly with the offending line. Leave travel
times out of the file for any window you have not measured: the shutter still
animates on `default_travel_seconds`, marked uncalibrated, and the calibration flow
fills it in.

## 6. Run it as a service

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

## 7. Switch to the real radio

Only after the simulator works end to end:

```bash
sudo -u somfy sed -i 's/^kind = "sim"/kind = "mqtt"/' /opt/somfy-shutters/config/shutters.toml
sudo systemctl restart somfy-shutters
journalctl -u somfy-shutters -f
```

Expect `ready: N shutters, bridge=mqtt`. Move one shutter from the app and watch the
window. Two things are worth knowing before you trust it:

- **Pi-Somfy must be v3.1 or newer.** The app speaks its current topics
  (`somfy/<id>/command`, `set_position`, `position`, `state`, `somfy/bridge/availability`);
  older versions used `level/cmd` and are not supported. Direction needs no setting — the
  bridge declares 100 = open.
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
sudo tar czf ~/somfy-backup-$(date +%F).tar.gz -C /opt/somfy-shutters config
sudo chown "$USER" ~/somfy-backup-*.tar.gz
sudo systemctl start somfy-shutters
```

Stop the service first: SQLite is in WAL mode and a live copy can catch a torn write.
`sudo` because the service creates its files readable only by `somfy`.

**Updating:**

```bash
cd /opt/somfy-shutters
sudo systemctl stop somfy-shutters
sudo -u somfy git pull
sudo -u somfy backend/.venv/bin/pip install -e backend
cd frontend && sudo -u somfy npm ci && sudo -u somfy npm run build
sudo cp /opt/somfy-shutters/deploy/somfy-shutters.service /etc/systemd/system/ \
  && sudo systemctl daemon-reload                  # in case the unit changed
sudo systemctl start somfy-shutters
```

## When it does not work

| Symptom | Where to look |
|---|---|
| Service will not start | `journalctl -u somfy-shutters -n 50`. A config error prints the offending field and exits. |
| `no configuration at …` | `config/shutters.toml` is missing, or the unit's `SHUTTERS_CONFIG` points elsewhere. |
| `Permission denied` on anything in `config/` | A file there was created by you or root instead of `somfy`. `sudo chown -R somfy:somfy /opt/somfy-shutters/config`. |
| `bridge.connected` stays `false` | Broker down, wrong credentials, the app is not on the Pi and Mosquitto is bound to loopback — or Pi-Somfy is not running: the app counts the bridge reachable only once it announces `online` on `somfy/bridge/availability`. Check with `mosquitto_sub -h 127.0.0.1 -u somfy -P '…' -t somfy/bridge/availability -v`. |
| App works, shutters do not move | Prove the broker path outside the app: `mosquitto_pub -h 127.0.0.1 -u somfy -P '…' -t 'somfy/0x279621/command' -m CLOSE`. If that moves nothing, it is Pi-Somfy or the radio, not this app. |
| Positions never become "sicher" | Expected until a shutter reaches an end stop. Only the end stops are certain. |
| Unknown address warnings | An address in `shutters.toml` does not match `operateShutters.conf`. Copy it again. |
| Commands land seconds late, live view keeps reconnecting | WiFi power saving is on. `iw dev wlan0 get power_save` — see [WiFi](#wifi-turn-off-power-saving). |
| `<hostname>.local` does not resolve | The phone or network blocks mDNS. Use the IP from `hostname -I` on the Pi. |
| Blank page, API responds | The frontend was never built, or `dist` landed in the wrong place. |

## Environment

Set in the unit file; all optional except where the default is wrong for your layout.

| Variable | Default | Meaning |
|---|---|---|
| `SHUTTERS_CONFIG` | `<repo>/config/shutters.toml` | which shutters exist |
| `SHUTTERS_DB` | `<repo>/config/state.db` | persisted positions |
| `SHUTTERS_CALIBRATION` | next to the database | measured travel times |
| `LOG_LEVEL` | `INFO` | |
