-- Migration 043: Add assessed_year column to parcels table
-- Tracks the BC Assessment roll year for staleness warnings (DV-F01-006).

ALTER TABLE parcels ADD COLUMN IF NOT EXISTS assessed_year INTEGER;

-- Default existing rows to 2024 (seed data from 2024 assessment roll)
UPDATE parcels SET assessed_year = 2024 WHERE assessed_year IS NULL;
