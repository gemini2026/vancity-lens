# AGENTS.md

## Scope
- This file documents the Python SDK in isolation; assume no context from other folders.
- For system-level architecture and milestones, read `../implementation_plan.md`.

## What this library is
- Minimal Python client for the API service.
- Used by external apps and examples to call the REST API.

## Entry point
- Client: `sdk/client.py`.

## Key files
- `sdk/_base.py`: HTTP plumbing and shared request logic.
- `sdk/types/`: data model types for responses.
- `sdk/errors.py`: exception types.
- `sdk/examples/`: runnable usage samples.

## External dependencies (treat as contracts)
- Expects API base URL and `X-API-Key` auth.
- API request/response shapes must match server endpoints.

## When changing this library
- Keep backwards compatibility for public client methods.
- If the API contract changes, update `sdk/types/` and regenerate examples.
