-- Chapter 08: the driver position index.
CREATE EXTENSION IF NOT EXISTS h3;      -- h3-pg: H3 functions in Postgres
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS driver_locations (
    driver_id    uuid PRIMARY KEY,
    city_id      text        NOT NULL,
    cell_r9      bigint      NOT NULL,
    cell_r7      bigint      NOT NULL,
    position     geography(Point, 4326) NOT NULL,
    available    boolean     NOT NULL DEFAULT true,
    vehicle_type text        NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Equality on cell, then a cheap filter. This is the matching index.
CREATE INDEX IF NOT EXISTS driver_cell_r9_idx
    ON driver_locations (cell_r9) WHERE available;

-- Zone-level counting for surge and supply/demand dashboards.
CREATE INDEX IF NOT EXISTS driver_cell_r7_idx
    ON driver_locations (cell_r7);

-- True radius queries, when you genuinely need them.
CREATE INDEX IF NOT EXISTS driver_position_idx
    ON driver_locations USING gist (position);

-- Keep the cell columns in sync with the position in ONE statement, or you
-- create drivers who can never be matched.
CREATE OR REPLACE FUNCTION upsert_driver_location(
    p_driver uuid, p_city text, p_lat float8, p_lng float8,
    p_vehicle text, p_available boolean
) RETURNS void AS $$
DECLARE
    pt point := ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::point;
BEGIN
    INSERT INTO driver_locations
        (driver_id, city_id, cell_r9, cell_r7, position, vehicle_type, available, updated_at)
    VALUES (
        p_driver, p_city,
        h3_lat_lng_to_cell(pt, 9),
        h3_lat_lng_to_cell(pt, 7),
        ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::geography,
        p_vehicle, p_available, now()
    )
    ON CONFLICT (driver_id) DO UPDATE SET
        city_id = EXCLUDED.city_id,
        cell_r9 = EXCLUDED.cell_r9,
        cell_r7 = EXCLUDED.cell_r7,
        position = EXCLUDED.position,
        available = EXCLUDED.available,
        updated_at = now();
END;
$$ LANGUAGE plpgsql;
