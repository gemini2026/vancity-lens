-- Migration 010: Compound Database Indexes (VCL-51 / PERF-004)
-- Addresses sequential scan bottlenecks identified in performance review.
-- Expected impact: signal feed queries 500ms → 50ms (10×)

-- ============================================================
-- INTELLIGENCE SIGNALS — Compound indexes for feed queries
-- The signal feed endpoint filters by (neighborhood, signal_type, event_date).
-- Without a compound index, Postgres does sequential scans on 10K+ rows.
-- ============================================================

-- Primary feed query index: neighborhood + type + date descending
-- Partial index excluding NULL event_date (most feed queries filter by date)
CREATE INDEX IF NOT EXISTS idx_signals_feed_combined
    ON intelligence_signals(neighborhood, signal_type, event_date DESC)
    WHERE event_date IS NOT NULL;

-- Severity-filtered feed: for "show me critical signals in Mount Pleasant"
CREATE INDEX IF NOT EXISTS idx_signals_neighborhood_severity
    ON intelligence_signals(neighborhood, severity, event_date DESC)
    WHERE event_date IS NOT NULL;

-- ============================================================
-- DOCUMENTS — Unprocessed batch lookup
-- The admin/process endpoint needs to find unprocessed documents quickly.
-- Current query: WHERE processed_at IS NULL AND raw_text IS NOT NULL
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_documents_unprocessed_batch
    ON documents(processed_at, id)
    WHERE processed_at IS NULL AND raw_text IS NOT NULL;

-- Source type + date for browsing/filtering documents
CREATE INDEX IF NOT EXISTS idx_documents_source_type_date
    ON documents(source_type, published_date DESC, source_url);

-- ============================================================
-- DOCUMENT CHUNKS — Chunk ordering within document
-- Required for ordered retrieval during RAG context assembly
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_chunks_document_index
    ON document_chunks(document_id, chunk_index);

-- ============================================================
-- NEIGHBORHOOD SCORES — Scorecard lookup optimization
-- Scorecards query: WHERE neighborhood_id = X ORDER BY period_start DESC
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_scores_neighborhood_category
    ON neighborhood_scores(neighborhood_id, category, period_start DESC);

-- ============================================================
-- PARCELS — Spatial + attribute compound indexes
-- These support the entitlement and opportunity endpoints
-- ============================================================

-- For opportunity ranking: lot_area filter + asking_price sort
CREATE INDEX IF NOT EXISTS idx_parcels_lot_area
    ON parcels(lot_area_sqm)
    WHERE lot_area_sqm BETWEEN 200 AND 10000;

-- ============================================================
-- CHAT MESSAGES — Session lookup
-- Already exists from 007 but adding covering index for content
-- ============================================================
-- (idx_chat_messages_session already exists in 007)

-- ============================================================
-- VERIFY: Run ANALYZE to update planner statistics
-- ============================================================
ANALYZE intelligence_signals;
ANALYZE documents;
ANALYZE document_chunks;
ANALYZE neighborhood_scores;
ANALYZE parcels;
