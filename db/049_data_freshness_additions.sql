-- Migration 049: Add missing data sources to freshness monitoring (F02-001, F04-001)
-- Adds development_applications, political_risk, DPB, and rezoning sources

INSERT INTO data_source_freshness (source_id, source_name, expected_cadence_hours)
VALUES
    ('DS-015', 'Development Applications (DPB)', 168),
    ('DS-016', 'Rezoning Applications', 168),
    ('DS-017', 'Political Risk Scores', 168),
    ('DS-018', 'Development Pipeline (Supply)', 24)
ON CONFLICT (source_id) DO NOTHING;

-- Update council agendas cadence to 24h (was 168h) to match daily scraping schedule
UPDATE data_source_freshness
SET expected_cadence_hours = 24
WHERE source_id = 'DS-006'
  AND expected_cadence_hours = 168;
