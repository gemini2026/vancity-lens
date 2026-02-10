-- Migration 026: RAG & Hybrid Search Hardening
-- Adds columns for URL health tracking, archive fallbacks, chunk metadata,
-- embedding model versioning, and search configuration.

-- ============================================================
-- RAG-002 + RAG-003: URL Health & Archive Fallbacks on documents
-- ============================================================
ALTER TABLE documents ADD COLUMN IF NOT EXISTS url_status TEXT DEFAULT 'unchecked';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS url_checked_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS archive_url TEXT;

CREATE INDEX IF NOT EXISTS idx_documents_url_status ON documents(url_status);

-- ============================================================
-- RAG-004: Structured metadata on document_chunks
-- ============================================================
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON document_chunks USING gin(metadata);

-- ============================================================
-- RAG-009: Embedding model versioning on document_chunks
-- ============================================================
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_model TEXT DEFAULT 'cohere-v3';

-- ============================================================
-- RAG-007: Search configuration table
-- ============================================================
CREATE TABLE IF NOT EXISTS search_config (
    id SERIAL PRIMARY KEY,
    vector_weight NUMERIC DEFAULT 0.5,
    text_weight NUMERIC DEFAULT 0.5,
    rrf_k INT DEFAULT 60,
    rerank_enabled BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT now(),
    updated_by TEXT DEFAULT 'system'
);

-- Insert default row if table is empty
INSERT INTO search_config (vector_weight, text_weight, rrf_k, rerank_enabled)
SELECT 0.5, 0.5, 60, true
WHERE NOT EXISTS (SELECT 1 FROM search_config LIMIT 1);
