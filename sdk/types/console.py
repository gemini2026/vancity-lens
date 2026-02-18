from __future__ import annotations

from typing import Any, TypedDict

from .jobs import JobListItem


class ConsoleMeResponse(TypedDict, total=False):
    provisioned: bool
    org_id: str | None
    org_name: str | None
    project_id: str | None
    project_name: str | None
    role: str | None
    is_console_admin: bool
    auth_subject: str | None
    user_id: str | None
    email: str | None
    name: str | None


class ConsoleBootstrapResponse(ConsoleMeResponse, total=False):
    created: bool


class ConsoleSummaryResponse(TypedDict):
    corpora_total: int
    documents_total: int
    documents_failed: int
    recent_jobs: list[JobListItem]


class ConsoleProjectItem(TypedDict, total=False):
    id: str
    name: str
    org_id: str
    role: str
    graph_rag_policy: dict[str, Any] | None


class ConsoleProjectListResponse(TypedDict):
    projects: list[ConsoleProjectItem]


class ConsoleOrgResponse(TypedDict, total=False):
    id: str
    name: str
    contact_email: str | None


class TeamMember(TypedDict, total=False):
    membership_id: str
    user_id: str
    email: str | None
    name: str | None
    role: str
    created_at: str | None
    is_current_user: bool


class TeamListResponse(TypedDict):
    members: list[TeamMember]


class InviteListItem(TypedDict, total=False):
    id: str
    email: str
    role: str
    created_at: str | None
    expires_at: str | None
    accepted_at: str | None


class InviteListResponse(TypedDict):
    invites: list[InviteListItem]


class InviteCreateResponse(TypedDict, total=False):
    id: str
    email: str
    role: str
    token: str
    expires_at: str | None


class InviteAcceptResponse(TypedDict, total=False):
    org_id: str
    org_name: str | None
    project_id: str
    project_name: str | None
    role: str


class MemberUpdateResponse(TypedDict):
    updated: bool
    role: str


class MemberRemoveResponse(TypedDict):
    removed: bool
