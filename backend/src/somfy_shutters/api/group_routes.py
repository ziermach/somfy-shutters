"""Groups over REST (specs/004-shutter-groups/contracts/rest.md).

Every change publishes the full list as a `groups` event, so each open client
replaces its copy rather than merging one. Errors use the shared three-field shape.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .. import commands
from ..auth.gate import COMMAND, CONFIGURE, WATCH
from ..automation.conflicts import conflicts_from_group_change
from ..groups import Group, GroupDraft, GroupStore, NameTaken, NotAPermutation
from .rest import TARGET_REQUIRED, CommandBody, many_status

router = APIRouter(prefix="/api")

UNKNOWN_GROUP = "Diese Gruppe gibt es nicht."


def _groups(request: Request) -> GroupStore:
    return request.app.state.groups


def error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse({"error": code, "message": message, "detail": detail}, status_code=status)


def listing(store: GroupStore) -> list[dict[str, Any]]:
    return [g.wire() for g in store.groups()]


async def announce(request: Request) -> None:
    await request.app.state.bus.publish({"type": "groups", "groups": listing(_groups(request))})


def parse_draft(request: Request, raw: Any) -> GroupDraft | JSONResponse:
    """A group body, validated against the model and the configuration, or why not."""
    try:
        draft = GroupDraft.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        return error(
            422,
            "invalid_group",
            "Die Gruppe ist so nicht gültig.",
            {"field": ".".join(str(p) for p in first["loc"]), "problem": first["msg"]},
        )
    configured = request.app.state.settings.shutters
    unknown = [sid for sid in draft.members if sid not in configured]
    if unknown:
        return error(
            422, "unknown_shutter", "Diesen Rolladen gibt es nicht.", {"shutters": unknown}
        )
    return draft


def name_taken(exc: NameTaken) -> JSONResponse:
    return error(409, "name_taken", "Diesen Namen gibt es schon.", {"group_id": exc.group_id})


def group_conflicts(request: Request, group_id: str, before: list[Group]) -> list[dict[str, Any]]:
    """Rule conflicts this change created (FR-028). A warning; the group is saved."""
    engine = request.app.state.automation
    now = engine.clock()
    found = conflicts_from_group_change(
        group_id,
        before,
        _groups(request).groups(),
        engine.store.rules(),
        list(request.app.state.settings.shutters),
        now,
        engine.tz,
        engine.sun(),
    )
    return [
        {
            "rule_id": c.rule_id,
            "rule_name": c.rule_name,
            "other_rule_id": c.other_rule_id,
            "other_rule_name": c.other_rule_name,
            "shutter_id": c.shutter_id,
            "via": c.via,
            "first_at": c.first_at.astimezone(engine.tz).isoformat(),
            "winner": c.winner,
        }
        for c in found
    ]


@router.get("/groups", dependencies=WATCH)
async def list_groups(request: Request) -> dict[str, Any]:
    return {"groups": listing(_groups(request))}


@router.post("/groups", dependencies=CONFIGURE, status_code=201)
async def create_group(request: Request) -> Any:
    draft = parse_draft(request, await request.json())
    if isinstance(draft, JSONResponse):
        return draft
    try:
        group = _groups(request).create(draft)
    except NameTaken as exc:
        return name_taken(exc)
    await announce(request)
    # No rule can name a group that did not exist a moment ago: nothing to warn about.
    return JSONResponse({**group.wire(), "conflicts": []}, status_code=201)


# Registered before /groups/{group_id}: FastAPI matches in order, and "order" would
# otherwise be taken for a group id.
@router.put("/groups/order", dependencies=CONFIGURE)
async def reorder_groups(request: Request) -> Any:
    raw = await request.json()
    ids = raw.get("ids") if isinstance(raw, dict) else None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return error(422, "invalid_order", "Die Reihenfolge muss jede Gruppe genau einmal nennen.")
    try:
        _groups(request).reorder(ids)
    except NotAPermutation:
        # Usually a group was created or deleted meanwhile; the client re-fetches.
        return error(422, "invalid_order", "Die Gruppen haben sich inzwischen geändert.")
    await announce(request)
    return {"groups": listing(_groups(request))}


@router.put("/groups/{group_id}", dependencies=CONFIGURE)
async def replace_group(request: Request, group_id: str) -> Any:
    store = _groups(request)
    if store.get(group_id) is None:
        return error(404, "unknown_group", UNKNOWN_GROUP)
    draft = parse_draft(request, await request.json())
    if isinstance(draft, JSONResponse):
        return draft
    before = store.groups()
    try:
        group = store.update(group_id, draft)
    except NameTaken as exc:
        return name_taken(exc)
    if group is None:  # deleted between the check and the write
        return error(404, "unknown_group", UNKNOWN_GROUP)
    await announce(request)
    return {**group.wire(), "conflicts": group_conflicts(request, group_id, before)}


@router.delete("/groups/{group_id}", dependencies=CONFIGURE)
async def delete_group(request: Request, group_id: str) -> Any:
    if not _groups(request).delete(group_id):
        return error(404, "unknown_group", UNKNOWN_GROUP)
    await announce(request)
    # FR-026: rules lose the group as a target. Not atomic with the delete; the
    # engine ignores unknown group ids, so a crash in between is harmless.
    engine = request.app.state.automation
    if engine.store.drop_group(group_id):
        engine.reschedule()
        await request.app.state.bus.publish({"type": "rules_changed"})
    return Response(status_code=204)


@router.post("/groups/{group_id}/command", dependencies=COMMAND)
async def command_group(request: Request, group_id: str, body: CommandBody) -> Any:
    group = _groups(request).get(group_id)
    if group is None:
        return error(404, "unknown_group", UNKNOWN_GROUP)
    if not group.members:
        return error(409, "empty_group", "Diese Gruppe hat keine Rolladen.")
    if body.action == "position" and body.target_percent is None:
        return JSONResponse(TARGET_REQUIRED, status_code=422)
    # Configuration order, the order automations use too (research §4); the
    # member order is how the group is shown, not how it is driven.
    ordered = [sid for sid in request.app.state.settings.shutters if sid in group.members]
    results = await commands.apply_many(
        request.app.state, ordered, body.action, body.target_percent
    )
    return JSONResponse({"results": results}, status_code=many_status(results))
