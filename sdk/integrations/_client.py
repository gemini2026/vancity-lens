from __future__ import annotations

import os

from sdk import Knowledge2

DEFAULT_K2_API_HOST = "https://api.knowledge2.ai"


def resolve_client(
    *,
    client: Knowledge2 | None,
    api_key: str | None,
    api_host: str | None,
) -> Knowledge2:
    """Return a configured Knowledge2 client.

    Preference order:
      1) explicit client
      2) api_key/api_host parameters
      3) environment variables K2_API_KEY/K2_BASE_URL
    """
    if client is not None:
        return client

    resolved_api_key = api_key or os.getenv("K2_API_KEY")
    if not resolved_api_key:
        raise ValueError("K2 API key required: pass api_key/client or set K2_API_KEY")

    # NOTE: typeshed's os.getenv() typing keeps this as Optional[str] even with a default.
    resolved_api_host = api_host or os.getenv("K2_BASE_URL") or DEFAULT_K2_API_HOST
    return Knowledge2(api_key=resolved_api_key, api_host=resolved_api_host)


def resolve_corpus_id(corpus_id: str | None) -> str:
    """Resolve corpus_id from argument or environment."""
    resolved_corpus_id = corpus_id or os.getenv("K2_CORPUS_ID")
    if not resolved_corpus_id:
        raise ValueError("K2 corpus_id required: pass corpus_id or set K2_CORPUS_ID")
    return resolved_corpus_id


def merge_return_config(
    *,
    base: dict[str, object] | None,
    override: dict[str, object] | None,
    include_text: bool = True,
    include_scores: bool = True,
    include_provenance: bool = True,
) -> dict[str, object]:
    """Merge return configs with safe defaults for framework adapters."""
    merged: dict[str, object] = {
        "include_text": include_text,
        "include_scores": include_scores,
        "include_provenance": include_provenance,
    }
    if base:
        merged.update(base)
    if override:
        merged.update(override)
    return merged
