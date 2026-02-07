-- Migration: Add rew_url column to parcels table
-- Stores the direct REW.ca listing URL for price verification links
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS rew_url TEXT;
