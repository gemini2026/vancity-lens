-- Migration 046: Data source freshness monitoring (DI-006)

CREATE TABLE IF NOT EXISTS data_source_freshness (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    expected_cadence_hours INT NOT NULL,
    last_successful_retrieval TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO data_source_freshness (source_id, source_name, expected_cadence_hours)
VALUES
    ('DS-001', 'City of Vancouver Open Data', 24),
    ('DS-002', 'BC Assessment', 2160),
    ('DS-004', 'TransLink GTFS', 2160),
    ('DS-005', 'BC Laws', 168),
    ('DS-006', 'Vancouver Council Agendas', 168),
    ('DS-007', 'BC Contaminated Sites Registry', 720),
    ('DS-008', 'StatsCan Web Data Service', 24),
    ('DS-009', 'CMHC Housing Data', 720),
    ('DS-010', 'Vancouver Heritage Register', 8760),
    ('DS-011', 'Vancouver View Cones', 8760),
    ('DS-012', 'Vancouver Neighbourhood Plans', 8760),
    ('DS-013', 'Local News Sources', 24),
    ('DS-014', 'BC Gazette', 168)
ON CONFLICT (source_id) DO NOTHING;
