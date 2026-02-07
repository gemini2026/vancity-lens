-- Migration 007: Intelligence Layer
-- Adds document storage, vector search (pgvector), hybrid search (tsvector),
-- and intelligence signals

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- RAW DOCUMENT STORAGE
-- Every scraped document gets stored here with full text
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,          -- 'council_minutes', 'rezoning_report', 'dpb_minutes', 'court_ruling', 'community_plan'
    source_url TEXT UNIQUE NOT NULL,    -- dedupe key: same URL = same document
    title TEXT,
    published_date DATE,
    meeting_date DATE,                  -- for council/DPB: the actual meeting date
    raw_text TEXT,                      -- full extracted text
    text_length INT,                    -- character count for quick filtering
    page_count INT,                     -- for PDFs
    file_format TEXT,                   -- 'html', 'pdf'
    metadata JSONB DEFAULT '{}',        -- flexible: vote counts, agenda item numbers, etc.
    scraped_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ,          -- NULL until AI extraction is done
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_published_date ON documents(published_date DESC);
CREATE INDEX IF NOT EXISTS idx_documents_processed ON documents(processed_at) WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING gin(metadata);

-- ============================================================
-- DOCUMENT CHUNKS
-- Text split into ~800 token chunks for embedding & retrieval
-- Supports hybrid search: dense (pgvector) + sparse (tsvector/BM25)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,           -- order within document
    chunk_text TEXT NOT NULL,
    token_count INT,                    -- approximate token count
    section_header TEXT,                -- nearest section header (if parseable)
    embedding vector(1024),            -- Cohere embed-english-v3.0 dimension
    chunk_tsvector tsvector,           -- Full-text search vector (BM25 sparse)
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);
-- Dense vector index (cosine similarity via pgvector)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- Sparse full-text index (GIN for tsvector BM25)
CREATE INDEX IF NOT EXISTS idx_chunks_tsvector ON document_chunks
    USING gin(chunk_tsvector);

-- Auto-populate tsvector on INSERT or UPDATE
CREATE OR REPLACE FUNCTION update_chunk_tsvector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.chunk_tsvector := to_tsvector('english', NEW.chunk_text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunk_tsvector ON document_chunks;
CREATE TRIGGER trg_chunk_tsvector
    BEFORE INSERT OR UPDATE OF chunk_text ON document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_chunk_tsvector();

-- ============================================================
-- INTELLIGENCE SIGNALS
-- Structured insights extracted by LLM from document chunks
-- Each signal = one actionable piece of information
-- ============================================================
CREATE TABLE IF NOT EXISTS intelligence_signals (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id INT REFERENCES document_chunks(id) ON DELETE SET NULL,

    -- What happened
    signal_type TEXT NOT NULL,           -- rezoning_decision, permit_approval, policy_change,
                                         -- infrastructure_announcement, legal_precedent,
                                         -- community_opposition, density_change, land_sale, other
    summary TEXT NOT NULL,               -- 2-3 sentence plain English summary
    headline TEXT,                        -- short one-liner for feed display

    -- Where
    addresses TEXT[],                    -- specific addresses mentioned
    neighborhood TEXT,                   -- Vancouver neighborhood (geo_local_area)
    parcel_pid TEXT,                     -- linked parcel PID if we can match
    geom GEOMETRY(Point, 4326),         -- geocoded location (nullable)

    -- Zoning / Development specifics
    zoning_from TEXT,                    -- e.g., 'RS-1'
    zoning_to TEXT,                      -- e.g., 'CD-1'
    height_before NUMERIC,              -- storeys before
    height_after NUMERIC,               -- storeys after
    fsr_before NUMERIC,
    fsr_after NUMERIC,
    unit_count INT,                      -- proposed units if mentioned
    project_value_dollars NUMERIC,       -- project value if mentioned

    -- Decision metadata
    decision TEXT,                        -- approved, denied, deferred, referred, pending
    vote_for INT,
    vote_against INT,
    conditions TEXT[],                   -- conditions of approval

    -- Assessment
    sentiment TEXT,                       -- positive_for_development, negative_for_development, neutral
    severity TEXT DEFAULT 'info',         -- info, low, medium, high, critical
    confidence NUMERIC DEFAULT 0.5,      -- 0.0 - 1.0 LLM self-assessed confidence

    -- Timing
    event_date DATE,                     -- when the event occurred

    -- Bookkeeping
    extracted_at TIMESTAMPTZ DEFAULT now(),
    llm_model TEXT,                      -- which model extracted this
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signals_type ON intelligence_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_neighborhood ON intelligence_signals(neighborhood);
CREATE INDEX IF NOT EXISTS idx_signals_event_date ON intelligence_signals(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_severity ON intelligence_signals(severity);
CREATE INDEX IF NOT EXISTS idx_signals_geom ON intelligence_signals USING gist(geom);
CREATE INDEX IF NOT EXISTS idx_signals_addresses ON intelligence_signals USING gin(addresses);
CREATE INDEX IF NOT EXISTS idx_signals_document ON intelligence_signals(document_id);

-- ============================================================
-- CHAT HISTORY (optional, for context window management)
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    session_id UUID DEFAULT gen_random_uuid(),
    user_label TEXT DEFAULT 'colin',     -- who's chatting (just a label for now)
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    role TEXT NOT NULL,                  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    source_chunks INT[],                -- which chunk IDs were used for this response
    source_signals INT[],               -- which signal IDs were cited
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
