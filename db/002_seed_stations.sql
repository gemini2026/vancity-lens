-- ============================================================
-- VanCity Lens — Seed Data: Vancouver Transit Stations
-- Real coordinates from TransLink / OpenStreetMap
-- ============================================================

-- Expo Line (within City of Vancouver)
INSERT INTO transit_stations (name, line, type, geom) VALUES
    ('Waterfront',              'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.1116, 49.2856), 4326)),
    ('Burrard',                 'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.1226, 49.2856), 4326)),
    ('Granville',               'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.1162, 49.2831), 4326)),
    ('Stadium-Chinatown',       'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.1089, 49.2793), 4326)),
    ('Main Street-Science World','expo',      'skytrain', ST_SetSRID(ST_MakePoint(-123.1005, 49.2733), 4326)),
    ('Commercial-Broadway',     'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.0694, 49.2627), 4326)),
    ('Nanaimo',                 'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.0559, 49.2484), 4326)),
    ('29th Avenue',             'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.0462, 49.2443), 4326)),
    ('Joyce-Collingwood',       'expo',       'skytrain', ST_SetSRID(ST_MakePoint(-123.0318, 49.2384), 4326));

-- Canada Line
INSERT INTO transit_stations (name, line, type, geom) VALUES
    ('Vancouver City Centre',   'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1189, 49.2829), 4326)),
    ('Yaletown-Roundhouse',     'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1218, 49.2743), 4326)),
    ('Olympic Village',         'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1174, 49.2664), 4326)),
    ('Broadway-City Hall',      'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1148, 49.2632), 4326)),
    ('King Edward',             'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1159, 49.2490), 4326)),
    ('Oakridge-41st',           'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1167, 49.2333), 4326)),
    ('Langara-49th',            'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1162, 49.2264), 4326)),
    ('Marine Drive',            'canada',     'skytrain', ST_SetSRID(ST_MakePoint(-123.1161, 49.2098), 4326));

-- Millennium Line (Broadway Extension)
INSERT INTO transit_stations (name, line, type, geom) VALUES
    ('Great Northern Way-Emily Carr', 'millennium', 'skytrain', ST_SetSRID(ST_MakePoint(-123.0858, 49.2668), 4326)),
    ('Mount Pleasant',          'millennium', 'skytrain', ST_SetSRID(ST_MakePoint(-123.0978, 49.2649), 4326)),
    ('South Granville',         'millennium', 'skytrain', ST_SetSRID(ST_MakePoint(-123.1330, 49.2632), 4326)),
    ('Arbutus',                 'millennium', 'skytrain', ST_SetSRID(ST_MakePoint(-123.1530, 49.2632), 4326));

-- Bus Exchanges
INSERT INTO transit_stations (name, line, type, geom) VALUES
    ('Dunbar Loop',             'bus',        'bus_exchange', ST_SetSRID(ST_MakePoint(-123.1862, 49.2350), 4326)),
    ('Kootenay Loop',           'bus',        'bus_exchange', ST_SetSRID(ST_MakePoint(-123.0383, 49.2756), 4326));

-- Refresh the materialized view
REFRESH MATERIALIZED VIEW toa_buffers;

-- ============================================================
-- Demo Parcels for POC
-- ============================================================

-- Demo Parcel 1: ~150m from Broadway-City Hall (Tier 1, Red Dot)
INSERT INTO parcels (pid, civic_address, current_zoning, current_fsr, current_height,
                     lot_area_sqm, assessed_value, asking_price, geo_local_area, geom) VALUES
    (
        '009-123-456',
        '163 W 8th Ave, Vancouver',
        'RS-1',
        0.60,
        2,
        557.4,
        1890000,
        2195000,
        'Mount Pleasant',
        ST_SetSRID(ST_GeomFromText(
            'POLYGON((-123.1168 49.2638, -123.1163 49.2638,
                      -123.1163 49.2634, -123.1168 49.2634,
                      -123.1168 49.2638))'
        ), 4326)
    );

-- Demo Parcel 2: ~350m from station (Tier 2)
INSERT INTO parcels (pid, civic_address, current_zoning, current_fsr, current_height,
                     lot_area_sqm, assessed_value, asking_price, geo_local_area, geom) VALUES
    (
        '010-456-789',
        '2875 Yukon St, Vancouver',
        'RS-1',
        0.60,
        2,
        502.0,
        1650000,
        1850000,
        'Mount Pleasant',
        ST_SetSRID(ST_GeomFromText(
            'POLYGON((-123.1120 49.2610, -123.1115 49.2610,
                      -123.1115 49.2606, -123.1120 49.2606,
                      -123.1120 49.2610))'
        ), 4326)
    );

-- Demo Parcel 3: outside all TOA zones (control case)
INSERT INTO parcels (pid, civic_address, current_zoning, current_fsr, current_height,
                     lot_area_sqm, assessed_value, asking_price, geo_local_area, geom) VALUES
    (
        '011-789-012',
        '4567 W 33rd Ave, Vancouver',
        'RS-1',
        0.60,
        2,
        610.0,
        1980000,
        NULL,
        'Dunbar-Southlands',
        ST_SetSRID(ST_GeomFromText(
            'POLYGON((-123.1800 49.2420, -123.1795 49.2420,
                      -123.1795 49.2416, -123.1800 49.2416,
                      -123.1800 49.2420))'
        ), 4326)
    );
