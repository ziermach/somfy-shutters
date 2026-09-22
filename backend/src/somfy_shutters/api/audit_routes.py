"""The record over REST (specs/008-api-auth-audit/contracts/rest.md, "Record").

Reading it needs `manage`: it says which device did what, and that is the owner's
view, not every phone's (research §3).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from ..auth.audit import MAX_PAGE, Entry
from ..auth.gate import MANAGE

router = APIRouter(prefix="/api")


def entry_json(request: Request, entry: Entry, states: dict[str, str]) -> dict[str, Any]:
    tz = request.app.state.settings.general.tz
    actor: dict[str, Any] = {
        "kind": entry.actor.kind,
        "id": entry.actor.id,
        "name": entry.actor.name,
    }
    if entry.actor.kind == "credential":
        # The name is as it was then (FR-017); the state is as it is now.
        actor["state"] = states.get(entry.actor.id or "", "unknown")
    return {
        "id": entry.id,
        "at": entry.at.astimezone(tz).isoformat(),
        "clock_ok": entry.clock_ok,
        "actor": actor,
        "action": entry.action,
        "shutter_id": entry.shutter_id,
        "target": entry.target,
        "outcome": entry.outcome,
        "detail": entry.detail,
    }


@router.get("/audit", dependencies=MANAGE)
async def read_record(
    request: Request,
    shutter: str | None = None,
    actor: str | None = None,
    before: int | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE),
) -> dict[str, Any]:
    entries = request.app.state.audit.query(
        shutter=shutter, actor=actor, before=before, limit=limit
    )
    auth = request.app.state.auth
    now = auth.clock()
    states = {c.id: c.state(now) for c in auth.list()}
    return {
        "entries": [entry_json(request, e, states) for e in entries],
        "next_before": entries[-1].id if len(entries) == limit else None,
    }
