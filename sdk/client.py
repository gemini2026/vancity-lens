"""Knowledge2 API client.

Usage::

    from sdk import Knowledge2

    client = Knowledge2(api_key="k2_...")
    results = client.search(corpus_id, "my query")
"""

from __future__ import annotations

import httpx

from sdk._base import BaseClient, ClientLimits
from sdk._logging import set_debug as _set_debug
from sdk.resources import (
    A2AMixin,
    AuditMixin,
    AuthMixin,
    ConsoleMixin,
    CorporaMixin,
    DeploymentsMixin,
    DocumentsMixin,
    IndexesMixin,
    JobsMixin,
    MetadataMixin,
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
    MetadataMixin,
    TrainingMixin,
    DeploymentsMixin,
    JobsMixin,
    AuditMixin,
    UsageMixin,
    ConsoleMixin,
    OnboardingMixin,
    A2AMixin,
):
    """Knowledge2 API client.

    The SDK is intentionally self-contained so it can be published directly from
    the ``sdk/`` directory.

    Args:
        api_host: Base URL of the Knowledge2 API.
        api_key: API key for authentication (``X-API-Key`` header).
        org_id: Organisation ID.  Auto-detected from the API key when
            omitted.
        bearer_token: Bearer token for console / Auth0 authentication.
        admin_token: Admin token (``X-Admin-Token`` header).
        headers: Extra default headers sent with every request.
        user_agent: Custom ``User-Agent`` header value.
        timeout: Request timeout in seconds (or an ``httpx.Timeout``).
        limits: Connection pool limits.
        max_retries: Maximum number of automatic retries for transient
            errors (5xx, 429, connection failures, timeouts).  Set to
            ``0`` to disable.
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
        max_retries: int = 2,
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
            max_retries=max_retries,
        )
        self.org_id = org_id
        if self.org_id is None and api_key is not None:
            self.org_id = self.get_whoami()["org_id"]

    @staticmethod
    def set_debug(enabled: bool = True) -> None:
        """Enable or disable SDK debug logging.

        When enabled, request method, URL, response status, and retry
        attempts are logged to stderr.  Authentication headers are
        redacted.

        Args:
            enabled: ``True`` to turn on debug logging, ``False`` to
                turn it off.
        """
        _set_debug(enabled)
