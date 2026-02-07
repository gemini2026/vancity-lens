-- ================================================================
-- E2E Test Seed Data
-- Idempotent: safe to run multiple times
-- Provides representative data for UI testing
-- ================================================================

-- Seed intelligence documents
INSERT INTO documents (id, source_type, source_url, title, content, scraped_at, processed, metadata)
VALUES
  ('e2e-doc-001', 'council_minutes', 'https://council.vancouver.ca/e2e-test-1', 
   'Council Meeting — January 2026 Regular Session',
   'The Council approved the rezoning application for 1234 Main Street from RS-1 to RM-4, allowing construction of a 6-storey mixed-use building with 120 rental units. The vote passed 7-4 with conditions including 20% below-market rental units and ground-floor commercial space. Council also discussed the Broadway Plan implementation timeline and transit-oriented area density bonuses near SkyTrain stations.',
   NOW() - INTERVAL '3 days', true,
   '{"meeting_date": "2026-01-15", "session_type": "regular"}'::jsonb),

  ('e2e-doc-002', 'rezoning_application', 'https://rezoning.vancouver.ca/e2e-test-2',
   'Rezoning Application — 555 West Broadway',
   'Application to rezone 555 West Broadway from C-3A to CD-1, proposing a 28-storey mixed-use tower with 350 residential units, 15,000 sq ft of commercial space, and underground parking for 200 vehicles. The proposal includes a community amenity contribution of $3.2 million toward affordable housing and park improvements in Mount Pleasant.',
   NOW() - INTERVAL '5 days', true,
   '{"application_number": "RZ-2026-001", "applicant": "Westbank Corp"}'::jsonb),

  ('e2e-doc-003', 'dpb_minutes', 'https://vancouver.ca/dpb/e2e-test-3',
   'Development Permit Board Meeting — December 2025',
   'The Board approved the development permit for 2100 Commercial Drive, a 4-storey residential building with 48 units. Community members raised concerns about shadowing and parking, but the Board found the proposal consistent with the Grandview-Woodland Community Plan. The applicant agreed to additional landscaping requirements along the lane.',
   NOW() - INTERVAL '10 days', true,
   '{"meeting_date": "2025-12-18"}'::jsonb),

  ('e2e-doc-004', 'news', 'https://vancouversun.com/e2e-test-4',
   'Vancouver approves new transit-oriented development near Renfrew Station',
   'The City of Vancouver has given the green light to a major transit-oriented development near Renfrew SkyTrain station. The project will include 500 residential units, a community center, and retail space. The development is part of the broader Transit-Oriented Areas (TOA) framework under Bill 47, which allows increased density within 800 meters of rapid transit stations.',
   NOW() - INTERVAL '1 day', true,
   '{"source": "Vancouver Sun", "author": "Jane Reporter"}'::jsonb),

  ('e2e-doc-005', 'news', 'https://biv.com/e2e-test-5',
   'Mount Pleasant condo prices surge amid rezoning wave',
   'Real estate prices in Mount Pleasant have jumped 12% year-over-year as multiple rezoning applications transform the neighborhood. Developers are betting on the area''s proximity to transit and the Broadway Plan''s allowance for increased density. Analysts note that the pipeline of approved projects could add over 2,000 new units to the area by 2028.',
   NOW() - INTERVAL '2 days', true,
   '{"source": "Business in Vancouver"}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- Seed document chunks (simplified — normally created by chunker)
INSERT INTO document_chunks (id, document_id, chunk_index, content, token_count, metadata)
VALUES
  ('e2e-chunk-001', 'e2e-doc-001', 0,
   'The Council approved the rezoning application for 1234 Main Street from RS-1 to RM-4, allowing construction of a 6-storey mixed-use building with 120 rental units. The vote passed 7-4 with conditions including 20% below-market rental units and ground-floor commercial space.',
   62, '{}'::jsonb),
  ('e2e-chunk-002', 'e2e-doc-001', 1,
   'Council also discussed the Broadway Plan implementation timeline and transit-oriented area density bonuses near SkyTrain stations.',
   22, '{}'::jsonb),
  ('e2e-chunk-003', 'e2e-doc-002', 0,
   'Application to rezone 555 West Broadway from C-3A to CD-1, proposing a 28-storey mixed-use tower with 350 residential units, 15,000 sq ft of commercial space, and underground parking for 200 vehicles.',
   44, '{}'::jsonb),
  ('e2e-chunk-004', 'e2e-doc-003', 0,
   'The Board approved the development permit for 2100 Commercial Drive, a 4-storey residential building with 48 units. Community members raised concerns about shadowing and parking.',
   33, '{}'::jsonb),
  ('e2e-chunk-005', 'e2e-doc-004', 0,
   'The City of Vancouver has given the green light to a major transit-oriented development near Renfrew SkyTrain station. The project will include 500 residential units, a community center, and retail space.',
   38, '{}'::jsonb),
  ('e2e-chunk-006', 'e2e-doc-005', 0,
   'Real estate prices in Mount Pleasant have jumped 12% year-over-year as multiple rezoning applications transform the neighborhood. Developers are betting on the area proximity to transit and the Broadway Plan.',
   40, '{}'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- Seed intelligence signals (geocoded, with addresses)
INSERT INTO intelligence_signals (
  id, document_id, signal_type, severity, title, summary, 
  address, neighborhood, latitude, longitude,
  extracted_at, metadata
)
VALUES
  ('e2e-sig-001', 'e2e-doc-001', 'rezoning_decision', 'high',
   'RS-1 to RM-4 Rezoning Approved — 1234 Main Street',
   'Council approved rezoning from RS-1 to RM-4, enabling a 6-storey mixed-use building with 120 rental units. Vote: 7-4. Conditions include 20% below-market rental.',
   '1234 Main Street', 'Mount Pleasant', 49.2630, -123.1010,
   NOW() - INTERVAL '3 days',
   '{"vote_result": "7-4", "from_zone": "RS-1", "to_zone": "RM-4", "units": 120}'::jsonb),

  ('e2e-sig-002', 'e2e-doc-002', 'density_change', 'critical',
   '28-Storey Tower Proposed — 555 West Broadway',
   'Major rezoning application: C-3A to CD-1 for a 28-storey mixed-use tower with 350 units. Community amenity contribution of $3.2M.',
   '555 West Broadway', 'Mount Pleasant', 49.2634, -123.1143,
   NOW() - INTERVAL '5 days',
   '{"from_zone": "C-3A", "to_zone": "CD-1", "units": 350, "storeys": 28, "cac": 3200000}'::jsonb),

  ('e2e-sig-003', 'e2e-doc-003', 'permit_approval', 'medium',
   'Development Permit Approved — 2100 Commercial Drive',
   'DPB approved 4-storey residential building with 48 units on Commercial Drive. Community concerns about shadowing were addressed.',
   '2100 Commercial Drive', 'Grandview-Woodland', 49.2690, -123.0700,
   NOW() - INTERVAL '10 days',
   '{"units": 48, "storeys": 4}'::jsonb),

  ('e2e-sig-004', 'e2e-doc-004', 'infrastructure_announcement', 'high',
   'TOD Approved Near Renfrew Station — 500 Units',
   'Major transit-oriented development approved near Renfrew SkyTrain station: 500 units, community center, and retail under Bill 47 TOA framework.',
   'Renfrew Station Area', 'Renfrew-Collingwood', 49.2590, -123.0340,
   NOW() - INTERVAL '1 day',
   '{"units": 500, "framework": "Bill 47 TOA"}'::jsonb),

  ('e2e-sig-005', 'e2e-doc-005', 'community_opposition', 'low',
   'Mount Pleasant Condo Prices Surge 12% YoY',
   'Real estate prices surging in Mount Pleasant amid rezoning wave. Over 2,000 new units in development pipeline through 2028.',
   'Mount Pleasant Area', 'Mount Pleasant', 49.2620, -123.1050,
   NOW() - INTERVAL '2 days',
   '{"price_change_pct": 12, "pipeline_units": 2000}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- Verify seed data
DO $$
DECLARE
  doc_count INTEGER;
  chunk_count INTEGER;
  signal_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO doc_count FROM documents WHERE id LIKE 'e2e-%';
  SELECT COUNT(*) INTO chunk_count FROM document_chunks WHERE id LIKE 'e2e-%';
  SELECT COUNT(*) INTO signal_count FROM intelligence_signals WHERE id LIKE 'e2e-%';
  RAISE NOTICE 'E2E seed data: % documents, % chunks, % signals', doc_count, chunk_count, signal_count;
END $$;
