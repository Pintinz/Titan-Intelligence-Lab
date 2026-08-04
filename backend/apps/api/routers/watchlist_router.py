"""Watchlist API — users follow matches, teams, competitions, and predictions.

Deliberately returns raw entries only (id, entity_type, entity_ref, created_at), not hydrated
match/team/competition/prediction summaries: the sports and predictions routers already expose
get-by-id endpoints for every one of those entity types (``GET /api/v1/sports/fixtures/{id}``,
``/teams/{id}``, ``/competitions/{id}``, ``GET /api/v1/predictions/{id}``), and the frontend
already has query hooks for each. Re-serializing those entities here would duplicate that logic
rather than reuse it — the frontend hydrates each entry with the existing per-type fetch.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_watchlist_service, get_session
from modules.identity.domain.entities import User
from modules.watchlist.application.watchlist_service import NotWatchlistEntryOwnerError, WatchlistEntryNotFoundError
from modules.watchlist.domain.entities import WatchlistEntry
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_entity_type(value: str) -> WatchlistEntityType:
    try:
        return WatchlistEntityType(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized entity_type '{value}'") from None


def _parse_entry_id(value: str) -> WatchlistEntryId:
    try:
        return WatchlistEntryId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid watchlist entry id: {value}") from None


def _serialize(entry: WatchlistEntry) -> dict:
    return {
        "id": str(entry.id),
        "entity_type": entry.entity_type.value,
        "entity_ref": entry.entity_ref,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


class FollowRequest(BaseModel):
    entity_type: str
    entity_ref: str


@router.get("")
async def list_watchlist(
    entity_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    parsed_type = _parse_entity_type(entity_type) if entity_type is not None else None
    service = build_watchlist_service(session)
    entries = await service.list_for_user(user.id, parsed_type)
    return envelope([_serialize(e) for e in entries])


@router.post("")
async def follow(
    body: FollowRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    entity_type = _parse_entity_type(body.entity_type)
    service = build_watchlist_service(session)
    entry = await service.follow(user.id, entity_type, body.entity_ref, _now())
    return envelope(_serialize(entry))


@router.delete("/{entry_id}")
async def unfollow(
    entry_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    parsed_id = _parse_entry_id(entry_id)
    service = build_watchlist_service(session)
    try:
        await service.unfollow(user.id, parsed_id)
    except WatchlistEntryNotFoundError:
        raise HTTPException(status_code=404, detail="watchlist entry not found") from None
    except NotWatchlistEntryOwnerError:
        raise HTTPException(status_code=404, detail="watchlist entry not found") from None
    return envelope({"unfollowed": True})
