-- Chapter 08: the matching query.
-- $1 lat, $2 lng, $3 city_id, $4 limit, $5 k (ring size)
WITH rider AS (
  SELECT h3_lat_lng_to_cell(
           ST_SetSRID(ST_MakePoint($2, $1), 4326)::point, 9) AS cell
),
ring AS (
  SELECT h3_grid_disk(r.cell, $5) AS cells FROM rider r
)
SELECT d.driver_id,
       d.vehicle_type,
       ST_Distance(d.position,
                   ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) AS meters,
       d.cell_r9
FROM driver_locations d
JOIN ring ON d.cell_r9 = ANY(ring.cells)
WHERE d.city_id = $3
  AND d.available
  AND d.updated_at > now() - interval '2 minutes'   -- no ghost drivers
ORDER BY meters ASC
LIMIT $4;
