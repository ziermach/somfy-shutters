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
| Pi | Pi 3 or newer, Raspberry Pi OS **Lite** (64-bit), Bookworm or Trixie. A Zero 2 W works but see [building the frontend](#5-build-the-frontend). |
| Radio | CC1101 (E07-M1101D-SMA) wired to the SPI header — see [wiring the radio](#wiring-the-radio). **3.3V only.** |
| Pi-Somfy | Release 3.3 or newer, installed in [step 3](#3-pi-somfy-and-pigpiod), then paired with every window in its own web UI. |
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

Fixed by the [constitution](../.specify/memory/constitution.md) (v1.2.0); module pin
numbers are from Ebyte's [E07-M1101D-SMA manual](https://www.scribd.com/document/708471606/E07-M1101D-SMA-Usermanual-EN-v1-30).
This is the wiring Pi-Somfy's CC1101 transmitter (`RFBackend = cc1101`) expects by
default: the Pi's hardware SPI0, with the RTS waveform on GDO0 driven from `TXGPIO = 4`.

| Module pin | Signal | Pi physical pin | Pi GPIO |
|---|---|---|---|
| 1 | GND | 25 | GND |
| 2 | VCC | **17** | **3.3V** |
| 3 | GDO0 | 7 | GPIO4 |
| 4 | CSN | 24 | GPIO8 (SPI0 CE0) |
| 5 | SCK | 23 | GPIO11 (SPI0 SCLK) |
| 6 | MOSI | 19 | GPIO10 (SPI0 MOSI) |
| 7 | MISO/GDO1 | 21 | GPIO9 (SPI0 MISO) |
| 8 | GDO2 | — | not connected |

Six of the seven wires land in one block in the middle of the header; GDO0 goes to pin 7,
near the pin-1 end:

```
          inner   outer
   7 GDO0   ●       ●   8
   …
  17 VCC    ●       ●  18
  19 MOSI   ●       ●  20
  21 MISO   ●       ●  22
  23 SCK    ●       ●  24 CSN
  25 GND    ●       ●  26
```

Pin 1 is the corner farthest from the USB ports; odd pins are the inner row, even pins
the row along the board edge.

> **VCC to 3.3V — pin 17 — never 5V.** Pins 2 and 4 carry 5V; the module's absolute
> maximum is about 3.6V and 5V destroys it. Wire with the Pi unplugged and check VCC
> twice before powering on.
>
> **Screw the antenna on before anything transmits.** Transmitting into an open SMA
> connector can damage the module.

SPI0 is the bus `raspi-config` switches on:

```bash
sudo raspi-config nonint do_spi 0       # adds dtparam=spi=on; takes effect after a reboot
ls /dev/spidev0.0                       # present once it is on
```

Pins 35–40 (GPIO 19/20/21/16/26) stay free on purpose: they are where Pi-Somfy wants an
optional *second* CC1101 that listens to physical remotes (open hardware question 4).
[pinout.xyz](https://pinout.xyz) shows every pin interactively.

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
  installing — `apt`, `pip`, `npm` — so build the frontend elsewhere (step 5) and do
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

# a random password, kept root-only: Pi-Somfy's config and the app's config read it from here
sudo sh -c 'umask 077; openssl rand -base64 24 | tr -d "=+/" > /etc/mosquitto/somfy.password'
sudo sh -c 'umask 077; touch /etc/mosquitto/passwd'
sudo mosquitto_passwd -b /etc/mosquitto/passwd somfy "$(sudo cat /etc/mosquitto/somfy.password)"
sudo chown root:mosquitto /etc/mosquitto/passwd && sudo chmod 640 /etc/mosquitto/passwd
sudo systemctl enable --now mosquitto
sudo systemctl restart mosquitto
```

Check it, and that anonymous clients are refused:

```bash
P="$(sudo cat /etc/mosquitto/somfy.password)"
mosquitto_sub -h 127.0.0.1 -u somfy -P "$P" -t 'somfy/#' -v     # Ctrl+C to stop
mosquitto_pub -h 127.0.0.1 -t test -m x                         # expect: not authorised
```

Once Pi-Somfy runs (next step), `somfy/bridge/availability online` shows up in that
subscription.

If nothing appears here, nothing will appear in the app either — fix it at this layer.

> If you keep the app off the Pi, the broker has to listen on the LAN instead
> (`listener 1883 0.0.0.0`). Keep 1883 off the internet regardless: no TLS is
> configured here, and the credentials go over the wire in the clear.

## 3. Pi-Somfy and pigpiod

Pi-Somfy is the transmitter and the only holder of rolling codes (constitution, principle
I). This project talks to it over MQTT only; installing it is still part of the house.

### pigpiod

On a Pi 3 or 4, Pi-Somfy generates the RTS waveform with pigpio, whose daemon times it by
DMA. **Trixie packages no pigpio daemon** — only the Python client — so build it. If
`apt-cache policy pigpiod` shows a candidate on your release, `sudo apt install pigpiod`
replaces the build below.

```bash
sudo apt install -y build-essential unzip python3-pigpio python3-lgpio python3-spidev python3-pip
cd /tmp && curl -fsSL -o pigpio.zip https://github.com/joan2937/pigpio/archive/refs/heads/master.zip
unzip -q pigpio.zip && cd pigpio-master && make -j4          # about a minute on a Pi 3

sudo install -m 0755 pigpiod pigs pig2vcd /usr/local/bin/
sudo install -m 0755 libpigpio.so.1 libpigpiod_if.so.1 libpigpiod_if2.so.1 /usr/local/lib/
sudo install -m 0644 pigpio.h pigpiod_if.h pigpiod_if2.h /usr/local/include/
cd /usr/local/lib && for l in libpigpio libpigpiod_if libpigpiod_if2; do sudo ln -fs $l.so.1 $l.so; done
sudo ldconfig
```

Not `make install`: that also runs `python3 setup.py install` into the system Python, on
top of Debian's `python3-pigpio`.

```bash
sudo tee /etc/systemd/system/pigpiod.service >/dev/null <<'UNIT'
[Unit]
Description=pigpio daemon (built from joan2937/pigpio)

[Service]
Type=forking
# -l: localhost only
ExecStart=/usr/local/bin/pigpiod -l
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now pigpiod
pigs hwver          # prints the board revision, e.g. 10494082 (= a02082, a Pi 3B)
```

### Pi-Somfy

SPI0 has to be on first — see [wiring the radio](#wiring-the-radio). Then, following
upstream's own layout in `/opt/Pi-Somfy`:

```bash
sudo git clone https://github.com/Nickduino/Pi-Somfy.git /opt/Pi-Somfy
cd /opt/Pi-Somfy
sudo python3 -m venv --system-site-packages .venv       # uses the apt pigpio/lgpio/spidev
sudo .venv/bin/pip install -r requirements.txt
curl -fsSL https://raw.githubusercontent.com/ziermach/somfy-shutters/main/deploy/pi-somfy-pi5-detection.patch \
  | sudo git apply
```

**The patch matters.** Unpatched, Pi-Somfy (3.3) decides every Pi on a current kernel is
a Pi 5 — they all have a `/dev/gpiochip4` link now — and sends RTS frames through its
experimental, software-timed lgpio path instead of pigpiod. RTS is one-way, so a badly
timed frame fails silently. See the header of
[`pi-somfy-pi5-detection.patch`](pi-somfy-pi5-detection.patch). Re-apply it after every
`git pull` in `/opt/Pi-Somfy` until upstream fixes the detection.

Its configuration — root-only, it will hold the broker password and every rolling code:

```bash
sudo install -m 600 defaultConfig.conf operateShutters.conf
sudo nano operateShutters.conf
```

| Section | Key | Value |
|---|---|---|
| `[General]` | `RFBackend` | `cc1101` *(add it)* |
| | `CC1101Frequency` | `433.42` *(add it)* |
| | `SendRepeat` | `5` — upstream's recommendation for the CC1101 |
| | `TXGPIO` | `4` — the pin GDO0 is wired to |
| `[MQTT]` | `MQTT_Server` | `127.0.0.1` |
| | `MQTT_User` | `somfy` |
| | `MQTT_Password` | from `sudo cat /etc/mosquitto/somfy.password` |
| | `EnableDiscovery` | `true` — the app finds shutters through these announcements |

Run it as a service with the web UI and MQTT on, and no Alexa (which would need the
internet). `installService.sh` is not executable in the checkout, hence `bash`:

```bash
sudo PI_SOMFY_ARGS="-a -m" bash installService.sh
grep -E "pigpio|lgpio|MQTT" /var/log/operateShutters.log | tail -4
```

Expect `pigpio's pi instantiated` and `somfy/bridge/availability = online`. One
`Disconnected from MQTT (rc=7)` right after start is normal; it reconnects within a
second. Pi-Somfy runs as root, as upstream designs it (port 80, `/dev/spidev0.0`), and
its web UI is at `http://<hostname>.local` — that is where shutters are added and paired.

## 4. Install the app

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

## 5. Build the frontend

The backend serves `frontend/dist` itself, so production is one process on one port.

```bash
sudo apt install -y nodejs npm                    # Vite needs Node 18 or newer
cd /opt/somfy-shutters/frontend
sudo -u somfy npm ci && sudo -u somfy npm run build
```

Easier: skip Node entirely and install a release with `deploy/update.sh` (see
[Updating](#operating-it)) — it downloads the frontend CI built.

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

## 6. Configure

```bash
cd /opt/somfy-shutters
sudo -u somfy install -m 600 config/shutters.example.toml config/shutters.toml
sudo -u somfy nano config/shutters.toml
```

Mode `600`: the file will hold the broker password, and nobody but the app needs to
read it.

`config/shutters.toml` is gitignored — it holds the broker password and this
repository is public. **Shutters do not have to be listed in it.** Pi-Somfy announces
every shutter it knows; the app shows them as "Neuer Rolladen gefunden" and each joins
the household once you give it a name in the app ("Rolladen"). That needs Pi-Somfy's
announcements switched on — `EnableDiscovery = true` in its config, which is its default.

If you do list a shutter by hand, copy its `address` exactly out of Pi-Somfy's
`operateShutters.conf`. A wrong address is completely silent: the radio never answers,
so the app cheerfully animates a shutter that never moved. A hand-listed shutter is
matched to Pi-Somfy's announcement by address and never appears twice.

```toml
[bridge]
kind = "sim"          # start here; switch to "mqtt" in step 8
host = "127.0.0.1"
port = 1883
user = "somfy"
password = "…"
```

Validation is strict and startup fails loudly with the offending line. Leave travel
times out of the file for any window you have not measured: the shutter still
animates on `default_travel_seconds`, marked uncalibrated, and the calibration flow
fills it in.

## 7. Run it as a service

```bash
sudo cp deploy/somfy-shutters.service /etc/systemd/system/
sudo systemctl enable --now somfy-shutters
systemctl status somfy-shutters
```

The unit starts after `mosquitto.service`, restarts on failure, and is confined with
`ProtectSystem=strict` — `config/` is the only writable path, because that is where
the database and the measured calibration live.

Check it. On a Pi 3 the app needs about 20 seconds after `systemctl start` before it
answers — `curl` exits with code 7 (connection refused) until then, and the log shows
`ready: N shutters` once it is up:

```bash
curl -s localhost:8000/api/health
# {"status":"ok"}   — without a credential the health check says nothing about the house
```

With a credential it adds `bridge` and `shutters`; `status` is `ok` even when the bridge
is down, because the service is up and correctly reporting a broken dependency.

Then open `http://<pi-ip>:8000` from a phone on the same network and install it as a
PWA. Do not port-forward it; reach it from outside over a VPN (WireGuard, Tailscale) if
you need to.

### Pairing the first phone

With the simulator the app runs open, so there is nothing to do yet. Once
`bridge.kind = "mqtt"` (step 7) every device needs its own credential. The first one
comes from the Pi itself:

```bash
sudo -u pi /home/pi/somfy-shutters/backend/.venv/bin/somfy-shutters auth recover
# Kopplungscode: K7Q-9XM  (gültig bis 14:32)
```

Open the app on the phone, type the code and a name for the phone. From then on that
phone pairs every further device under **Geräte → Gerät koppeln** — nobody types a long
secret. On an iPhone, pair inside the installed home-screen app, not in Safari first:
the two keep separate cookies.

The same command is the way back in if every device is lost; it touches nothing but
the credentials. `somfy-shutters auth list` shows which exist, without secrets.

**Upgrading an installation from before feature 008:** nothing is migrated or lost, but
after the restart the app shows the pairing screen. Run `auth recover` once, as above.

## 8. Switch to the real radio

Only after the simulator works end to end:

```bash
sudo -u somfy sed -i 's/^kind = "sim"/kind = "mqtt"/' /opt/somfy-shutters/config/shutters.toml
sudo systemctl restart somfy-shutters
journalctl -u somfy-shutters -f
```

Expect `ready: N shutters, bridge=mqtt`. Move one shutter from the app and watch the
window. Two things are worth knowing before you trust it:

- **Pi-Somfy must be v3.1 or newer.** The app speaks its current topics
  (`somfy/<id>/command`, `set_position`, `position`, `state`, `somfy/bridge/availability`,
  and the discovery announcements under `homeassistant/cover/`); older versions used
  `level/cmd` and are not supported. Direction needs no setting — the bridge declares
  100 = open.
- **A shutter added or deleted in Pi-Somfy shows up in the app only after Pi-Somfy
  restarts.** Pi-Somfy announces its shutters, and listens for their commands, only when it
  connects to the broker. The app's "Rolladen hinzufügen" guide includes the restart.
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
| `shutters.toml` | hand-written: broker, hand-listed shutters, measured overrides | yes — it is not in git |
| `calibration.toml` | written by the app: measured travel times | yes — re-measuring costs eight windows of button presses |
| `state.db` | SQLite: the shutters confirmed in the app, groups, rules, last known positions and history | yes — it now holds which shutters belong to the house |

```bash
sudo systemctl stop somfy-shutters
sudo tar czf ~/somfy-backup-$(date +%F).tar.gz -C /opt/somfy-shutters config
sudo chown "$USER" ~/somfy-backup-*.tar.gz
sudo systemctl start somfy-shutters
```

Stop the service first: SQLite is in WAL mode and a live copy can catch a torn write.
`sudo` because the service creates its files readable only by `somfy`.

**Updating from a release** — no Node needed on the Pi. Every `v*` tag pushed to GitHub
builds the frontend in CI and attaches it to the release as `frontend-dist.tar.gz`
(under 300 KB). The script checks out the tag, reinstalls the backend, swaps in the
downloaded frontend after verifying its checksum, and restarts the service:

```bash
sh /opt/somfy-shutters/deploy/update.sh          # newest release
sh /opt/somfy-shutters/deploy/update.sh v0.2.0   # or a given one
```

It leaves the checkout on the tag (detached HEAD); `git pull` then refuses, so either
keep using the script or `sudo -u somfy git -C /opt/somfy-shutters checkout main` first.
The first time, the script is not on the Pi yet — fetch it with
`sudo -u somfy git -C /opt/somfy-shutters pull`.

Cutting a release, on your machine: `git tag v0.2.0 && git push origin v0.2.0`.

**Updating from `main`, building on the Pi:**

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
| Unknown address warnings | An address in `shutters.toml` does not match `operateShutters.conf`. Copy it again — or remove the block and confirm the shutter from Pi-Somfy's announcement in the app. |
| No "Neuer Rolladen gefunden" for a new shutter | Pi-Somfy was not restarted after adding it, or its announcements are off (`EnableDiscovery`). Check with `mosquitto_sub -h 127.0.0.1 -u somfy -P '…' -t 'homeassistant/cover/#' -v`. |
| A long-deleted shutter shows up as new | Pi-Somfy never withdraws an announcement. Name it and remove it again: it then lies under "Beiseitegelegt" and stays out of the way. |
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
