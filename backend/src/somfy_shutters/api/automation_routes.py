"""Automations over REST (specs/003-shutter-automations/contracts/rest.md).

Times go out as local wall-clock with offset, so a client can print them as they
are; they come in as `HH:MM`. Every error uses the shared three-field shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..automation.engine import AutomationEngine
from ..automation.models import Firing, Rule, RuleDraft, targets_wire

router = APIRouter(prefix="/api")


def _engine(request: Request) -> AutomationEngine:
    return request.app.state.automation


def error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse({"error": code, "message": message, "detail": detail}, status_code=status)


def _local(engine: AutomationEngine, at: datetime | None) -> str | None:
    return at.astimezone(engine.tz).isoformat() if at else None


def last_json(engine: AutomationEngine, firing: Firing | None) -> dict[str, Any] | None:
    if firing is None:
        return None
    return {
        "planned_at": _local(engine, firing.planned_at),
        "status": firing.status.value,
        "commanded": firing.commanded,
        "total": len(firing.outcomes),
    }


def rule_json(engine: AutomationEngine, rule: Rule, now: datetime | None = None) -> dict[str, Any]:
    nxt = engine.next_for(rule, now)
    return {
        "id": rule.id,
        "name": rule.name,
        "enabled": rule.enabled,
        "days": rule.days,
        "trigger": rule.trigger.model_dump(),
        "targets": targets_wire(rule.targets),
        "action": rule.action.model_dump(),
        "skip_next": rule.skip_planned_at is not None and rule.skip_planned_at == nxt.at,
        "next": {"at": _local(engine, nxt.at), "reason": nxt.reason},
        "last": last_json(engine, engine.store.last_firing(rule.id)),
        "created_at": rule.created_at.isoformat(),
    }


def _location_json(engine: AutomationEngine, now: datetime) -> dict[str, Any] | None:
    where = engine.location()
    if where is None:
        return None
    sun = engine.sun()
    today = now.astimezone(engine.tz).date()
    times = {}
    for event in ("sunrise", "sunset"):
        at = sun(today, event) if sun else None
        times[event] = at.astimezone(engine.tz).strftime("%H:%M") if at else None
    return {**where, **times}


def _pause_json(engine: AutomationEngine) -> dict[str, Any]:
    state = engine.state_json()
    return {"paused": state["paused"], "until": state["until"]}


def parse_draft(engine: AutomationEngine, raw: Any) -> RuleDraft | JSONResponse:
    """A rule body, validated, or the response that says why not."""
    try:
        draft = RuleDraft.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        return error(
            422,
            "invalid_rule",
            "Die Regel ist so nicht gültig.",
            {"field": where, "problem": first["msg"]},
        )
    if draft.targets != "all":
        unknown = [sid for sid in draft.targets.shutters if sid not in engine.settings.shutters]
        if unknown:
            return error(
                422,
                "unknown_shutter",
                "Diesen Rolladen gibt es nicht.",
                {"shutters": unknown},
            )
        known = {g.id for g in engine.current_groups()}
        missing = [gid for gid in draft.targets.groups if gid not in known]
        if missing:
            return error(422, "unknown_group", "Diese Gruppe gibt es nicht.", {"groups": missing})
    if draft.is_sun and engine.location() is None:
        return error(
            409,
            "no_location",
            "Für Regeln nach dem Sonnenstand braucht die App den Standort des Hauses.",
        )
    return draft


async def changed(request: Request) -> None:
    engine = _engine(request)
    engine.reschedule()
    await request.app.state.bus.publish({"type": "rules_changed"})


def _ordered(engine: AutomationEngine, rules: list[Rule], now: datetime) -> list[Rule]:
    """FR-011 order: by next firing, then creation. Rules that never fire go last."""
    far = datetime.max.replace(tzinfo=now.tzinfo)

    def key(rule: Rule) -> tuple[datetime, datetime, str]:
        at = engine.next_for(rule, now).at
        return (at or far, rule.created_at, rule.id)

    return sorted(rules, key=key)


@router.get("/automations")
async def list_automations(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    now = engine.clock()
    return {
        "rules": [rule_json(engine, r, now) for r in _ordered(engine, engine.store.rules(), now)],
        "pause": _pause_json(engine),
        "clock": {"reliable": engine.verdict.reliable, "reason": engine.verdict.reason},
        "location": _location_json(engine, now),
    }


@router.post("/automations", status_code=201)
async def create_rule(request: Request) -> Any:
    engine = _engine(request)
    draft = parse_draft(engine, await request.json())
    if isinstance(draft, JSONResponse):
        return draft
    conflicts = conflicts_json(engine, draft, None)
    rule = engine.store.create(draft)
    for c in conflicts:
        if c["winner"] == "this":
            c["winner"] = rule.id
    await changed(request)
    return JSONResponse({**rule_json(engine, rule), "conflicts": conflicts}, status_code=201)


# Registered before /automations/{rule_id}: FastAPI matches in order, and "pause"
# would otherwise be taken for a rule id.
@router.put("/automations/pause")
async def pause(request: Request) -> Any:
    """Pause every rule until a time, or until resumed (FR-024)."""
    from ..automation.engine import PAUSE_KEY

    engine = _engine(request)
    raw = await request.json()
    until_text = raw.get("until") if isinstance(raw, dict) else None
    until = None
    if until_text is not None:
        try:
            until = datetime.fromisoformat(until_text)
        except (TypeError, ValueError):
            return error(422, "invalid_pause", "Unbekanntes Datum.", {"until": until_text})
        if until.tzinfo is None:
            until = until.replace(tzinfo=engine.tz)
        if until <= engine.clock():
            return error(422, "invalid_pause", "Dieser Zeitpunkt liegt in der Vergangenheit.")
    engine.store.set_setting(PAUSE_KEY, {"until": until.isoformat() if until else None})
    await engine.announce_state()
    await changed(request)
    return _pause_json(engine)


@router.delete("/automations/pause")
async def resume(request: Request) -> Any:
    from ..automation.engine import PAUSE_KEY

    engine = _engine(request)
    engine.store.set_setting(PAUSE_KEY, None)
    await engine.announce_state()
    await changed(request)
    return _pause_json(engine)


@router.put("/automations/{rule_id}")
async def replace_rule(request: Request, rule_id: str) -> Any:
    engine = _engine(request)
    if engine.store.rule(rule_id) is None:
        return error(404, "unknown_rule", "Diese Regel gibt es nicht.")
    draft = parse_draft(engine, await request.json())
    if isinstance(draft, JSONResponse):
        return draft
    conflicts = conflicts_json(engine, draft, rule_id)
    for c in conflicts:
        if c["winner"] == "this":
            c["winner"] = rule_id
    rule = engine.store.replace(rule_id, draft)
    assert rule is not None
    # A skip only makes sense for an instant the rule still fires at.
    if rule.skip_planned_at is not None and engine.next_for(rule).at != rule.skip_planned_at:
        rule = engine.store.set_skip(rule_id, None) or rule
    await changed(request)
    return {**rule_json(engine, rule), "conflicts": conflicts}


@router.patch("/automations/{rule_id}")
async def patch_rule(request: Request, rule_id: str) -> Any:
    engine = _engine(request)
    rule = engine.store.rule(rule_id)
    if rule is None:
        return error(404, "unknown_rule", "Diese Regel gibt es nicht.")
    patch = await request.json()
    if not isinstance(patch, dict) or set(patch) - {"enabled", "skip_next"} or not patch:
        return error(422, "invalid_patch", "Nur „enabled“ oder „skip_next“ lassen sich so ändern.")
    if "enabled" in patch:
        rule = engine.store.set_enabled(rule_id, bool(patch["enabled"])) or rule
    if "skip_next" in patch:
        if patch["skip_next"]:
            nxt = engine.next_for(rule).at
            if nxt is None:
                return error(409, "nothing_to_skip", "Diese Regel hat keine nächste Ausführung.")
            rule = engine.store.set_skip(rule_id, nxt) or rule
        else:
            rule = engine.store.set_skip(rule_id, None) or rule
    await changed(request)
    return rule_json(engine, rule)


@router.get("/automations/{rule_id}/firings")
async def rule_firings(request: Request, rule_id: str, limit: int = 50) -> Any:
    engine = _engine(request)
    if engine.store.rule(rule_id) is None:
        return error(404, "unknown_rule", "Diese Regel gibt es nicht.")
    return {
        "firings": [
            {
                "planned_at": _local(engine, f.planned_at),
                "fired_at": _local(engine, f.fired_at),
                "status": f.status.value,
                "outcomes": [o.model_dump() for o in f.outcomes],
            }
            for f in engine.store.firings(rule_id, limit=max(1, min(limit, 500)))
        ]
    }


@router.delete("/automations/{rule_id}")
async def delete_rule(request: Request, rule_id: str) -> Any:
    engine = _engine(request)
    if not engine.store.delete(rule_id):
        return error(404, "unknown_rule", "Diese Regel gibt es nicht.")
    await changed(request)
    return Response(status_code=204)


@router.post("/automations/preview")
async def preview(request: Request) -> Any:
    """The form's live line: next firing, what the trigger means today, conflicts.

    Saves nothing. A sun trigger without a location still previews — as "no
    location" — so the form can explain rather than fail.
    """
    engine = _engine(request)
    raw = await request.json()
    editing = raw.pop("id", None) if isinstance(raw, dict) else None
    try:
        draft = RuleDraft.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        return error(
            422,
            "invalid_rule",
            "Die Regel ist so nicht gültig.",
            {"field": ".".join(str(p) for p in first["loc"]), "problem": first["msg"]},
        )
    from ..automation.planner import next_firing, today_at

    now = engine.clock()
    sun = engine.sun()
    nxt = next_firing(draft, now, engine.tz, sun, has_targets=bool(engine.targets(draft).reached))
    today = today_at(draft, now, engine.tz, sun) if (not draft.is_sun or sun) else None
    return {
        "next": {"at": _local(engine, nxt.at), "reason": nxt.reason},
        "today": today.astimezone(engine.tz).strftime("%H:%M") if today else None,
        "conflicts": conflicts_json(engine, draft, editing),
    }


def conflicts_json(
    engine: AutomationEngine, draft: RuleDraft, editing: str | None
) -> list[dict[str, Any]]:
    """Same-minute clashes on a shared shutter, with the rule that wins (FR-022)."""
    from ..automation.conflicts import find_conflicts

    existing = engine.store.rule(editing) if editing else None
    found = find_conflicts(
        draft,
        engine.store.rules(),
        list(engine.settings.shutters),
        engine.clock(),
        engine.tz,
        engine.sun(),
        editing=editing,
        created_at=existing.created_at if existing else None,
        groups=engine.current_groups(),
    )
    return [
        {
            "rule_id": c.rule_id,
            "rule_name": c.rule_name,
            "shutter_id": c.shutter_id,
            "via": c.via,
            "first_at": _local(engine, c.first_at),
            "winner": c.winner,
        }
        for c in found
    ]


@router.get("/location")
async def get_location(request: Request) -> Any:
    engine = _engine(request)
    return _location_json(engine, engine.clock())


@router.put("/location")
async def put_location(request: Request) -> Any:
    from ..config import LocationConfig

    engine = _engine(request)
    try:
        where = LocationConfig.model_validate(await request.json())
    except ValidationError as exc:
        first = exc.errors()[0]
        return error(
            422,
            "invalid_location",
            "Breite muss zwischen -90 und 90 liegen, Länge zwischen -180 und 180.",
            {"field": ".".join(str(p) for p in first["loc"]), "problem": first["msg"]},
        )
    engine.store.set_setting("location", where.model_dump())
    await changed(request)  # sun rules move, and so does the timer
    return _location_json(engine, engine.clock())
