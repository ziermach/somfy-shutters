# Quickstart: validating adding and removing shutters

Scenarios mapped to [spec.md](./spec.md); API in [contracts/rest.md](./contracts/rest.md).

## A — Simulator

`config/shutters.toml` with `bridge.kind = "sim"`. The simulated bridge knows every
configured shutter and every shutter in the app's table; a person working in Pi-Somfy's
interface is played with the sim-only endpoints below.

**A1 Take over (US1).** Give the simulated bridge three shutters the app does not know
yet, as if they had been set up in Pi-Somfy before the app was installed:

```bash
for n in Bad Gästezimmer Arbeitszimmer; do
  curl -XPOST localhost:8000/api/sim/bridge/shutters -H 'content-type: application/json' -d "{\"name\":\"$n\"}"
done
curl -XPOST localhost:8000/api/sim/bridge/restart
```

The overview says "3 neue Rolladen gefunden" (new, not yet in the household — FR-002);
under "Rolladen" confirm each with a name. They appear on the overview, "Laufzeit nicht
gemessen". The hand-configured ones are there once, unchanged (automated:
`tests/integration/test_roster_takeover.py`).

**A2 Add, guided (US2).** "Rolladen hinzufügen" → read the steps → in another terminal play
the person working in the bridge:

```bash
curl -XPOST localhost:8000/api/sim/bridge/shutters -H 'content-type: application/json' -d '{"name":"Bad"}'
# nothing appears — the bridge does not announce before a restart
curl -XPOST localhost:8000/api/sim/bridge/restart
```

The open guide jumps to "Neuer Rolladen gefunden: Bad" within 5 s. Name it, finish: it is on
the overview and offered for measurement.

**A3 Nothing appears (US2 scenario 4).** Start the guide, do nothing for ten minutes (or
shorten via the test clock) — the guide lists the usual causes, restart first.

**A4 Remove (US3).** Put "Bad" in a group and a rule, remove it. The confirmation names the
group and the rule; afterwards neither mentions it, the rule without targets says "kein
Rolladen mehr", and the simulator received nothing. It shows under "beiseitegelegt"
(still announced) and can be restored.

**A5 The bridge forgets (US4).**

```bash
curl -XDELETE localhost:8000/api/sim/bridge/shutters/<address of "Bad">
curl -XPOST localhost:8000/api/sim/bridge/restart
```

Within a minute the shutter reads "Funkbrücke kennt diesen Rolladen nicht mehr", buttons
disabled, settings kept; a command via the API is 409 `forgotten`.

**A6 Power cycle route (US5).** In the guide choose "keine Fernbedienung mehr": the
power-cycle steps and the shared-circuit warning appear before the programming step.

## B — Local Mosquitto impersonating Pi-Somfy

As in feature 006's quickstart B. Announce a shutter the way Pi-Somfy does:

```bash
mosquitto_pub -t somfy/bridge/availability -m online -r
mosquitto_pub -r -t homeassistant/cover/pisomfy_0x279630/config -m \
 '{"name":"Bad","unique_id":"pisomfy_0x279630","command_topic":"somfy/0x279630/command",
   "device":{"configuration_url":"http://pi-somfy.local/"}}'
```

→ "Neuer Rolladen gefunden: Bad", `web_url` in `GET /api/roster`. Restart the bridge's
announcements without that shutter (publish `offline` then `online`, and re-publish only the
others without `-r` inside 30 s) → it is marked forgotten.

## C — On the Pi (pending hardware)

Add a shutter in Pi-Somfy's interface, program it, restart Pi-Somfy — the app finds it.
Delete it in Pi-Somfy, restart — the app marks it forgotten.
