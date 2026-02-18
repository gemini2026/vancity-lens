# Changelog

All notable changes to the Knowledge2 Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-13

### Added

- **Error hierarchy**: 10 exception types (`AuthenticationError`, `RateLimitError`,
  `ServerError`, `APIConnectionError`, `APITimeoutError`, etc.) with `retryable`
  property. All subclass `Knowledge2Error` for backward compatibility.
- **Automatic retry**: Exponential backoff with jitter for 5xx, 429, connection
  errors, and timeouts. Configurable via `max_retries` (default: 2). Rate limit
  429 responses honor `Retry-After` header.
- **Pagination iterators**: `iter_*` methods for all paginated `list_*` endpoints
  (e.g., `iter_documents`, `iter_corpora`, `iter_jobs`). Lazy page fetching.
- **Debug logging**: Logger named `knowledge2` with credential redaction.
  `set_debug()` convenience method.
- **Typed config parameters**: Search methods accept TypedDict types
  (`SearchHybridConfig`, `SearchRerankConfig`, etc.) alongside `dict[str, Any]`.
- **Comprehensive docstrings**: Google-style docstrings on all public methods.
- **Standalone package**: `pyproject.toml` for independent `pip install`.
- **SDK versioning**: `__version__` attribute and this changelog.
- **Focused examples**: Quick-start, search, document upload, error handling,
  pagination, and batch operations examples.
- **Comprehensive README**: Installation, authentication, configuration, error
  handling, pagination, and resource overview.

### Changed

- `fetch_whoami()` renamed to `get_whoami()` for consistency. `fetch_whoami()`
  is now a deprecated alias.
- `reconcile_jobs()` and `cancel_tuning_run()` return typed responses instead
  of `dict[str, Any]`.
