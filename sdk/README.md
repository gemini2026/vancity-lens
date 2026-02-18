# Knowledge2 Python SDK

[![PyPI version](https://img.shields.io/pypi/v/knowledge2.svg)](https://pypi.org/project/knowledge2/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Official Python client for the Knowledge2 retrieval platform. Build, search, and tune hybrid retrieval corpora with a simple API.

## Installation

```bash
pip install knowledge2
```

From source:

```bash
pip install -e /path/to/sdk
```

Framework extras:

```bash
pip install -e "/path/to/sdk[langchain]"
pip install -e "/path/to/sdk[llamaindex]"
pip install -e "/path/to/sdk[integrations]"  # both
```

## Quick Start

```python
from sdk import Knowledge2

client = Knowledge2(api_key="k2_...")

# Create project and corpus
project = client.create_project("My Project")
corpus = client.create_corpus(project["id"], "My Corpus")

# Upload a document
client.upload_document(
    corpus["id"],
    raw_text="Knowledge2 is a retrieval platform for building hybrid search systems.",
)

# Build indexes and search
client.build_indexes(corpus["id"])
results = client.search(corpus["id"], "retrieval platform", top_k=5)

for chunk in results["results"]:
    print(chunk["score"], chunk.get("text", "")[:80])
```

## Framework integrations

### LangChain

```python
from sdk.integrations.langchain import K2LangChainRetriever

retriever = K2LangChainRetriever(
    api_key="YOUR_API_KEY",
    api_host="https://api.knowledge2.ai",
    corpus_id="YOUR_CORPUS_ID",
    top_k=5,
    filters={"topic": "search"},
    hybrid={"enabled": True, "fusion_mode": "rrf", "dense_weight": 0.7, "sparse_weight": 0.3},
)

docs = retriever.invoke("How does hybrid retrieval work?")
```

### LlamaIndex

```python
from sdk.integrations.llamaindex import K2LlamaIndexRetriever

retriever = K2LlamaIndexRetriever(
    api_key="YOUR_API_KEY",
    api_host="https://api.knowledge2.ai",
    corpus_id="YOUR_CORPUS_ID",
    top_k=5,
)

nodes = retriever.retrieve("How does hybrid retrieval work?")
```

## Authentication

Use one of the following credentials. API key is the primary method for programmatic access.

| Method | Header | Typical use |
|--------|--------|-------------|
| **API key** | `X-API-Key` | Primary — programmatic access from apps and scripts |
| **Bearer token** | `Authorization: Bearer <token>` | Console / Auth0 session |
| **Admin token** | `X-Admin-Token` | Internal admin operations |

```python
# API key (recommended)
client = Knowledge2(api_key="k2_...")

# From environment
import os
client = Knowledge2(api_key=os.environ["K2_API_KEY"])

# Bearer token (console)
client = Knowledge2(bearer_token=os.environ["K2_BEARER_TOKEN"])

# Admin operations
client = Knowledge2(admin_token=os.environ["K2_ADMIN_TOKEN"])
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_host` | `https://api.knowledge2.ai` | Base URL of the API |
| `api_key` | `None` | API key for `X-API-Key` auth |
| `org_id` | Auto-detected from API key | Organisation ID |
| `bearer_token` | `None` | Bearer token for console auth |
| `admin_token` | `None` | Admin token for `X-Admin-Token` |
| `timeout` | `None` (httpx default) | Request timeout in seconds or `httpx.Timeout` |
| `max_retries` | `2` | Max retries for transient errors (0 to disable) |
| `limits` | `None` | `ClientLimits` for connection pool tuning |

```python
from sdk import Knowledge2, ClientLimits

# Custom host and timeout
client = Knowledge2(
    api_host="https://api.example.com",
    api_key="k2_...",
    timeout=30.0,
)

# Connection pool limits
limits = ClientLimits(
    max_connections=50,
    max_keepalive_connections=20,
    keepalive_expiry=60.0,
)
client = Knowledge2(api_key="k2_...", limits=limits)

# Disable retries
client = Knowledge2(api_key="k2_...", max_retries=0)
```

## Error Handling

All SDK exceptions inherit from `Knowledge2Error`. Use `except Knowledge2Error` as a catch-all.

```
Knowledge2Error (base)
├── APIError (HTTP 4xx/5xx)
│   ├── AuthenticationError (401)
│   ├── PermissionDeniedError (403)
│   ├── NotFoundError (404)
│   ├── ConflictError (409)
│   ├── ValidationError (422)
│   ├── RateLimitError (429)
│   └── ServerError (500, 502, 503, 504)
├── APIConnectionError (network failures)
└── APITimeoutError (request timeout)
```

```python
from sdk import Knowledge2
from sdk.errors import (
    Knowledge2Error,
    NotFoundError,
    ValidationError,
    RateLimitError,
)

client = Knowledge2(api_key="k2_...")

try:
    corpus = client.get_corpus("nonexistent")
except NotFoundError as e:
    print(f"Corpus not found: {e.message}")
except ValidationError as e:
    print(f"Validation failed: {e.details}")
except RateLimitError as e:
    if e.retryable:
        print(f"Rate limited; retry after {e.retry_after}s")
except Knowledge2Error as e:
    print(f"API error: {e.message}")
```

**`retryable` property**: Indicates whether the operation can be retried. `True` for `RateLimitError`, `ServerError`, `APIConnectionError`, and `APITimeoutError`; `False` for auth, validation, and not-found errors.

## Automatic Retries

The SDK retries transient failures automatically:

- **Retried**: 5xx, 429, connection errors, timeouts
- **Not retried**: 4xx (except 429)

Configure via `max_retries` (default `2`). Backoff is exponential with jitter; for `RateLimitError`, the `Retry-After` header is respected when present.

```python
# Default: 2 retries
client = Knowledge2(api_key="k2_...")

# Aggressive retries
client = Knowledge2(api_key="k2_...", max_retries=5)

# No retries
client = Knowledge2(api_key="k2_...", max_retries=0)
```

## Pagination

**Iterator methods** (`iter_*`) yield items lazily across pages:

```python
for corpus in client.iter_corpora(limit=50):
    print(corpus["name"])

for doc in client.iter_documents(corpus_id, limit=100):
    process(doc)
```

**Manual pagination** with `list_*`:

```python
page = client.list_corpora(limit=50, offset=0)
corpora = page["corpora"]
total = page.get("total", len(corpora))

while len(corpora) < total:
    page = client.list_corpora(limit=50, offset=len(corpora))
    corpora.extend(page["corpora"])
```

## Resource Overview

| Resource | Methods |
|----------|---------|
| **Organisations** | `create_org` |
| **Projects** | `create_project`, `list_projects`, `iter_projects` |
| **Corpora** | `create_corpus`, `list_corpora`, `iter_corpora`, `get_corpus`, `get_corpus_status`, `update_corpus`, `delete_corpus`, `list_corpus_models`, `iter_corpus_models` |
| **Documents** | `upload_document`, `upload_documents_batch`, `upload_files_batch`, `ingest_urls`, `ingest_manifest`, `list_documents`, `iter_documents`, `get_document`, `delete_document`, `list_chunks`, `iter_chunks` |
| **Indexes** | `build_indexes` |
| **Search** | `search`, `search_batch`, `search_generate`, `embeddings`, `create_feedback` |
| **Training** | `build_training_data`, `list_training_data`, `iter_training_data`, `list_tuning_runs`, `iter_tuning_runs`, `create_tuning_run`, `build_and_start_tuning_run`, `get_tuning_run`, `get_tuning_run_logs`, `get_eval_run`, `promote_tuning_run` |
| **Deployments** | `create_deployment`, `list_deployments`, `iter_deployments` |
| **Jobs** | `get_job`, `list_jobs`, `iter_jobs` |
| **Models** | `list_models`, `iter_models`, `delete_model` |
| **Auth** | `create_api_key`, `list_api_keys`, `get_whoami` |
| **Audit** | `list_audit_logs`, `iter_audit_logs` |
| **Usage** | `usage_summary`, `usage_by_corpus`, `usage_by_key` |
| **Console** | `console_me`, `console_bootstrap`, `console_summary`, `console_projects`, `console_get_project`, `console_update_project`, `console_get_org`, `console_update_org`, `console_list_team`, `console_list_invites`, `console_create_invite`, `console_accept_invite`, `console_update_member_role`, `console_remove_member`, `console_list_api_keys`, `console_create_api_key`, `console_revoke_api_key` |
| **Onboarding** | `get_onboarding_status`, `get_analysis`, `upload_gold_labels`, `upload_gold_labels_file`, `list_gold_labels`, `iter_gold_labels`, `list_synthetic_batches`, `get_synthetic_batch`, `list_evaluations`, `get_evaluation`, `get_evaluation_report`, `get_summarization_status`, `get_document_summary` |

## Debug Logging

```python
from sdk import Knowledge2

Knowledge2.set_debug(True)  # Log requests, responses, retries to stderr
client = Knowledge2(api_key="k2_...")
# ... use client ...
```

Alternative: configure the `knowledge2` logger directly:

```python
import logging
logging.getLogger("knowledge2").setLevel(logging.DEBUG)
logging.getLogger("knowledge2").addHandler(logging.StreamHandler())
```

Auth headers are redacted in logs.

## Examples

Runnable examples are in the `examples/` directory:

```bash
# End-to-end lifecycle (ingest, index, tune, search)
python -m sdk.examples.e2e_lifecycle
```

## Version

```python
from sdk import __version__
print(__version__)  # e.g. "0.1.0"
```

## Links

- **Website**: https://knowledge2.ai
- **Documentation**: https://knowledge2.ai/docs
- **Support**: contact@knowledge2.ai
