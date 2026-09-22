# Research: Speaking the radio bridge's current interface

Decisions for [plan.md](./plan.md). The source for every statement about the bridge is
Pi-Somfy's `mqtt.py` on `master` (last changed 2026-08-01, interface introduced in v3.1,
2026-03-27), read in full, not summarised.

## 1. What the bridge actually does

| Topic | Direction | Payload | Notes |
|---|---|---|---|
| `somfy/<id>/command` | we publish | `OPEN` \| `CLOSE` \| `STOP` | anything else is logged and ignored by the bridge |
| `somfy/<id>/set_position` | we publish | integer | `>= 100` → full rise, `<= 0` → full lower, else a partial move **relative to the bridge's own position**; equal to it → **nothing happens** |
| `somfy/<id>/position` | bridge publishes, **retained** | integer 0–100 | on every position change, and for every shutter right after the bridge connects |
| `somfy/<id>/state` | bridge publishes, **retained** | `opening` \| `closing` \| `open` \| `closed` \| `stopped` | `opening`/`closing` fire for software *and* physical-remote movement (the latter only with the receiver enabled); `open`/`closed`/`stopped` follow every position change |
| `somfy/bridge/availability` | bridge publishes, retained, last will | `online` \| `offline` | `online` on connect, `offline` by LWT when the process dies |
| `homeassistant/cover/<bridge>_<id>/config` | bridge publishes, retained | discovery JSON | only with discovery enabled; used by feature 005, not here |

Discovery declares `position_open: 100`, `position_closed: 0`. `<id>` is the key of the
shutter in the bridge's `[Shutters]` config section — the radio address.

## 2. The port grows by one verb

- **Decision**: `ShutterBridge` keeps `send_level(address, percent)` for positions and gains
  `send_stop(address)`. The MQTT adapter maps `send_level(100)` → `command OPEN`,
  `send_level(0)` → `command CLOSE`, anything else → `set_position`.
- **Why not three new verbs** (`open`, `close`, `position`): end stops are already expressed
  as levels 0 and 100 everywhere above the port — commands, automations, calibration, the
  bridge-counter logic of feature 002. Mapping them to OPEN/CLOSE in the one file that knows
  topics keeps every caller unchanged. Stop is different in kind — it is not a position —
  so it gets its own verb.
- **Why explicit OPEN/CLOSE** when `set_position 100` would do the same: the command topic is
  the bridge's primary interface; if a later version drops the `>= 100` shortcut, end stops
  still work (FR-003).
- **Callers to change**: `commands.apply` (stop), calibration abort (halt). Both use
  `tracker.halt_level()` today; they call `send_stop` instead, and the tracker still settles
  where the movement stood (feature 001's stop semantics are unchanged on our side).

## 3. Reports carry what kind they are, and whether they are old news

- **Decision**: `Report` gains `kind` (`position` \| `movement`), `state` (for movements) and
  `retained` (true when the broker delivered it from its store rather than live).
  aiomqtt exposes the retain flag on received messages; retained messages arrive exactly
  on subscribe.
- **Retained positions (FR-007)**: `tracker.handle_report(..., retained=True)` fills a position
  only if the app's is unknown, records the bridge counter (feature 002's relative commands
  need it), and emits nothing else — no correction, no glide, no external movement. A known
  position is left alone: the app's own record is newer knowledge than the broker's store.
- **Retained movement states** are ignored entirely: an `opening` from before a restart
  describes nothing current.
- **Live movement states (FR-006)**:
  - during our own travel or the bridge's run for our command (feature 001's bridge-run
    window): ours, ignored;
  - otherwise `opening`/`closing` marks the shutter as **moved by someone else** from that
    instant: the position stays an estimate, `certain_at` is refreshed as feature 001 does for
    external movement, and following position reports are accepted as corrections without
    waiting for the two-report heuristic;
  - `stopped`/`open`/`closed` end that state; the accompanying position report carries the
    value.
- The old heuristic (two reports within 3 s, ≥ 2 pp apart) stays as the fallback for bridges
  whose receiver is off, which send no `opening`/`closing` for remotes.

## 4. "Reachable" means broker and bridge

- **Decision**: the adapter subscribes to `somfy/bridge/availability`. `connected` is true only
  while the broker connection is up **and** the last availability payload was `online`
  (FR-010). No availability message at all counts as not reachable: a bridge that never
  started has not announced itself, and its LWT is retained, so a bridge that ever ran is
  always known one way or the other.
- The connection callbacks feature 001 already fires on changes carry this combined value,
  so the banner, the command refusal and the WebSocket frame need no change.

## 5. Topic spelling of the identity

- The bridge builds topics from the key in its config, which a person typed, e.g.
  `0x279621` or `0X279621`. Our config normalises addresses to lower case.
- **Decision**: incoming topics are matched case-insensitively. The adapter remembers the
  spelling it last saw for each address on any bridge topic (the retained burst on connect
  supplies all of them) and publishes with that spelling; until one is seen, it uses the
  configured address. No config change for anybody, and a mismatch cannot silently drop
  commands once the bridge has spoken.

## 6. The direction switch

- The bridge now declares 100 = open. `invert_level` stays readable (removing it would make
  old configs fail validation, since config rejects unknown keys) but is **ignored**; at
  start the app logs one warning if it is set to true (FR-012). The test that guarded "only
  mqtt.py knows about inversion" becomes a test that inversion is gone.

## 7. The simulator

- **Decision**: `SimBridge` implements the new port and emits the new report kinds:
  position reports (its linear belief, as now) marked live during travel; a movement report
  `opening`/`closing` at the start and `open`/`closed`/`stopped` at the end; on `start()` a
  retained burst of every shutter's position and last state; availability `online` on start,
  `offline`/`online` from `set_connected`. `send_stop` halts its motor where it is.
- Simulator-only endpoints: `/api/sim/report` keeps injecting a live position;
  a new `POST /api/sim/movement {shutter_id, state}` injects a live movement report, for
  walking the external-movement path by hand.
- Every existing scenario of features 001–004 must pass against it (SC-006).

## 8. The adapter is tested without a broker

- `MqttBridge._handle(topic, payload, retain)` and `_publish_plan(address, verb, value)` are
  pure; unit tests feed them the exact topic/payload shapes of §1. A fake client records
  publishes. No Mosquitto in CI.
- The quickstart includes an optional walk against a real local Mosquitto using
  `mosquitto_pub`/`mosquitto_sub` to impersonate the bridge — the closest thing to hardware
  on a laptop.

## 9. Constitution amendment

- Principle II names `level/cmd` and `level/set_state`. **Decision**: amend to name the
  current topics, keep the principle's rule and rationale verbatim. Version 1.0.0 → 1.1.0
  (the principle's guidance is materially updated; nothing is removed or redefined), with a
  Sync Impact Report. CLAUDE.md, README and feature 001's MQTT contract follow.

## 10. What is not changed

- Feature 002's relative commands rest on the bridge timing the motor on its own linear
  position. The new `set_position` computes partial moves from `getPosition()`, the same
  counter — so the counter tracking and travel curve carry over unchanged.
- Discovery (feature 005) is out of scope; the adapter ignores `homeassistant/#`.
