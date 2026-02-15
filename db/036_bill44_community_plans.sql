-- Migration 036: Bill 44 Small-Scale Multi-Unit Housing + Community Plan Density Bonuses
-- Bill 44 (Housing Statutes Amendment Act, 2023) enables multiplex housing
-- on single/duplex-zoned lots across BC municipalities.

-- ============================================================
-- BILL 44 ZONING ELIGIBILITY
-- Defines which zoning districts are eligible for Bill 44 SSMUH
-- ============================================================
CREATE TABLE IF NOT EXISTS bill44_eligible_zones (
    id SERIAL PRIMARY KEY,
    zoning_district TEXT NOT NULL UNIQUE,
    zone_category TEXT NOT NULL,           -- 'single_family', 'duplex', 'excluded'
    is_eligible BOOLEAN DEFAULT true,
    notes TEXT
);

-- Seed Vancouver RS-* and RT-* zones as eligible
INSERT INTO bill44_eligible_zones (zoning_district, zone_category, is_eligible, notes) VALUES
    ('RS-1',  'single_family', true,  'Standard single-family residential'),
    ('RS-1A', 'single_family', true,  'Single-family with secondary suite'),
    ('RS-1B', 'single_family', true,  'Single-family small lot'),
    ('RS-2',  'single_family', true,  'Single-family residential (Hastings area)'),
    ('RS-3',  'single_family', true,  'Single-family residential (First Shaughnessy)'),
    ('RS-3A', 'single_family', true,  'Single-family residential (First Shaughnessy heritage)'),
    ('RS-4',  'single_family', true,  'Single-family residential (Queen Mary)'),
    ('RS-5',  'single_family', true,  'Single-family residential (Norquay Village)'),
    ('RS-6',  'single_family', true,  'Single-family residential'),
    ('RS-7',  'single_family', true,  'Single-family residential (Southlands)'),
    ('RT-1',  'duplex',        true,  'Two-family dwelling'),
    ('RT-2',  'duplex',        true,  'Two-family dwelling'),
    ('RT-3',  'duplex',        true,  'Two-family dwelling (Grandview-Woodland)'),
    ('RT-4',  'duplex',        true,  'Two-family dwelling'),
    ('RT-4A', 'duplex',        true,  'Two-family dwelling'),
    ('RT-4N', 'duplex',        true,  'Two-family dwelling (Norquay)'),
    ('RT-5',  'duplex',        true,  'Two-family dwelling (Marpole)'),
    ('RT-5N', 'duplex',        true,  'Two-family dwelling (Norquay)'),
    ('RT-6',  'duplex',        true,  'Two-family dwelling (Cambie Corridor)'),
    ('RT-7',  'duplex',        true,  'Two-family dwelling'),
    ('RT-8',  'duplex',        true,  'Two-family dwelling'),
    ('RT-9',  'duplex',        true,  'Two-family dwelling'),
    ('RT-10', 'duplex',        true,  'Two-family dwelling'),
    ('RT-10N','duplex',        true,  'Two-family dwelling (Norquay)'),
    ('RT-11', 'duplex',        true,  'Two-family dwelling'),
    ('RT-11N','duplex',        true,  'Two-family dwelling (Norquay)')
ON CONFLICT (zoning_district) DO NOTHING;

-- ============================================================
-- COMMUNITY PLAN DENSITY BONUSES
-- Structured rules extracted from adopted community plans
-- ============================================================
CREATE TABLE IF NOT EXISTS community_plan_bonuses (
    id SERIAL PRIMARY KEY,
    plan_name TEXT NOT NULL,                -- e.g., 'Cambie Corridor Plan'
    plan_area TEXT NOT NULL,                -- sub-area within plan, e.g., 'Phase 3 - Cambie Village'
    applicable_zoning TEXT[],               -- array of zoning codes this bonus applies to
    bonus_fsr NUMERIC(4,2),                -- additional FSR above base entitlement
    bonus_storeys INTEGER,                  -- additional storeys above base
    max_fsr NUMERIC(4,2),                  -- absolute max FSR under this plan
    max_storeys INTEGER,                    -- absolute max storeys under this plan
    conditions TEXT,                        -- conditions for bonus (e.g., 'rental housing', '20% affordable')
    effective_date DATE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cpb_plan_name ON community_plan_bonuses(plan_name);
CREATE INDEX IF NOT EXISTS idx_cpb_plan_area ON community_plan_bonuses(plan_area);

-- Seed with major Vancouver community plan bonuses
INSERT INTO community_plan_bonuses (plan_name, plan_area, applicable_zoning, bonus_fsr, bonus_storeys, max_fsr, max_storeys, conditions, effective_date) VALUES
    -- Cambie Corridor Plan
    ('Cambie Corridor Plan', 'Phase 3 - Cambie Village', ARRAY['RS-1','RT-1','RT-2','C-1'], 1.50, 4, 6.00, 24, '20% below-market rental required', '2018-05-15'),
    ('Cambie Corridor Plan', 'Phase 3 - Oakridge Town Centre', ARRAY['RS-1','C-2','CD-1'], 2.00, 8, 7.50, 28, 'Mixed-use; 25% rental or affordable', '2018-05-15'),
    ('Cambie Corridor Plan', 'Phase 3 - Marine Landing', ARRAY['RS-1','RT-1'], 1.00, 2, 5.00, 18, 'Mixed-use; community amenity contribution', '2018-05-15'),
    ('Cambie Corridor Plan', 'Phase 2 - Queen Elizabeth', ARRAY['RS-1','RM-3','C-1'], 0.75, 2, 4.50, 14, 'Secured rental housing bonus', '2011-09-01'),

    -- Grandview-Woodland Community Plan
    ('Grandview-Woodland Plan', 'Nanaimo St Commercial', ARRAY['RT-3','C-1','C-2'], 1.00, 3, 5.00, 15, 'Mixed-use commercial + residential', '2016-07-20'),
    ('Grandview-Woodland Plan', 'Commercial Drive', ARRAY['RT-3','C-1'], 0.50, 2, 3.50, 10, '100% rental housing', '2016-07-20'),
    ('Grandview-Woodland Plan', 'Hastings Corridor', ARRAY['RT-3','RT-4','C-2'], 0.75, 2, 4.00, 12, 'Mixed-use with community amenity', '2016-07-20'),

    -- Marpole Community Plan
    ('Marpole Plan', 'Granville Corridor', ARRAY['RS-1','RT-5','C-1','C-2'], 1.50, 4, 6.00, 22, 'Mixed-use transit corridor', '2014-03-01'),
    ('Marpole Plan', 'Neighbourhood Apartment', ARRAY['RS-1','RT-5'], 0.50, 1, 2.50, 6, 'Townhouse/low-rise transition', '2014-03-01'),
    ('Marpole Plan', 'Marine Dr Station Area', ARRAY['RS-1','RT-5','C-1'], 1.00, 3, 5.50, 20, 'High-density near Marine Dr station', '2014-03-01'),

    -- West End Community Plan
    ('West End Plan', 'Davie Village', ARRAY['RM-5','RM-5A','C-5'], 1.00, 3, 6.50, 22, 'Heritage density transfer; 30% social housing', '2013-11-01'),
    ('West End Plan', 'Robson Corridor', ARRAY['RM-5','C-5','C-6'], 0.75, 2, 6.00, 20, 'Commercial mixed-use bonus', '2013-11-01'),

    -- Joyce-Collingwood Station Precinct Plan
    ('Joyce-Collingwood Plan', 'Station Area Core', ARRAY['RS-1','RT-4','C-2'], 2.00, 6, 7.00, 30, 'Transit hub density bonus', '2017-06-01'),
    ('Joyce-Collingwood Plan', 'Kingsway Corridor', ARRAY['RS-1','RT-4','C-2'], 1.00, 3, 5.00, 16, 'Mixed-use; 20% family-sized units', '2017-06-01'),

    -- Norquay Village Neighbourhood Centre Plan
    ('Norquay Village Plan', 'Kingsway Node', ARRAY['RS-5','RT-4N','RT-5N','RT-10N','C-2'], 1.00, 3, 4.50, 12, 'Local commercial + residential', '2010-09-01'),
    ('Norquay Village Plan', 'Neighbourhood Transition', ARRAY['RS-5','RT-4N','RT-5N'], 0.50, 1, 2.50, 5, 'Townhouse/rowhouse transition', '2010-09-01')
ON CONFLICT DO NOTHING;
