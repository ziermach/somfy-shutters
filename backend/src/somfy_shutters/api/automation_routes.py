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
from ..automation.models import Firing, Rule, RuleDraft

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
        "targets": rule.targets,
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
    if isinstance(draft.targets, list):
        unknown = [sid for sid in draft.targets if sid not in engine.settings.shutters]
        if unknown:
            return error(
                422,
                "unknown_shutter",
                "Diesen Rolladen gibt es nicht.",
                {"shutters": unknown},
            )
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
    rule = engine.store.create(draft)
    await changed(request)
    return JSONResponse({**rule_json(engine, rule), "conflicts": []}, status_code=201)


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
    present = [
        sid for sid in engine.settings.shutters if draft.targets == "all" or sid in draft.targets
    ]
    nxt = next_firing(draft, now, engine.tz, sun, has_targets=bool(present))
    today = today_at(draft, now, engine.tz, sun) if (not draft.is_sun or sun) else None
    return {
        "next": {"at": _local(engine, nxt.at), "reason": nxt.reason},
        "today": today.astimezone(engine.tz).strftime("%H:%M") if today else None,
        "conflicts": conflicts_json(engine, draft, editing),
    }


def conflicts_json(engine: AutomationEngine, draft: RuleDraft, editing: str | None) -> list:
    """Filled in with US3 (automation/conflicts.py)."""
    return []


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
