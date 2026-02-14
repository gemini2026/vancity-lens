from __future__ import annotations

from typing import Optional, TypedDict


class OrgResponse(TypedDict, total=False):
    id: str
    name: str
    contact_email: str | None
