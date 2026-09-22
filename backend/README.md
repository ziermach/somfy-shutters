# Backend

FastAPI service: commands over REST, state over a WebSocket, Pi-Somfy over MQTT.
It also serves the built frontend, so production is one process.

## Run

```bash
cd backend
uv venv --python 3.11 .venv          # or python3.11 -m venv .venv
uv pip install -e ".[dev]"           # or .venv/bin/pip install -e ".[dev]"
cp ../config/shutters.example.toml ../config/shutters.toml

.venv/bin/uvicorn somfy_shutters.main:app --reload --host 0.0.0.0
```

With `bridge.kind = "sim"` in the config this needs no broker and no hardware —
it runs a simulated house with soft-start, non-linear travel and per-direction
speeds the app cannot see. Point `kind` at `"mqtt"` to talk to Pi-Somfy.

Running this on the Pi as a service — broker, systemd unit, backups — is
[`deploy/README.md`](../deploy/README.md).

## Test

```bash
.venv/bin/python -m pytest        # unit, contract and integration
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

`tracker.py` holds the rules worth reading: confidence transitions and the
FR-017 precedence table. It does no I/O, which is why those tests need neither a
broker nor a clock.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `SHUTTERS_CONFIG` | `../config/shutters.toml` | settings and hand-listed shutters |
| `SHUTTERS_DB` | `../config/state.db` | positions, shutters confirmed in the app, groups, rules, history |
| `SHUTTERS_CALIBRATION` | `calibration.toml` beside the database | measured travel times, written by the app |
| `LOG_LEVEL` | `INFO` | |

## Simulator-only endpoints

Registered only when `bridge.kind == "sim"`, used by the quickstart scenarios:

```bash
curl -XPOST localhost:8000/api/sim/bridge/offline
curl -XPOST localhost:8000/api/sim/report -H 'content-type: application/json' \
     -d '{"shutter_id":"wohnzimmer","percent":40}'

# feature 005: a person working in Pi-Somfy's own interface
curl -XPOST localhost:8000/api/sim/bridge/shutters -H 'content-type: application/json' \
     -d '{"name":"Bad"}'                                  # added, not announced yet
curl -XPOST localhost:8000/api/sim/bridge/restart          # announced live now
curl -XDELETE localhost:8000/api/sim/bridge/shutters/0x279625   # deleted; forgotten after the next restart
```
