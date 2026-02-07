#!/usr/bin/env bash
set -euo pipefail

echo "Seeding E2E test data..."

# Run against the docker-compose database
docker compose exec -T db psql -U vancity -d vancity_lens -f /docker-entrypoint-initdb.d/008_e2e_seed.sql

echo ""
echo "E2E seed data loaded successfully"
echo ""
echo "Quick check:"
docker compose exec -T db psql -U vancity -d vancity_lens -c "
  SELECT 'documents' as table_name, COUNT(*) as count FROM documents WHERE id LIKE 'e2e-%'
  UNION ALL
  SELECT 'chunks', COUNT(*) FROM document_chunks WHERE id LIKE 'e2e-%'
  UNION ALL
  SELECT 'signals', COUNT(*) FROM intelligence_signals WHERE id LIKE 'e2e-%';
"
