"""Organization REST endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


from .user_auth import get_current_user_from_request
from . import organizations

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str


class MemberInvite(BaseModel):
    email: str
    role: str = "member"


@router.post("")
async def create_organization(body: OrgCreate, request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    org = await organizations.create_org(body.name, user["id"])
    org["created_at"] = org["created_at"].isoformat()
    return org


@router.get("")
async def list_my_organizations(request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    return await organizations.list_user_orgs(user["id"])


@router.get("/{org_id}")
async def get_organization(org_id: int, request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    org = await organizations.get_org(org_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    org["created_at"] = org["created_at"].isoformat()
    return org


@router.get("/{org_id}/members")
async def list_org_members(org_id: int, request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    members = await organizations.list_members(org_id)
    for m in members:
        m["joined_at"] = m["joined_at"].isoformat()
    return members


@router.post("/{org_id}/members")
async def invite_member(org_id: int, body: MemberInvite, request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    member = await organizations.add_member(org_id, body.email, body.role, user["id"])
    if not member:
        raise HTTPException(
            400, "Could not add member (user not found or seat limit reached)"
        )
    member["joined_at"] = member["joined_at"].isoformat()
    return member


@router.delete("/{org_id}/members/{user_id}")
async def remove_org_member(org_id: int, user_id: int, request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    ok = await organizations.remove_member(org_id, user_id)
    if not ok:
        raise HTTPException(400, "Cannot remove member (owner cannot be removed)")
    return {"ok": True}
