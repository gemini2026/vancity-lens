from __future__ import annotations

import httpx

from sdk._base import BaseClient, ClientLimits
from sdk.resources import (
    AuditMixin,
    AuthMixin,
    ConsoleMixin,
    CorporaMixin,
    DeploymentsMixin,
    DocumentsMixin,
    IndexesMixin,
    JobsMixin,
    ModelsMixin,
    OnboardingMixin,
    OrgsMixin,
    ProjectsMixin,
    SearchMixin,
    TrainingMixin,
    UsageMixin,
)

DEFAULT_API_HOST = "https://api.knowledge2.ai"


class Knowledge2(
    BaseClient,
    OrgsMixin,
    AuthMixin,
    ProjectsMixin,
    CorporaMixin,
    ModelsMixin,
    DocumentsMixin,
    IndexesMixin,
    SearchMixin,
    TrainingMixin,
    DeploymentsMixin,
    JobsMixin,
    AuditMixin,
    UsageMixin,
    ConsoleMixin,
    OnboardingMixin,
):
    """Knowledge2 API client.

    The SDK is intentionally self-contained so it can be published directly from
    the `sdk/` directory.
    """

    def __init__(
        self,
        *,
        api_host: str = DEFAULT_API_HOST,
        api_key: str | None = None,
        org_id: str | None = None,
        bearer_token: str | None = None,
        admin_token: str | None = None,
        headers: dict[str, str] | None = None,
        user_agent: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        limits: ClientLimits | None = None,
    ) -> None:
        super().__init__(
            api_host,
            api_key,
            bearer_token=bearer_token,
            admin_token=admin_token,
            headers=headers,
            user_agent=user_agent,
            timeout=timeout,
            limits=limits,
        )
        self.org_id = org_id
        if self.org_id is None and api_key is not None:
            self.org_id = self.fetch_whoami()["org_id"]
