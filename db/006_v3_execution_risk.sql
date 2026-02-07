-- V3: Business licences for tenant displacement + execution risk scoring
-- Source: Vancouver Open Data "business-licences" dataset

CREATE TABLE IF NOT EXISTS business_licences (
    id SERIAL PRIMARY KEY,
    licence_number TEXT,
    business_name TEXT,
    business_type TEXT,          -- e.g. "Gasoline Station", "Dry Cleaning Plant", "Auto Repair"
    status TEXT,                 -- "Issued", "Inactive", etc.
    issue_date DATE,
    expiry_date DATE,
    address TEXT,
    local_area TEXT,
    number_of_employees INT,
    geom GEOMETRY(Point, 4326)
);

CREATE INDEX IF NOT EXISTS idx_business_licences_geom ON business_licences USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_business_licences_status ON business_licences (status);
CREATE INDEX IF NOT EXISTS idx_business_licences_type ON business_licences (business_type);

-- Add permit elapsed days to existing permits table (for timeline estimation)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'issued_building_permits' AND column_name = 'permit_elapsed_days'
    ) THEN
        ALTER TABLE issued_building_permits ADD COLUMN permit_elapsed_days INT;
    END IF;
END $$;
