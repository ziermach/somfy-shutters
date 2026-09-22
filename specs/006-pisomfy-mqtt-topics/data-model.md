# Data model: Speaking the radio bridge's current interface

No new tables, no stored data changes. Everything here is in-memory shapes at the port
between the app and whatever moves the shutters.

## Report (extended) — `bridge/base.py`

| Field | Type | Rules |
|---|---|---|
| `address` | str | configured address, lower case (inbound ids are matched case-insensitively) |
| `kind` | `position` \| `movement` | |
| `percent` | int \| None | 0–100; set for `position`, None for `movement` |
| `state` | `opening` \| `closing` \| `open` \| `closed` \| `stopped` \| None | set for `movement` |
| `retained` | bool | true only for messages delivered from the broker's store on subscribe |

Existing constructions `Report(address, percent)` keep meaning a live position report
(defaults `kind="position"`, `retained=False`), so feature 001–004 code and tests that build
reports stay valid.

## Port — `ShutterBridge`

| Member | Change |
|---|---|
| `send_level(address, percent)` | unchanged signature; 0 and 100 become OPEN/CLOSE in the adapter |
| `send_stop(address)` | **new**; explicit stop |
| `connected` | now broker **and** bridge availability |
| `reports()` | yields extended `Report`s |
| `on_connection_change(cb)` | unchanged; fires on the combined value |

## Tracker reaction to reports

| Report | Tracker already has a position | Tracker has none |
|---|---|---|
| position, retained | nothing emitted; bridge counter recorded | position filled (end stop → certain, else estimated), bridge counter recorded |
| position, live | feature 001 reconciliation, unchanged | as today |
| movement, retained | ignored | ignored |
| movement `opening`/`closing`, live, during our travel or bridge run | ignored | ignored |
| movement `opening`/`closing`, live, otherwise | shutter marked externally moving; `certain_at` refreshed; next position reports accepted as corrections | same |
| movement `open`/`closed`/`stopped`, live | ends external movement; the position report carries the value | same |

"Externally moving" is transient state in the tracker, not persisted; a restart forgets it,
and the retained burst on reconnect cannot recreate it (retained movements are ignored).

## Configuration

| Key | Change |
|---|---|
| `bridge.invert_level` | still accepted; ignored; warning at start when true |
| everything else | unchanged — addresses, travel times, timezone, location |
