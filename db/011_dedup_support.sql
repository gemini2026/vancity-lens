-- Migration 011: Deduplication Support for VCL-76 [DATA-003]
-- Adds content hashing, simhash, and fuzzy matching infrastructure
-- to support scraper deduplication logic

-- ============================================================
-- Enable pg_trgm extension for trigram-based fuzzy matching
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- Add deduplication columns to documents table
-- ============================================================

-- Content hash (SHA-256) for exact content matching
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- SimHash (64-bit locality-sensitive hash) for fast approximate matching
ALTER TABLE documents ADD COLUMN IF NOT EXISTS simhash BIGINT;

-- ============================================================
-- Create indexes for deduplication performance
-- ============================================================

-- Index on content_hash for O(1) exact content lookups
CREATE INDEX IF NOT EXISTS idx_documents_content_hash
    ON documents(content_hash)
    WHERE content_hash IS NOT NULL;

-- Index on simhash for fast near-duplicate detection
CREATE INDEX IF NOT EXISTS idx_documents_simhash
    ON documents(simhash)
    WHERE simhash IS NOT NULL;

-- GIN trigram index on title for fuzzy full-text matching
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm
    ON documents USING gin(title gin_trgm_ops)
    WHERE title IS NOT NULL;

-- GIN trigram index on raw_text for content similarity
CREATE INDEX IF NOT EXISTS idx_documents_text_trgm
    ON documents USING gin(raw_text gin_trgm_ops)
    WHERE raw_text IS NOT NULL;

-- ============================================================
-- Function: Calculate text similarity using trigrams
-- Used in DuplicateDetector.find_near_duplicates()
-- ============================================================
CREATE OR REPLACE FUNCTION text_similarity(text1 TEXT, text2 TEXT)
RETURNS FLOAT AS $$
BEGIN
    -- Returns similarity score (0.0 - 1.0) using trigram similarity
    -- Returns 0 if either text is NULL
    IF text1 IS NULL OR text2 IS NULL THEN
        RETURN 0.0;
    END IF;

    RETURN similarity(text1, text2);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================
-- Function: Update content_hash on document insert/update
-- ============================================================
CREATE OR REPLACE FUNCTION update_document_content_hash()
RETURNS TRIGGER AS $$
BEGIN
    -- Compute SHA-256 hash of normalized text if raw_text is provided
    -- For now, store MD5 hash (PostgreSQL built-in, crypto extension not required)
    -- In production, this would be computed by Python's hashlib.sha256
    -- This trigger serves as a fallback/validation

    IF NEW.raw_text IS NOT NULL AND NEW.raw_text != '' THEN
        NEW.content_hash := md5(lower(NEW.raw_text));
    ELSE
        NEW.content_hash := NULL;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop existing trigger if it exists to avoid conflicts
DROP TRIGGER IF EXISTS trg_document_content_hash ON documents;

-- Create trigger to update content_hash on INSERT or UPDATE
CREATE TRIGGER trg_document_content_hash
    BEFORE INSERT OR UPDATE OF raw_text ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_document_content_hash();

-- ============================================================
-- Statistics: Document deduplication summary view
-- ============================================================
CREATE OR REPLACE VIEW document_dedup_stats AS
SELECT
    source_type,
    COUNT(*) as total_documents,
    COUNT(DISTINCT content_hash) as unique_content_hashes,
    COUNT(*) - COUNT(DISTINCT content_hash) as duplicate_documents,
    ROUND(100.0 * (COUNT(*) - COUNT(DISTINCT content_hash)) / NULLIF(COUNT(*), 0), 2) as duplicate_percentage,
    COUNT(DISTINCT source_url) as unique_urls,
    MAX(scraped_at) as last_scrape,
    MIN(scraped_at) as first_scrape
FROM documents
WHERE content_hash IS NOT NULL
GROUP BY source_type
ORDER BY total_documents DESC;

-- ============================================================
-- Statistics: Recent deduplication activity
-- ============================================================
CREATE OR REPLACE VIEW recent_dedup_activity AS
SELECT
    source_type,
    DATE_TRUNC('day', scraped_at) as scrape_date,
    COUNT(*) as documents_scraped,
    COUNT(DISTINCT content_hash) as unique_contents,
    COUNT(*) - COUNT(DISTINCT content_hash) as duplicates_found
FROM documents
WHERE scraped_at >= now() - interval '30 days'
GROUP BY source_type, DATE_TRUNC('day', scraped_at)
ORDER BY source_type, scrape_date DESC;

-- ============================================================
-- Grant permissions (adjust as needed for your security model)
-- ============================================================
-- Assuming documents table already exists with proper permissions
-- No additional grants needed if using role-based access control
