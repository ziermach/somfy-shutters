# Contract: MQTT addition — the bridge's announcements

Extends [feature 006's contract](../../006-pisomfy-mqtt-topics/contracts/mqtt.md). Still only
in `bridge/mqtt.py`.

## Inbound, added

| Topic | Payload | Becomes |
|---|---|---|
| `homeassistant/cover/+/config` | Pi-Somfy's discovery JSON, retained | `Announcement(address, name, web_url, retained)` |

- `address` is parsed from the payload's `command_topic` (`somfy/<id>/command`) and
  lower-cased; the topic segment `<bridge_id>_<id>` is not relied on.
- `name` is the payload's `name`; `web_url` is `device.configuration_url` when present.
- A payload without a `command_topic` of that shape, or not JSON, is ignored — other
  integrations publish covers under the same prefix. An **empty** payload (how a retained
  message is cleared) is passed up as a withdrawal of that topic's announcement, in case a
  later bridge version clears deleted shutters.
- `retained` is the received message's retain flag, as in feature 006.

## Outbound

Unchanged. Nothing is ever published to `homeassistant/#`: those topics belong to the bridge
(constitution, principle II).
