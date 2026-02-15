-- Migration 034: Setback Rules & Site Coverage
-- Adds zoning-based setback and site coverage constraints for FR-HBU-008

-- ============================================================
-- ZONING SETBACK RULES TABLE
-- Stores front/rear/side setback requirements by zoning district
-- Source: City of Vancouver Zoning & Development By-law
-- ============================================================
CREATE TABLE IF NOT EXISTS zoning_setback_rules (
    id SERIAL PRIMARY KEY,
    zoning_district TEXT NOT NULL UNIQUE,  -- e.g. 'RS-1', 'RM-4', 'CD-1'

    -- Setback distances in metres
    front_setback_m NUMERIC(5,2) NOT NULL DEFAULT 6.0,
    rear_setback_m  NUMERIC(5,2) NOT NULL DEFAULT 7.5,
    side_setback_m  NUMERIC(5,2) NOT NULL DEFAULT 1.2,

    -- Site coverage (building footprint / lot area)
    max_site_coverage NUMERIC(4,3) NOT NULL DEFAULT 0.45,  -- 0.45 = 45%

    -- Notes
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_setback_rules_zoning ON zoning_setback_rules(zoning_district);

-- Seed common Vancouver zoning districts with typical setback rules
-- Source: City of Vancouver Zoning & Development By-law (simplified)
INSERT INTO zoning_setback_rules (zoning_district, front_setback_m, rear_setback_m, side_setback_m, max_site_coverage, notes) VALUES
    -- Single-family residential
    ('RS-1',  7.3, 7.9, 1.2, 0.45, 'Standard single-family residential'),
    ('RS-1A', 7.3, 7.9, 1.2, 0.45, 'Single-family residential (small lot)'),
    ('RS-1B', 7.3, 7.9, 1.2, 0.45, 'Single-family residential (Shaughnessy)'),
    ('RS-2',  7.3, 7.9, 1.2, 0.45, 'One-family dwelling with secondary suite'),
    ('RS-3',  7.3, 10.7, 1.2, 0.45, 'One-family with rear detached'),
    ('RS-3A', 7.3, 10.7, 1.2, 0.45, 'One-family with rear detached (variant)'),
    ('RS-5',  7.3, 7.9, 1.2, 0.45, 'One-family with infill'),
    ('RS-6',  7.3, 7.9, 1.2, 0.45, 'One-family residential (Oakridge)'),
    ('RS-7',  7.3, 7.9, 1.2, 0.45, 'One-family residential (Southlands)'),

    -- Two-family residential
    ('RT-1',  3.7, 7.9, 1.2, 0.45, 'Two-family dwelling'),
    ('RT-2',  3.7, 7.9, 1.2, 0.45, 'Two-family dwelling (Grandview-Woodland)'),
    ('RT-3',  3.7, 7.9, 0.9, 0.45, 'Two-family dwelling (First Shaughnessy)'),

    -- Multi-family residential
    ('RM-1',  3.7, 7.9, 0.9, 0.50, 'Low-density multiple dwelling'),
    ('RM-2',  3.7, 7.9, 0.9, 0.50, 'Low-density multiple dwelling (Kitsilano)'),
    ('RM-3',  3.7, 7.9, 0.9, 0.55, 'Medium-density multiple dwelling'),
    ('RM-3A', 3.7, 7.9, 0.9, 0.55, 'Medium-density multiple dwelling (variant)'),
    ('RM-4',  3.7, 7.6, 0.9, 0.55, 'Medium-density apartment'),
    ('RM-4N', 3.7, 7.6, 0.9, 0.55, 'Medium-density apartment (Norquay)'),
    ('RM-5',  3.7, 7.6, 0.9, 0.55, 'Medium-density apartment (Norquay Village)'),
    ('RM-5A', 3.7, 7.6, 0.9, 0.55, 'Medium-density apartment (Norquay Village A)'),
    ('RM-5B', 3.7, 7.6, 0.9, 0.55, 'Medium-density apartment (Norquay Village B)'),
    ('RM-5C', 3.7, 7.6, 0.9, 0.55, 'Medium-density apartment (Norquay Village C)'),
    ('RM-5D', 3.7, 7.6, 0.9, 0.55, 'Medium-density apartment (Norquay Village D)'),
    ('RM-6',  3.7, 7.6, 0.9, 0.60, 'Higher-density multiple dwelling'),
    ('RM-7',  3.7, 7.6, 0.9, 0.55, 'Multiple dwelling (Marpole)'),
    ('RM-8',  3.7, 7.6, 0.9, 0.55, 'Multiple dwelling (Marpole low-rise)'),
    ('RM-8N', 3.7, 7.6, 0.9, 0.55, 'Multiple dwelling (Marpole low-rise N)'),
    ('RM-9',  3.7, 7.6, 0.9, 0.55, 'Multiple dwelling (Marpole mid-rise)'),
    ('RM-9N', 3.7, 7.6, 0.9, 0.55, 'Multiple dwelling (Marpole mid-rise N)'),
    ('RM-10', 3.7, 7.6, 0.9, 0.60, 'Multiple dwelling (Grandview)'),
    ('RM-10N',3.7, 7.6, 0.9, 0.60, 'Multiple dwelling (Grandview N)'),
    ('RM-11', 3.7, 7.6, 0.9, 0.60, 'Multiple dwelling (Norquay)'),
    ('RM-12N',3.7, 7.6, 0.9, 0.60, 'Multiple dwelling (Cambie Corridor)'),

    -- Commercial / mixed-use
    ('C-1',   0.0, 3.0, 0.0, 0.75, 'Commercial: neighbourhood'),
    ('C-2',   0.0, 3.0, 0.0, 1.00, 'Commercial: community'),
    ('C-2B',  0.0, 3.0, 0.0, 1.00, 'Commercial: community (Kingsway)'),
    ('C-2C',  0.0, 3.0, 0.0, 1.00, 'Commercial: community (Cambie)'),
    ('C-2C1', 0.0, 3.0, 0.0, 1.00, 'Commercial: community (Cambie Village)'),
    ('C-3A',  0.0, 3.0, 0.0, 1.00, 'Commercial: Downtown'),
    ('C-5',   0.0, 0.0, 0.0, 1.00, 'Commercial: auto-oriented'),
    ('C-6',   0.0, 0.0, 0.0, 1.00, 'Commercial: auto-oriented mixed'),

    -- Downtown
    ('DD',    0.0, 0.0, 0.0, 1.00, 'Downtown District'),

    -- Comprehensive Development
    ('CD-1',  0.0, 3.0, 0.0, 0.70, 'Comprehensive Development (site-specific)')
ON CONFLICT (zoning_district) DO NOTHING;
