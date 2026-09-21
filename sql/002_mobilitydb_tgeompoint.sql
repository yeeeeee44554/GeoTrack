-- MobilityDB: populate the temporal_geom (tgeompoint) column from trajectory_points.
-- One tgeompoint per trajectory (linear interpolation between consecutive points),
-- enabling time-aware queries such as valueAtTimestamp() and atTime().
-- Points that share a timestamp are de-duplicated first, because MobilityDB
-- requires strictly increasing timestamps within a temporal sequence.
-- Idempotent: only fills rows whose temporal_geom is still NULL.
UPDATE trajectories t
SET temporal_geom = tt.g
FROM (
  SELECT trajectory_id,
         tgeompointseq(
           ARRAY_AGG(
             tgeompoint(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326), ts)
             ORDER BY ts
           ),
           'linear'
         ) AS g
  FROM (
    SELECT DISTINCT ON (trajectory_id, ts) trajectory_id, ts, longitude, latitude
    FROM trajectory_points
    ORDER BY trajectory_id, ts, seq
  ) d
  GROUP BY trajectory_id
) tt
WHERE t.trajectory_id = tt.trajectory_id
  AND t.temporal_geom IS NULL;
