# Research: Setting up shutters directly in the app

Decisions for [plan.md](./plan.md). Statements about the bridge come from Pi-Somfy's current
`webserver.py`, `mqtt.py` and `operateShutters.py` on `master` (read in full, 2026-09-22).

## 1. Fork, not patches — and not the web route

The bridge offers what this feature needs only through its Flask command route
`GET|POST /cmd/<command>`: `addShutter` (the bridge picks the id), `program` (transmits the RTS
PROG frame), `editShutter`, `deleteShutter`, `getConfig`. Over MQTT it offers nothing of the
kind. Three ways were weighed:

| | Approach | Why not / why |
|---|---|---|
| A | The app calls `/cmd/` | Needs an exception to principle II for web routes, a second port in the app, and Pi-Somfy's management commands check **no password at all** (only `up`/`down`/`stop` and the main page do), so the app would lean on an unauthenticated surface. Two patch files against a foreign `master` would still be needed. |
| **B** | **Fork Pi-Somfy; the fork speaks MQTT for management** | **Chosen.** Driving and managing then share one boundary; access control is the broker's, which already has user and password; the app keeps one adapter; the deploy is a clone instead of a clone plus patches. |
| C | The app transmits itself | Rolling codes and RTS timing rebuilt from scratch; principle I exists to prevent exactly this. Rejected. |

**Decision**: a fork, `ziermach/Pi-Somfy`, branch `somfy-shutters`, kept rebaseable on upstream
and written so each change can be offered as a pull request to `Nickduino/Pi-Somfy`. The
existing `deploy/pi-somfy-pi5-detection.patch` folds into it as its first commit; `deploy/`
then clones the fork instead of patching upstream.

**Consequence for the constitution**: principle II is *extended*, not broken — two more topics
in the same `somfy/` namespace. Flask routes, HTML, database and config files stay off limits.

## 2. What the fork adds

**A management channel** (in `mqtt.py`, the file that already owns every topic):

- subscribe `somfy/bridge/manage/request` on connect;
- answer on `somfy/bridge/manage/response`, **not retained**;
- one JSON request, one JSON response, correlated by `request_id`
  ([contracts/mqtt-manage.md](./contracts/mqtt-manage.md)).

Handlers call the functions the web routes already call — `config.WriteValue`,
`shutter.program`, the same name and duration checks — so behaviour stays identical whichever
interface is used, and the diff is small enough for a pull request.

**Announcing without a restart**: today a shutter is subscribed and announced only in
`on_connect`, so one added through any interface is deaf until the bridge restarts. The fork
adds `announceShutter(id)` (subscribe both command topics, publish its discovery message) and
`withdrawShutter(id)` (unsubscribe, publish an **empty retained** message on its discovery
topic), called from add, rename and delete — including from the web route, so Pi-Somfy's own
interface benefits too. That is the part most worth upstreaming.

**Idempotency**: `program` must never be sent twice by accident — a second PROG during one
learning mode *undoes* the pairing (§3). Management is published at QoS 1, which may deliver
twice, so the fork remembers the last 32 `request_id`s and answers a repeat with the stored
response instead of acting again.

**Nothing else changes.** No new dependency in the fork; `sendMQTT` gains a `retain` argument
because responses must not be retained.

## 3. Pairing and unpairing are the same signal

RTS: a motor in learning mode (PROG held on a remote it knows, or the power-cycle sequence)
learns the next sender that sends PROG; a sender it already knows, sending PROG while in
learning mode, is removed. So pairing = learning mode + one `program`; "Motor soll die
Funkbrücke vergessen" = learning mode + one more `program`.

**Decisions**: one `program` per press of "PROG senden" (FR-008), never retried by the app;
requests for one shutter serialised (a press while one is in flight → 409 `busy`); after "Hat
gewackelt" the flow closes, and another PROG needs an explicit new pairing.

## 4. The power-cycle sequence

From the mock and the usual SIMU/Somfy procedure: off 2–8 s, on 10–15 s, off 2–8 s, on — then
the motor jogs and is in learning mode for about two minutes. The app cannot switch power; it
times the person's presses (a pure function in `lib/setup.ts`, tested). A step outside its
window marks the run failed; "PROG senden" is offered only after a clean run (FR-013). The
windows are constants in one place, flagged for confirmation on the motors.

## 5. Where a created-but-unpaired shutter lives

**Decision**: in `household_shutter` with `pairing = 'unpaired'`, **not** in `settings.shutter`.
So it is invisible to "all shutters", groups and automations (FR-011), and not "new" either (its
address is in the table). "Hat gewackelt" sets `pairing = 'paired'` and appends it to
`settings.shutter` — the join feature 005 already uses. Rows from feature 005 are paired by
definition (migration default).

The travel time typed at creation is stored on the row (`estimate_seconds`) and sits in feature
002's precedence below measured values: hand-written > measured > estimate > default.

## 6. Security

- Every setup route requires **configure** (feature 008), `program` included: a stray PROG can
  pair the wrong motor. Each `program` is recorded in the audit log with actor, address and
  outcome, on top of the gate's own change entry.
- Access control for management is the broker's, as for driving: whoever may publish to
  `somfy/#` may manage. No new secret in the app, no password in any response.
- The fork does **not** expose management over HTTP beyond what Pi-Somfy already does; its
  unauthenticated `/cmd/` surface is untouched by us. The deploy guide recommends binding the
  bridge's web server to loopback once the app is the interface.

## 7. Removing in the bridge — order and failure

1. Optional unpair (§3): guided, one `program` after the person confirms learning mode.
2. `delete` over the management channel.
3. Feature 005's cascade in the app; the row becomes `state = 'deleted'` (a tombstone).

Step 2 failing stops before step 3 — nothing is removed half-way. The answer names what was
done ("Motor hat vergessen, Löschen in der Funkbrücke fehlgeschlagen") and offers retry or "nur
aus der App entfernen" (feature 005's set-aside). The tombstone also keeps a deleted shutter out
of "new" if an old retained announcement lingers (an unforked bridge); a later **live**
announcement of that address clears it.

## 8. Names in the bridge

The bridge refuses a comma and requires a unique name; its discovery turns `_` into a space.
`bridge_name(name)`: umlauts transliterated, other non-ASCII dropped, commas removed, spaces →
`_`, ≤ 40 characters; on "name is not unique" a suffix `_2` … `_9`. The person only ever sees
the app's name (FR-017).

## 9. Fallback when the bridge cannot be managed

An upstream bridge (no fork) never answers on the management channel. **Decision**: no version
probe — a request that goes unanswered for 5 s is `management_unavailable`; the result is cached
until the bridge's availability changes, so one timeout does not cost every screen five seconds.
`GET /api/setup` reports it, and the frontend opens feature 005's guide with the reason
(FR-018). Feature 005 stays in full: the guide, announcements, set aside, forgotten.

## 10. The simulator

`SimBridge` gains the management side behind the same port: `add` (assigns the next address,
announces it live at once, as the fork does), `program`, `rename`, `delete`. Each `SimShutter`
gets `paired` and `learning_until`: an unpaired motor ignores commands;
`POST /api/sim/window/{address}/learn` plays "PROG held on the old remote" (learning for 120 s);
a `program` while learning toggles `paired` and ends learning — so "Nichts passiert" is
reproduced by simply not calling `learn`. `POST /api/sim/bridge/manage {"available": false}`
plays an unforked bridge for the fallback scenario.
