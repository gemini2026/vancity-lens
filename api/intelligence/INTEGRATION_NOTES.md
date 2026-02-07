# Integration Notes: Adding Intelligence Router to FastAPI App

## Overview

The intelligence router (`/sessions/zen-relaxed-lamport/mnt/bill47/api/intelligence/routes.py`) provides all endpoints for the VanCity Lens intelligence system. This document explains how to integrate it into `main.py`.

## Integration Steps

### 1. Add Import to `main.py`

At the top of `main.py` (around line 15, after other imports), add:

```python
from .intelligence.routes import router as intelligence_router
```

### 2. Include Router in App

In the main app setup (around line 46, after `app.include_router(admin_router)`), add:

```python
app.include_router(intelligence_router)
```

## Example Integration

Here's what the relevant sections of `main.py` should look like:

```python
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import db
from .entitlement import ParcelNotFoundError, compute_entitlement
from .models import EntitlementRequest, ParcelEntitlementResponse
from .admin import router as admin_router
from .intelligence.routes import router as intelligence_router  # <-- ADD THIS LINE

# ... rest of lifespan and app setup ...

app.include_router(admin_router)
app.include_router(intelligence_router)  # <-- ADD THIS LINE
```

## Environment Variables

The intelligence router requires two environment variables to be set:

- `ANTHROPIC_API_KEY` — Anthropic API key for Claude (used by chat endpoint)
- `OPENAI_API_KEY` — OpenAI API key for embeddings (used by chat endpoint for semantic search)

Set these before starting the FastAPI app:

```bash
export ANTHROPIC_API_KEY="your-key-here"
export OPENAI_API_KEY="your-key-here"
python -m uvicorn api.main:app --reload
```

## Database Pool Access

The router accesses the database pool via `request.app.state.pool`, which is created during the lifespan and is available to all routes once the app is running. The existing `lifespan` context manager in `main.py` handles database connection setup, so no additional changes are needed there.

## Available Endpoints

Once integrated, the following endpoints will be available under `/api/v1/intel/`:

### Chat
- `POST /api/v1/intel/chat` — RAG-powered chat with source documents

### Signals
- `GET /api/v1/intel/signals` — Paginated signal feed with filters
- `GET /api/v1/intel/signals/{signal_id}` — Get single signal details
- `GET /api/v1/intel/signals/parcel/{pid}` — Get signals near a parcel

### Statistics
- `GET /api/v1/intel/stats` — Dashboard statistics
- `GET /api/v1/intel/neighborhoods` — List all neighborhoods

### Admin
- `POST /api/v1/intel/admin/scrape` — Trigger document scraping (background)
- `POST /api/v1/intel/admin/process` — Trigger extraction + embedding (background)
- `GET /api/v1/intel/admin/status` — Check ingestion pipeline status

## CORS Configuration

The existing CORS middleware in `main.py` allows requests from:
- http://localhost:3000
- http://localhost:3001
- http://localhost:3002
- http://localhost:3003

All intelligence endpoints will respect these CORS settings.

## Error Handling

The router includes proper error handling:
- Missing API keys return 500 with descriptive error message
- Invalid query parameters return 400
- Database errors return 500
- Not found errors return 404

## Logging

The router uses Python's standard `logging` module. Set log level in your app startup:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

All router operations are logged to aid in debugging and monitoring.
