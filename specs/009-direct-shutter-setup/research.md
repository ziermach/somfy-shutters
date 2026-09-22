# Research: Setting up shutters directly in the app

Decisions for [plan.md](./plan.md). Statements about the bridge come from Pi-Somfy's current
`webserver.py`, `mqtt.py` and `operateShutters.py` on `master` (read in full, 2026-09-22).

## 1. What the bridge's management interface offers

Pi-Somfy's web server has one command route, `GET|POST /cmd/<command>`, parameters as form or
query values, answers as JSON with HTTP 200 — errors are `{"status": "ERROR", "message": …}`,
still 200. An unknown command or an exception is HTTP 400 with plain text.

| Command | Parameters | Effect | Answer |
|---|---|---|---|
| `getConfig` | — | read everything | `Shutters {id: name}`, `ShutterDurations {id: s}`, … |
| `addShutter` | `name`, `duration` | next free id after `RTS_Address` and every known id, rolling code 1, written to `operateShutters.conf` | `{"status": "OK", "id": "0x279625"}` |
| `program` | `shutter` (id) | transmits the RTS PROG frame once, advancing that shutter's rolling code | `{"status": "OK"}` |
| `editShutter` | `id`, `name`, `duration` | rename / new duration | `{"status": "OK", "nameChanged": bool}` |
| `deleteShutter` | `id` | marks it disabled in the config, forgets it in memory | `{"status": "OK"}` |

- **Names**: unique in the bridge; a comma is refused; Python 3 keeps any other character. The
  bridge's discovery shows `_` as a space and title-cases the name.
- **Duration** is stored as given and used as `int(float(duration))` seconds, up and down.
- **Passwords**: only `up`/`down`/`stop` and the main page check the `Password` header. The
  management commands check nothing. Consequence in §6.

**Decision**: a `PiSomfyManager` in `bridge/manage.py` — the only file that knows these
command names — with `add(name, seconds) -> address`, `program(address)`, `rename(address,
name, seconds)`, `delete(address)`, `probe()`. It always sends the `Password` header when one is
configured, so it keeps working if the bridge starts checking it.

**Alternatives**: MQTT commands added to the bridge (way B) — cleaner for the constitution but a
larger fork of the bridge; driving the bridge's HTML — brittle. Rejected by the owner in favour
of A.

## 2. A new shutter commandable without a bridge restart — the patch

`addShutter` writes the config and nothing else. The MQTT module subscribes to a shutter's
`command`/`set_position` topics and announces it only in `on_connect`. The web server and the
MQTT thread are built separately in `operateShutters.py` and never refer to each other.

**Decision**: a small patch in `deploy/`, next to the one already shipped
(`pi-somfy-pi5-detection.patch`):

- `operateShutters.py` hands the MQTT object to the web server (`mqtt=self.mqtt`, or None).
- `MQTT.announceShutter(id)`: subscribe to both topics, publish its discovery message (when
  discovery is on).
- `MQTT.withdrawShutter(id)`: unsubscribe, publish an **empty retained** message on its
  discovery topic — the standard way to clear it.
- `addShutter` → `announceShutter`; `editShutter` with a changed name → `announceShutter` again;
  `deleteShutter` → `withdrawShutter`.

The patch is on the bridge's side, in the bridge's namespace: the *bridge* clears its own
announcement. The app still never publishes under `homeassistant/#`.

**Detecting it**: the app does not probe versions. After `addShutter` it waits up to 5 s for a
**live** announcement of the new address. It arrives → patched, the shutter is commandable. It
does not → unpatched: the flow says "Pi-Somfy einmal neu starten" before pairing (the restart
is also what makes the bridge subscribe), and the deploy guide points to the patch.

## 3. Pairing and unpairing are the same signal

RTS: a motor in learning mode (PROG held on a remote it knows, or the power-cycle sequence)
learns the next sender that sends PROG. A sender it already knows, sending PROG while the motor
is in learning mode, is *removed*. So:

- pairing = learning mode + `program(address)` once;
- "Motor soll die Funkbrücke vergessen" = learning mode + `program(address)` once more;
- a second PROG during the same learning mode undoes the first. **Decision**: after "Hat
  gewackelt" the flow closes; another PROG needs an explicit new pairing (spec edge case).

One `program` per press (FR-008). Requests for the same address are serialised; a press while
one is in flight is refused (409 `busy`).

## 4. The power-cycle sequence

From the mock and the usual SIMU/Somfy procedure: off 2–8 s, on 10–15 s, off 2–8 s, on — then
the motor jogs and is in learning mode for about two minutes. The app cannot switch power;
it times the person's presses (client-side, a pure function in `lib/setup.ts`, tested). A step
outside its window marks the run failed; "PROG senden" is offered only after a clean run
(FR-013). Values are constants in one place, flagged for confirmation on the motors.

## 5. Where a created-but-unpaired shutter lives

**Decision**: in `household_shutter` with `pairing = 'unpaired'`, **not** in `settings.shutter`.
So it is invisible to "all shutters", groups and automations (FR-011), and it is not "new" either
(its address is in the table). "Hat gewackelt" sets `pairing = 'paired'` and appends it to
`settings.shutter` — the same join feature 005 uses for confirming. Rows from feature 005 are
paired by definition (migration default).

The estimated travel time is stored on the row (`estimate_seconds`) and sits in feature 002's
precedence below measured values and above the general default: hand-written > measured >
estimate > default.

## 6. Security

- Every new route requires **configure** (feature 008), including `program`: pairing a motor is
  configuration, and a stray PROG can pair the wrong motor. Each `program` is recorded in the
  audit log with actor, address and outcome, besides the gate's own change entry.
- The bridge password lives in `shutters.toml` (`bridge.manage_password`), never in any
  response.
- Pi-Somfy's management commands are unauthenticated on its own port. That is the bridge's
  exposure today, independent of this feature; the deploy guide recommends binding Pi-Somfy's
  web server to loopback once the app is the interface (`bridge.manage_url =
  "http://127.0.0.1:80"`, same Pi).

## 7. Removing in the bridge — order and failure

1. Optional unpair (§3): guided, a `program` after the person confirms learning mode.
2. `delete(address)` in the bridge.
3. Feature 005's cascade in the app; the row becomes `state = 'deleted'` (a tombstone).

Step 2 failing stops before step 3: nothing is removed half-way; the answer names what was done
(e.g. "Motor hat vergessen, Löschen in der Funkbrücke fehlgeschlagen") and offers retry or
"nur aus der App entfernen" (feature 005's set-aside). The tombstone keeps a deleted shutter out
of "new" even on an unpatched bridge whose retained announcement lingers (SC-006); a later
*live* announcement of that address (the person re-created it in the bridge) clears it.

## 8. Names in the bridge

`bridge_name(name)`: umlauts transliterated, other non-ASCII dropped, commas removed, spaces →
`_` (the bridge's own discovery turns `_` back into spaces), at most 40 characters; on "Name is
not unique" a suffix `_2`, `_3`. The person only ever sees the app's name (FR-017).

## 9. Fallback

`bridge.manage_url` unset, or `probe()` (`getConfig`) failing → management unavailable. `GET
/api/setup` says so with a reason; the frontend opens feature 005's guide with the reason on top
(FR-018). Management is re-probed on each flow start, not cached for long.

## 10. The simulator

`SimBridge` gains the management side in `SimManager`: `add` (patched behaviour by default,
unpatched selectable with `POST /api/sim/bridge/patched {"patched": false}`), `program`, `rename`,
`delete`. Each `SimShutter` gets `paired` and `learning_until`: a motor ignores commands unless
paired; `POST /api/sim/window/{address}/learn` plays "PROG held on the old remote" (learning for
120 s); a `program` while learning toggles `paired` and ends learning — so "Nichts passiert" is
reproducible by simply not calling `learn`.
