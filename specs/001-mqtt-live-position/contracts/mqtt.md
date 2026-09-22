# Contract: the Pi-Somfy boundary

**External contract — not ours to change.** Pi-Somfy defines these topics; this project
adapts to them. Everything radio-related lives behind this boundary, and nothing on our
side of it has a concept of RTS, rolling codes, or 433.42 MHz.

Source: Pi-Somfy's MQTT integration, configured in its `operateShutters.conf` under
`MQTT_Server`, `MQTT_Port`, `MQTT_User`, `MQTT_Password`.

## Topics

| Topic | Direction | Payload |
|---|---|---|
| `somfy/<address>/level/cmd` | we publish | `0`–`100`, target position |
| `somfy/<address>/level/set_state` | we subscribe | `0`–`100`, Pi-Somfy's current estimate |

`<address>` is the RTS address as it appears in Pi-Somfy's config, e.g. `0x279621`.
We publish only to addresses listed in our own `shutters.toml`; a `set_state` for an
unknown address is logged once and dropped (FR-004).

## Two translations, not one

The payload is a **level**: how far through its travel time the bridge should run
the motor. What the app and its users speak is a **percentage of the window**. The two
coincide only when a shutter's travel curve is neutral, because a motor does not move at
a constant rate.

| | converts | lives in |
|---|---|---|
| direction | which end 0 means | this adapter, below |
| travel curve | level ↔ percentage | `tracker.level_for` and `tracker.percent_from_level` |

The curve is per shutter and comes from calibration (feature 002), which is why it
cannot live down here: the adapter has no idea which shutter has been verified. Keeping
them apart also keeps this file's promise intact — flipping the direction setting is
still sufficient on its own to answer the open hardware question.

## The direction translation

Our whole system uses **100 = fully open, 0 = fully closed** (data-model.md). Which
direction Pi-Somfy expects is [open hardware question 1](../../../CLAUDE.md) and has not
been measured.

**This is the one place the *direction* is decided.** A single setting:

```toml
[bridge]
invert_level = false   # true if Pi-Somfy turns out to use 0 = open
```

```text
publish:   wire_value = invert_level ? 100 - percent : percent
subscribe: percent    = invert_level ? 100 - wire_value : wire_value
```

Nothing else in the codebase may be aware of the question. Flipping the setting must be
sufficient to correct the whole system — that is the acceptance criterion for this
translation, and a unit test asserts both directions round-trip. The travel curve above
is a separate conversion with its own place; the two never appear in the same file.

## What `set_state` actually is

Not a measurement. Pi-Somfy has no feedback from the motor either; it computes this
number from the travel time in its own configuration. Treating it as ground truth would
be wrong, and would also make our animation stutter whenever the two estimates disagree.

The precedence rules are in [research.md §5](../research.md) and implemented in
`tracker.py`. In short: while a command of ours is travelling, our estimate wins; when
we are idle, a report at an end stop is believed and becomes *certain*, a report that
moves while we are idle is believed and stays *estimated*, and small differences are
ignored.

## Commands we do not send

Pi-Somfy also accepts button-level commands and a PROG command. This feature sends
neither — only `level/cmd`. Pairing and programming belong to a later feature, and the
stop action is expressed as a level command at the current position rather than as a
button press.

**Note for that later feature**: stop-as-level is an approximation. A real stop button
halts the motor immediately, while a level command to the current position asks it to
travel to where it already is. If bring-up shows the motor does not stop crisply, the
button-press topic is the fix, and that changes this contract.

## Delivery and failure

MQTT QoS 0 is what Pi-Somfy uses. There is no acknowledgement that a motor moved —
there cannot be, the radio is one-way. So:

- a successful publish means *the broker took it*, nothing more (FR-021)
- a broker that is unreachable makes the command fail visibly; we do not queue it
- the adapter reconnects with backoff (FR-023) and reports its connection state, which
  the UI surfaces as "bridge unreachable"

Queuing commands for later delivery is deliberately **not** done: a shutter that closes
twenty minutes late because the broker came back is worse than one that never closed and
said so.
