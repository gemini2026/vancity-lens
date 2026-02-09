-- ================================================================
-- E2E Test Seed Data
-- Idempotent: safe to run multiple times
-- Provides representative data for UI testing
-- Matches schema from 007_intelligence_layer.sql
-- ================================================================

-- Seed intelligence documents (id is SERIAL, use explicit integer IDs)
INSERT INTO documents (id, source_type, source_url, title, raw_text, scraped_at, processed_at, metadata)
VALUES
  (10001, 'council_minutes', 'https://council.vancouver.ca/e2e-test-1',
   'Council Meeting — January 2026 Regular Session',
   'The Council approved the rezoning application for 1234 Main Street from RS-1 to RM-4, allowing construction of a 6-storey mixed-use building with 120 rental units. The vote passed 7-4 with conditions including 20% below-market rental units and ground-floor commercial space. Council also discussed the Broadway Plan implementation timeline and transit-oriented area density bonuses near SkyTrain stations.',
   NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days',
   '{"meeting_date": "2026-01-15", "session_type": "regular"}'::jsonb),

  (10002, 'rezoning_application', 'https://rezoning.vancouver.ca/e2e-test-2',
   'Rezoning Application — 555 West Broadway',
   'Application to rezone 555 West Broadway from C-3A to CD-1, proposing a 28-storey mixed-use tower with 350 residential units, 15,000 sq ft of commercial space, and underground parking for 200 vehicles. The proposal includes a community amenity contribution of $3.2 million toward affordable housing and park improvements in Mount Pleasant.',
   NOW() - INTERVAL '5 days', NOW() - INTERVAL '5 days',
   '{"application_number": "RZ-2026-001", "applicant": "Westbank Corp"}'::jsonb),

  (10003, 'dpb_minutes', 'https://vancouver.ca/dpb/e2e-test-3',
   'Development Permit Board Meeting — December 2025',
   'The Board approved the development permit for 2100 Commercial Drive, a 4-storey residential building with 48 units. Community members raised concerns about shadowing and parking, but the Board found the proposal consistent with the Grandview-Woodland Community Plan. The applicant agreed to additional landscaping requirements along the lane.',
   NOW() - INTERVAL '10 days', NOW() - INTERVAL '10 days',
   '{"meeting_date": "2025-12-18"}'::jsonb),

  (10004, 'news', 'https://vancouversun.com/e2e-test-4',
   'Vancouver approves new transit-oriented development near Renfrew Station',
   'The City of Vancouver has given the green light to a major transit-oriented development near Renfrew SkyTrain station. The project will include 500 residential units, a community center, and retail space. The development is part of the broader Transit-Oriented Areas (TOA) framework under Bill 47, which allows increased density within 800 meters of rapid transit stations.',
   NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day',
   '{"source": "Vancouver Sun", "author": "Jane Reporter"}'::jsonb),

  (10005, 'news', 'https://biv.com/e2e-test-5',
   'Mount Pleasant condo prices surge amid rezoning wave',
   'Real estate prices in Mount Pleasant have jumped 12% year-over-year as multiple rezoning applications transform the neighborhood. Developers are betting on the area''s proximity to transit and the Broadway Plan''s allowance for increased density. Analysts note that the pipeline of approved projects could add over 2,000 new units to the area by 2028.',
   NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days',
   '{"source": "Business in Vancouver"}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- Reset sequence to avoid conflicts with seed IDs
SELECT setval('documents_id_seq', GREATEST(nextval('documents_id_seq'), 10100));

-- Seed document chunks (matches schema: chunk_text, section_header, token_count)
INSERT INTO document_chunks (id, document_id, chunk_index, chunk_text, token_count, section_header)
VALUES
  (10001, 10001, 0,
   'The Council approved the rezoning application for 1234 Main Street from RS-1 to RM-4, allowing construction of a 6-storey mixed-use building with 120 rental units. The vote passed 7-4 with conditions including 20% below-market rental units and ground-floor commercial space.',
   62, 'Rezoning Decision'),
  (10002, 10001, 1,
   'Council also discussed the Broadway Plan implementation timeline and transit-oriented area density bonuses near SkyTrain stations.',
   22, 'Broadway Plan'),
  (10003, 10002, 0,
   'Application to rezone 555 West Broadway from C-3A to CD-1, proposing a 28-storey mixed-use tower with 350 residential units, 15,000 sq ft of commercial space, and underground parking for 200 vehicles.',
   44, 'Application Details'),
  (10004, 10003, 0,
   'The Board approved the development permit for 2100 Commercial Drive, a 4-storey residential building with 48 units. Community members raised concerns about shadowing and parking.',
   33, 'Permit Decision'),
  (10005, 10004, 0,
   'The City of Vancouver has given the green light to a major transit-oriented development near Renfrew SkyTrain station. The project will include 500 residential units, a community center, and retail space.',
   38, 'TOD Approval'),
  (10006, 10005, 0,
   'Real estate prices in Mount Pleasant have jumped 12% year-over-year as multiple rezoning applications transform the neighborhood. Developers are betting on the area proximity to transit and the Broadway Plan.',
   40, 'Market Analysis')
ON CONFLICT (id) DO NOTHING;

SELECT setval('document_chunks_id_seq', GREATEST(nextval('document_chunks_id_seq'), 10100));

-- Seed intelligence signals (matches actual schema columns)
INSERT INTO intelligence_signals (
  id, document_id, signal_type, severity, headline, summary,
  addresses, neighborhood, geom,
  event_date, extracted_at
)
VALUES
  (10001, 10001, 'rezoning_decision', 'high',
   'RS-1 to RM-4 Rezoning Approved — 1234 Main Street',
   'Council approved rezoning from RS-1 to RM-4, enabling a 6-storey mixed-use building with 120 rental units. Vote: 7-4. Conditions include 20% below-market rental.',
   ARRAY['1234 Main Street'], 'Mount Pleasant',
   ST_SetSRID(ST_MakePoint(-123.1010, 49.2630), 4326),
   CURRENT_DATE - 2, NOW() - INTERVAL '3 days'),

  (10002, 10002, 'density_change', 'critical',
   '28-Storey Tower Proposed — 555 West Broadway',
   'Major rezoning application: C-3A to CD-1 for a 28-storey mixed-use tower with 350 units. Community amenity contribution of $3.2M.',
   ARRAY['555 West Broadway'], 'Mount Pleasant',
   ST_SetSRID(ST_MakePoint(-123.1143, 49.2634), 4326),
   CURRENT_DATE - 5, NOW() - INTERVAL '5 days'),

  (10003, 10003, 'permit_approval', 'medium',
   'Development Permit Approved — 2100 Commercial Drive',
   'DPB approved 4-storey residential building with 48 units on Commercial Drive. Community concerns about shadowing were addressed.',
   ARRAY['2100 Commercial Drive'], 'Grandview-Woodland',
   ST_SetSRID(ST_MakePoint(-123.0700, 49.2690), 4326),
   CURRENT_DATE - 10, NOW() - INTERVAL '10 days'),

  (10004, 10004, 'infrastructure_announcement', 'high',
   'TOD Approved Near Renfrew Station — 500 Units',
   'Major transit-oriented development approved near Renfrew SkyTrain station: 500 units, community center, and retail under Bill 47 TOA framework.',
   ARRAY['Renfrew Station Area'], 'Renfrew-Collingwood',
   ST_SetSRID(ST_MakePoint(-123.0340, 49.2590), 4326),
   CURRENT_DATE - 20, NOW() - INTERVAL '1 day'),

  (10005, 10005, 'community_opposition', 'low',
   'Mount Pleasant Condo Prices Surge 12% YoY',
   'Real estate prices surging in Mount Pleasant amid rezoning wave. Over 2,000 new units in development pipeline through 2028.',
   ARRAY['Mount Pleasant Area'], 'Mount Pleasant',
   ST_SetSRID(ST_MakePoint(-123.1050, 49.2620), 4326),
   CURRENT_DATE - 45, NOW() - INTERVAL '2 days')

ON CONFLICT (id) DO NOTHING;

SELECT setval('intelligence_signals_id_seq', GREATEST(nextval('intelligence_signals_id_seq'), 10100));

-- Verify seed data
DO $$
DECLARE
  doc_count INTEGER;
  chunk_count INTEGER;
  signal_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO doc_count FROM documents WHERE id >= 10001 AND id <= 10005;
  SELECT COUNT(*) INTO chunk_count FROM document_chunks WHERE id >= 10001 AND id <= 10006;
  SELECT COUNT(*) INTO signal_count FROM intelligence_signals WHERE id >= 10001 AND id <= 10005;
  RAISE NOTICE 'E2E seed data: % documents, % chunks, % signals', doc_count, chunk_count, signal_count;
END $$;
