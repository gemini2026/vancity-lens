"""Error handling: catch specific errors, use retryable, configure max_retries."""

from __future__ import annotations

import os

from sdk import (
    AuthenticationError,
    Knowledge2,
    Knowledge2Error,
    NotFoundError,
    RateLimitError,
    ServerError,
)

try:
    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise SystemExit("K2_API_KEY is required")

    # Client with custom max_retries (0 = disable auto-retry)
    client = Knowledge2(
        api_key=api_key,
        max_retries=3,
    )

    corpus_id = os.environ.get("K2_CORPUS_ID", "corpus-123")

    try:
        client.get_corpus("nonexistent-corpus-id")
    except AuthenticationError as e:
        print("Invalid API key:", e.message)
    except NotFoundError as e:
        print("Resource not found:", e.message)
    except RateLimitError as e:
        print("Rate limited. Retry after:", e.retry_after)
        if e.retryable:
            print("This error is retryable.")
    except ServerError as e:
        print("Server error:", e.message)
        if e.retryable:
            print("Consider retrying the request.")

    # Example: check retryable before custom retry logic
    try:
        client.search(corpus_id, "test query")
    except Knowledge2Error as e:
        if e.retryable:
            print("Transient error - safe to retry:", e.message)
        else:
            print("Non-retryable error:", e.message)

except Knowledge2Error as e:
    print(f"API error: {e}")
    raise
