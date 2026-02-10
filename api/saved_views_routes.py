"""Saved views REST endpoints."""

import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .db import db
from .user_auth import get_current_user_from_request
from . import saved_views

router = APIRouter(prefix="/api/v1/views", tags=["views"])


class SavedViewCreate(BaseModel):
    name: str
    filters: dict


@router.post("")
async def create_saved_view(body: SavedViewCreate, request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    result = await saved_views.create_view(user["id"], body.name, body.filters)
    if isinstance(result.get("filters"), str):
        result["filters"] = json.loads(result["filters"])
    result["created_at"] = result["created_at"].isoformat()
    return result


@router.get("")
async def list_saved_views(request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    views = await saved_views.list_views(user["id"])
    for v in views:
        if isinstance(v.get("filters"), str):
            v["filters"] = json.loads(v["filters"])
        v["created_at"] = v["created_at"].isoformat()
    return views


@router.delete("/{view_id}")
async def delete_saved_view(view_id: int, request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    ok = await saved_views.delete_view(user["id"], view_id)
    if not ok:
        raise HTTPException(404, "View not found")
    return {"ok": True}
