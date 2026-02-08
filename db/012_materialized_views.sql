-- Migration 012: Materialized Views for Neighborhood Composite Scores (VCL-79 / PERF-011)
-- Optimizes performance of neighborhood ranking, scoring, and signal activity queries
-- Provides fast reads for frequently-accessed neighborhood scorecard data

-- ============================================================
-- MATERIALIZED VIEW 1: Neighborhood Composite Scores
-- Aggregates latest neighborhood scores with signal activity
-- Refreshed periodically (default 1 hour)
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_neighborhood_scores AS
SELECT
    n.id,
    n.name,
    n.slug,
    n.centroid,
    -- Latest composite score (weighted average of category scores)
    COALESCE(
        (SELECT overall_score FROM neighborhood_composite_scores ncs
         WHERE ncs.neighborhood_id = n.id
         ORDER BY ncs.period_start DESC
         LIMIT 1),
        5.0  -- default if no scores exist
    ) AS overall_score,
    -- Rank by overall score (dense_rank)
    DENSE_RANK() OVER (ORDER BY
        COALESCE(
            (SELECT overall_score FROM neighborhood_composite_scores ncs
             WHERE ncs.neighborhood_id = n.id
             ORDER BY ncs.period_start DESC
             LIMIT 1),
            5.0
        ) DESC
    ) AS rank,
    -- Latest category scores as JSONB
    COALESCE(
        (SELECT category_scores FROM neighborhood_composite_scores ncs
         WHERE ncs.neighborhood_id = n.id
         ORDER BY ncs.period_start DESC
         LIMIT 1),
        '{}'::jsonb
    ) AS category_scores,
    -- Count of active rezonings (signal_type = 'rezoning_decision' in last 90 days)
    (SELECT COUNT(*) FROM intelligence_signals
     WHERE neighborhood = n.name
     AND signal_type = 'rezoning_decision'
     AND event_date >= CURRENT_DATE - INTERVAL '90 days'
     AND event_date IS NOT NULL) AS active_rezonings,
    -- Count of recent permits (signal_type = 'permit_approval' in last 30 days)
    (SELECT COUNT(*) FROM intelligence_signals
     WHERE neighborhood = n.name
     AND signal_type = 'permit_approval'
     AND event_date >= CURRENT_DATE - INTERVAL '30 days'
     AND event_date IS NOT NULL) AS recent_permits,
    -- Signal activity score (total signals in last 90 days / 10, capped at 10.0)
    LEAST(10.0,
        COALESCE(
            (SELECT COUNT(*) * 0.1 FROM intelligence_signals
             WHERE neighborhood = n.name
             AND created_at >= CURRENT_DATE - INTERVAL '90 days'),
            0
        )
    ) AS signal_activity_score,
    -- Timestamp of last refresh
    CURRENT_TIMESTAMP AS refreshed_at
FROM neighborhoods n
ORDER BY overall_score DESC, n.name;

-- Create unique index for REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_neighborhood_scores_unique
ON mv_neighborhood_scores (id);

-- ============================================================
-- MATERIALIZED VIEW 2: Neighborhood Signal Activity
-- Temporal signal metrics for each neighborhood
-- 7-day, 30-day, and 90-day rolling windows
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_neighborhood_signal_activity AS
SELECT
    n.id,
    n.name,
    n.slug,
    -- 7-day signal count
    (SELECT COUNT(*) FROM intelligence_signals
     WHERE neighborhood = n.name
     AND created_at >= CURRENT_DATE - INTERVAL '7 days') AS signals_7d,
    -- 30-day signal count
    (SELECT COUNT(*) FROM intelligence_signals
     WHERE neighborhood = n.name
     AND created_at >= CURRENT_DATE - INTERVAL '30 days') AS signals_30d,
    -- 90-day signal count
    (SELECT COUNT(*) FROM intelligence_signals
     WHERE neighborhood = n.name
     AND created_at >= CURRENT_DATE - INTERVAL '90 days') AS signals_90d,
    -- Most common signal type (dominant signal)
    (SELECT signal_type FROM intelligence_signals
     WHERE neighborhood = n.name
     AND created_at >= CURRENT_DATE - INTERVAL '90 days'
     GROUP BY signal_type
     ORDER BY COUNT(*) DESC
     LIMIT 1) AS dominant_signal_type,
    -- Average severity (mapped to numeric: info=1, low=2, medium=3, high=4, critical=5)
    COALESCE(
        ROUND(AVG(
            CASE severity
                WHEN 'info' THEN 1
                WHEN 'low' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'high' THEN 4
                WHEN 'critical' THEN 5
                ELSE 1
            END
        )::numeric, 2),
        1.0
    ) AS avg_severity,
    -- Timestamp of last refresh
    CURRENT_TIMESTAMP AS refreshed_at
FROM neighborhoods n
LEFT JOIN intelligence_signals is_table ON is_table.neighborhood = n.name
    AND is_table.created_at >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY n.id, n.name, n.slug
ORDER BY n.name;

-- Create unique index for REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_neighborhood_signal_activity_unique
ON mv_neighborhood_signal_activity (id);

-- ============================================================
-- REFRESH FUNCTIONS
-- Callable from application code to refresh materialized views
-- ============================================================

-- Refresh neighborhood scores view
CREATE OR REPLACE FUNCTION refresh_mv_neighborhood_scores()
RETURNS TABLE (
    view_name TEXT,
    rows_refreshed BIGINT,
    duration_ms BIGINT,
    success BOOLEAN
) AS $$
DECLARE
    v_start_time TIMESTAMP;
    v_row_count BIGINT;
    v_duration BIGINT;
BEGIN
    v_start_time := CLOCK_TIMESTAMP();

    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_neighborhood_scores;

    v_duration := EXTRACT(EPOCH FROM (CLOCK_TIMESTAMP() - v_start_time)) * 1000;
    SELECT COUNT(*) INTO v_row_count FROM mv_neighborhood_scores;

    RETURN QUERY SELECT
        'mv_neighborhood_scores'::TEXT,
        v_row_count,
        v_duration,
        TRUE;
END;
$$ LANGUAGE plpgsql;

-- Refresh neighborhood signal activity view
CREATE OR REPLACE FUNCTION refresh_mv_neighborhood_signal_activity()
RETURNS TABLE (
    view_name TEXT,
    rows_refreshed BIGINT,
    duration_ms BIGINT,
    success BOOLEAN
) AS $$
DECLARE
    v_start_time TIMESTAMP;
    v_row_count BIGINT;
    v_duration BIGINT;
BEGIN
    v_start_time := CLOCK_TIMESTAMP();

    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_neighborhood_signal_activity;

    v_duration := EXTRACT(EPOCH FROM (CLOCK_TIMESTAMP() - v_start_time)) * 1000;
    SELECT COUNT(*) INTO v_row_count FROM mv_neighborhood_signal_activity;

    RETURN QUERY SELECT
        'mv_neighborhood_signal_activity'::TEXT,
        v_row_count,
        v_duration,
        TRUE;
END;
$$ LANGUAGE plpgsql;

-- Refresh all materialized views
CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS TABLE (
    view_name TEXT,
    rows_refreshed BIGINT,
    duration_ms BIGINT,
    success BOOLEAN
) AS $$
BEGIN
    RETURN QUERY SELECT * FROM refresh_mv_neighborhood_scores();
    RETURN QUERY SELECT * FROM refresh_mv_neighborhood_signal_activity();
END;
$$ LANGUAGE plpgsql;

-- Log materialized view refresh operations for audit
CREATE TABLE IF NOT EXISTS materialized_view_refreshes (
    id SERIAL PRIMARY KEY,
    view_name TEXT NOT NULL,
    rows_refreshed BIGINT,
    duration_ms BIGINT,
    success BOOLEAN,
    error_message TEXT,
    refreshed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mv_refreshes_view_name ON materialized_view_refreshes(view_name);
CREATE INDEX IF NOT EXISTS idx_mv_refreshes_timestamp ON materialized_view_refreshes(refreshed_at DESC);

-- Verify materialized views were created
DO $$
BEGIN
    RAISE NOTICE 'Materialized views created:';
    RAISE NOTICE '  - mv_neighborhood_scores (neighborhoods with scores and signal activity)';
    RAISE NOTICE '  - mv_neighborhood_signal_activity (7d/30d/90d signal counts)';
    RAISE NOTICE 'Refresh functions available:';
    RAISE NOTICE '  - refresh_mv_neighborhood_scores()';
    RAISE NOTICE '  - refresh_mv_neighborhood_signal_activity()';
    RAISE NOTICE '  - refresh_all_materialized_views()';
END $$;
