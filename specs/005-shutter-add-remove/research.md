# Research: Adding and removing shutters

Decisions for [plan.md](./plan.md). Statements about the bridge come from Pi-Somfy's
current `mqtt.py` and `webserver.py` on `master` (read in full, 2026-09-22).

## 1. What the bridge announces, and when

- **Per shutter**: `homeassistant/cover/<bridge_id>_<id>/config`, **retained**, JSON with
  `name` (display name, `_` → space, title case), `unique_id` `<bridge_id>_<id>`,
  `command_topic` `somfy/<id>/command`, and — when the bridge can detect it —
  `device.configuration_url`, the address of its web interface.
- **Only on connect.** `sendStartupInfo()` runs from the bridge's MQTT `on_connect`. The
  same handler subscribes to each shutter's command topics.
- **`addShutter` publishes nothing and subscribes to nothing.** A shutter created in the
  bridge's interface is neither announced nor commandable over MQTT until the bridge's MQTT
  client reconnects — in practice, until the bridge is restarted.
- **`deleteShutter` withdraws nothing.** It marks the shutter disabled in the bridge's config
  and forgets it in memory; the retained announcement stays on the broker, across restarts.
- Announcements depend on `EnableDiscovery = true` in the bridge's config (the default).

**Consequence**: the spec's assumptions were corrected (spec, Assumptions). Adding needs a
bridge restart in the guide; "forgotten" means "missing from the fresh announcements after
the bridge's next restart".

## 2. Learning the roster: retained vs. live announcements

- The adapter subscribes to `homeassistant/cover/+/config` (feature 006 excluded it; this
  feature adds it). Each message yields an **announcement**: address (parsed from
  `command_topic`, the only field that carries the bridge's own id), display name, the web
  address if present, and the MQTT retain flag.
- **Retained** announcements (delivered on our subscribe) describe what the bridge knew at
  some point — possibly a shutter deleted since.
- **Live** announcements arrive when the bridge (re)connects while we are subscribed; with
  our subscription active, a bridge restart delivers every current shutter live.
- **Decision — "forgotten"**: on each bridge `online` transition (feature 006's availability)
  a 30-second window opens. Active shutters learned from the bridge that are **not**
  announced live within the window are marked **forgotten** (FR-017, within 60 s of the
  restart). A live announcement at any later time clears it.
- **Why not clear the stale retained announcement ourselves**: publishing to the bridge's
  discovery topics is writing into its namespace. Principle II allows us `command` and
  `set_position` outbound, nothing else.
- **First start with no live window yet** (app starts while the bridge has been up for
  hours): only retained announcements exist; nothing is marked forgotten until the next
  bridge restart. A stale retained announcement of a deleted shutter would appear as
  "new" — the person can set it aside (FR-016); the guide text says so.

## 3. The roster becomes mutable — at one place

36 call sites read `settings.shutters` / `settings.by_address()`, which derive from the
`settings.shutter` list loaded from `shutters.toml`.

- **Decision**: a `Roster` service owns the household's shutters. At start it builds
  `settings.shutter` from (a) `shutters.toml` entries, unchanged, and (b) active entries in a
  new `household_shutter` table; adding or removing mutates `settings.shutter` in place, so
  every existing reader sees the change on its next lookup with no call site edited.
- **Per-shutter state that the roster must also add/remove**: tracker position and
  bridge-counter entries (`Tracker.add_shutter` / `remove_shutter`), the simulator's shutter
  (sim only), group memberships (`GroupStore.prune`, feature 004), rule targets (a new
  `AutomationStore.remove_shutter`, mirroring feature 004's group removal), calibration
  values and runs (`CalibrationService.clear`, feature 002), and the stored position row.
- **Hand-configured shutters** (in `shutters.toml`) are never written by the app, so they
  cannot be removed from it (FR-004); the app says where to remove them. They are matched
  to announcements by address and never duplicated (FR-003).

## 4. Identity

- **App id**: a slug of the confirmed name (`[a-z0-9_-]`, umlauts transliterated, unique by
  suffix), fixed at confirmation; later renames change the name only, never the id — groups,
  rules, calibration and history key on it.
- **Address**: from the announcement's `command_topic`, lower-cased like every configured
  address (feature 006 already matches case-insensitively and publishes in the bridge's
  spelling).

## 5. New, set aside, forgotten

| State | Where | Meaning |
|---|---|---|
| `new` | memory (from announcements) | announced, not in the roster, not set aside |
| `active` | `household_shutter` or `shutters.toml` | part of the household |
| `set_aside` | `household_shutter` | removed by a person while still announced; not offered as new (FR-016) |
| `forgotten` | memory flag on an active bridge shutter | not re-announced after the last bridge restart |

- New shutters are **not** in `settings.shutter`, so "all shutters", groups and automations
  never see them (FR-002).
- Forgotten shutters stay in the roster; `commands.apply` refuses them with
  `ShutterForgotten` (409 `forgotten`), the automation engine records them as skipped with
  reason `forgotten`, and the UI disables their buttons (FR-017).

## 6. Detection latency

The adapter hands announcements up as they arrive; the roster publishes a WebSocket frame on
every change of the new/forgotten sets. An open guide sees a new shutter within a message's
round trip (FR-008, 5 s).

## 7. Link to the bridge

The guide's "Pi-Somfy öffnen" link uses `configuration_url` from any announcement; an optional
`bridge.web_url` in `shutters.toml` overrides it; without either, the guide is text only.
Opening a link is the person's action in their browser — the app never requests the bridge's
pages (principle II).

## 8. The simulator

- Announces every shutter as retained on start, and live again on every `set_connected(True)`
  (its model of a bridge restart).
- Sim-only endpoints model the bridge's own interface for tests and the quickstart:
  `POST /api/sim/bridge/shutters {name}` (a person adds a shutter in the bridge: gets the
  next free address, **not announced until a restart**), `DELETE /api/sim/bridge/shutters/{address}`
  (deletes it; the retained announcement stays), `POST /api/sim/bridge/restart` (offline,
  online, live announcements).

## 9. Snapshot on roster change

Adding or removing changes the shape every client renders. **Decision**: the server sends a
fresh `snapshot` frame to every client after a roster change. Clients already replace
everything on a snapshot (feature 001), so no new client logic is needed for the overview;
the management screen listens to a separate `roster` frame for new/set-aside/forgotten.
