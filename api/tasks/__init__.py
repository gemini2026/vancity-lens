"""
VanCity Lens — Background Job Queue (VCL-95 / PERF-015)

Celery-based background task processing with Redis broker.
Provides:
- Task definitions for scraping, processing, and email
- Job status tracking with database persistence
- Retry logic with exponential backoff
- Dead letter queue for failed tasks
- Admin API routes for job management
"""
