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

**A7 Fallback (US5).** `POST /api/sim/bridge/manage {"available": false}` plays an upstream
bridge without the fork: "+ Rolladen hinzufügen" opens feature 005's guide with the reason, and
`GET /api/setup` says `no_answer`.

## B — The fork on a desk (no motor needed)

The Pi-Somfy fork running against a local Mosquitto, the app pointed at the same broker
(`bridge.kind = "mqtt"`). Watch the wire with
`mosquitto_sub -t 'somfy/bridge/manage/#' -t 'homeassistant/cover/#' -v`.

- Add a shutter in the app → one request, one response with the address,
  `operateShutters.conf` holds it, its announcement appears at once, and it takes commands
  without restarting the bridge.
- "PROG senden" → exactly one `program` request; Pi-Somfy's log shows one PROG frame. Publish
  the same request again by hand with the same `request_id` → answered from the store, **no**
  second frame (idempotency).
- Delete it → its announcement is cleared (empty retained message).
- Stop the fork, start upstream Pi-Somfy instead → `GET /api/setup` says `no_answer` and the app
  falls back to feature 005's guide.

## C — On the motor (pending hardware)

Pair a real motor with its old remote through the app; drive it; unpair and delete it. Then the
power-cycle route with the circuit of one motor, and confirm the timing windows.
