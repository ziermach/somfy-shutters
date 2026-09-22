# Quickstart: validating shutter setup in the app

Scenarios mapped to [spec.md](./spec.md); API in [contracts/rest.md](./contracts/rest.md).

## A — Simulator (`bridge.kind = "sim"`, management built in)

**A1 Add with the old remote (US1).** "Rolladen" → "+ Rolladen hinzufügen" → name
"Kinderzimmer", 20 s → the pairing step shows the address the bridge chose. Play the person at
the window, then press "PROG senden" in the app:

```bash
curl -XPOST localhost:8000/api/sim/window/<address>/learn
```

"Hat gewackelt" → on the overview, drivable at once, "Laufzeit nicht gemessen", measurement
offered. `GET /api/sim/bridge/programs` lists exactly one request. The audit record ("Geräte →
Protokoll") shows it with this device's name.

**A2 Nothing happened (US1 scenario 5).** Same, but skip the `learn` call: "Nichts passiert" →
the hint, attempt 2; call `learn`, send again → paired.

**A3 Abandon and resume (FR-011).** Create, close the flow before pairing: the shutter is under
"Nicht angelernt", absent from the overview and from "Alle zu"; "Anlernen fortsetzen" reopens
the pairing step.

**A4 Power cycle (US2).** In the pairing step "Keine Fernbedienung mehr vorhanden?" → warning →
time the four steps, one deliberately too short → flagged, "neu starten"; a clean run → "PROG
senden".

**A5 Remove everywhere (US3).** Remove "Kinderzimmer" with "auch in der Funkbrücke löschen" and
"Motor soll die Funkbrücke vergessen": call `learn` when asked, confirm → one more program
request, gone from the app and from `GET /api/sim/bridge/shutters`, not under "Beiseitegelegt",
not new after `POST /api/sim/bridge/restart`.

**A6 Rename (US4).** Rename to "Kinder Zimmer" → the simulated bridge holds `Kinder_Zimmer`.

**A7 Unpatched bridge.** `POST /api/sim/bridge/patched {"patched": false}`, add a shutter → the
flow asks for a Pi-Somfy restart before pairing; `POST /api/sim/bridge/restart` → continues.

**A8 Fallback (US5).** Start with `bridge.manage_url` removed from a `kind = "mqtt"` config (or
`POST /api/sim/bridge/manage {"available": false}`): "+ Rolladen hinzufügen" opens feature 005's
guide with the reason.

## B — Real Pi-Somfy on a desk (no motor needed)

Pi-Somfy running with the `deploy/` patch applied, the app pointed at it
(`bridge.kind = "mqtt"`, `bridge.manage_url = "http://127.0.0.1:80"`). Add a shutter in the app
→ `operateShutters.conf` has it with the address shown in the app; `mosquitto_sub -t
'homeassistant/cover/#' -v` shows its announcement at once; delete it → the announcement is
cleared (empty retained message). "PROG senden" → Pi-Somfy's log shows one program frame.

## C — On the motor (pending hardware)

Pair a real motor with its old remote through the app; drive it; unpair and delete it. Then the
power-cycle route with the circuit of one motor, and confirm the timing windows.
