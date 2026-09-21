"""Bulk-load Spark Parquet artefacts into versioned PostGIS serving tables.

The loader uses PostgreSQL COPY into temporary staging tables, validates the
batch, and publishes it by swapping ``current_run``.  A failed load therefore
leaves the previously published run untouched.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


TABLES = ("points", "trajectories", "stay_points", "users", "hotspots", "patterns")


def _dataset(path: Path):
    try:
        import pyarrow.dataset as ds
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("批量加载需要 pyarrow；请在 serving 镜像中安装 pyarrow") from error
    if not path.exists():
        return None
    try:
        return ds.dataset(str(path), format="parquet")
    except Exception:
        return None


def _count(path: Path) -> int:
    dataset = _dataset(path)
    return 0 if dataset is None else int(dataset.count_rows())


def _rows(path: Path, columns: list[str] | None = None) -> Iterator[dict[str, Any]]:
    dataset = _dataset(path)
    if dataset is None:
        return
    for batch in dataset.scanner(columns=columns, batch_size=8192).to_batches():
        yield from batch.to_pylist()


def _json_quality(root: Path) -> dict[str, Any]:
    quality_dir = root / "quality"
    candidates = [quality_dir] if quality_dir.is_file() else sorted(quality_dir.glob("**/*")) if quality_dir.exists() else []
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix not in {".crc", "._SUCCESS"}:
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("{"):
                        return json.loads(line)
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def inspect(root: Path) -> dict[str, Any]:
    counts = {
        "trajectory_points": _count(root / "points"),
        "trajectories": _count(root / "trajectories"),
        "stay_points": _count(root / "stay_points"),
        "users": _count(root / "users"),
        "hotspots": _count(root / "hotspots"),
        "temporal_patterns": _count(root / "patterns"),
    }
    return {"output_root": str(root), "counts": counts, "quality": _json_quality(root)}


def _copy(cur, sql: str, rows: Iterable[tuple[Any, ...]]) -> int:
    count = 0
    with cur.copy(sql) as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def load(root: Path, dsn: str, run_id: str | None = None, manifest_uri: str | None = None) -> dict[str, Any]:
    info = inspect(root)
    counts = info["counts"]
    if counts["trajectory_points"] == 0 or counts["trajectories"] == 0:
        raise ValueError("Parquet 产物缺少 points 或 trajectories，拒绝发布空批次")
    run_id = run_id or f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    try:
        import psycopg
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("写入数据库需要 psycopg；检查载荷请使用 --dry-run") from error

    try:
        with psycopg.connect(dsn) as connection:
            with connection.transaction():
                with connection.cursor() as cur:
                    cur.execute(
                        """INSERT INTO batch_runs(run_id,dataset,source,status,manifest_uri,counts,quality)
                           VALUES (%s,%s,%s,'staging',%s,%s::jsonb,%s::jsonb)
                           ON CONFLICT (run_id) DO UPDATE SET status='staging', started_at=now(),
                             finished_at=NULL, manifest_uri=EXCLUDED.manifest_uri,
                             counts=EXCLUDED.counts, quality=EXCLUDED.quality, error_message=NULL""",
                        (run_id, "GeoLife Trajectories 1.3", "spark-parquet", manifest_uri,
                         json.dumps(counts), json.dumps(info["quality"])),
                    )
                    cur.execute("CREATE TEMP TABLE stg_trajectories (run_id text, trajectory_id text, user_id text, start_ts timestamptz, end_ts timestamptz, point_count integer, distance_m double precision, duration_s double precision, geom_wkt text) ON COMMIT DROP")
                    cur.execute("CREATE TEMP TABLE stg_points (run_id text, user_id text, trajectory_id text, seq integer, ts timestamptz, latitude double precision, longitude double precision, altitude_m double precision) ON COMMIT DROP")
                    cur.execute("CREATE TEMP TABLE stg_stays (run_id text, user_id text, trajectory_id text, start_ts timestamptz, end_ts timestamptz, duration_s double precision, latitude double precision, longitude double precision, radius_m double precision) ON COMMIT DROP")
                    cur.execute("CREATE TEMP TABLE stg_users (run_id text, user_id text, trajectory_count integer, point_count bigint, distance_m double precision) ON COMMIT DROP")
                    cur.execute("CREATE TEMP TABLE stg_hotspots (run_id text, hotspot_id text, latitude double precision, longitude double precision, radius_m double precision, visit_count integer, unique_users integer, avg_dwell_s double precision, peak_hour smallint, weekday_ratio double precision, algorithm text) ON COMMIT DROP")
                    cur.execute("CREATE TEMP TABLE stg_patterns (run_id text, pattern_id text, cluster_id integer, label text, user_count integer, avg_trip_count double precision, avg_distance_m double precision, avg_duration_s double precision, hourly_profile jsonb, weekday_ratio double precision) ON COMMIT DROP")

                    _copy(cur, "COPY stg_trajectories FROM STDIN", ((run_id, row["trajectory_id"], row["user_id"], row["start_ts"], row["end_ts"], row["point_count"], row["distance_m"], row["duration_s"], row.get("geom_wkt", "LINESTRING EMPTY")) for row in _rows(root / "trajectories")))
                    _copy(cur, "COPY stg_points FROM STDIN", ((run_id, row["user_id"], row["trajectory_id"], row["seq"], row["ts"], row["latitude"], row["longitude"], row.get("altitude_m")) for row in _rows(root / "points")))
                    _copy(cur, "COPY stg_stays FROM STDIN", ((run_id, row["user_id"], row["trajectory_id"], row["start_ts"], row["end_ts"], row["duration_s"], row["latitude"], row["longitude"], row["radius_m"]) for row in _rows(root / "stay_points")))
                    _copy(cur, "COPY stg_users FROM STDIN", ((run_id, row["user_id"], row["trajectory_count"], row["point_count"], row["distance_m"]) for row in _rows(root / "users")))
                    _copy(cur, "COPY stg_hotspots FROM STDIN", ((run_id, row["hotspot_id"], row["latitude"], row["longitude"], row["radius_m"], row["visit_count"], row["unique_users"], row["avg_dwell_s"], row["peak_hour"], row["weekday_ratio"], row["algorithm"]) for row in _rows(root / "hotspots")))
                    _copy(cur, "COPY stg_patterns FROM STDIN", ((run_id, row["pattern_id"], row["cluster_id"], row["label"], row["user_count"], row["avg_trip_count"], row["avg_distance_m"], row["avg_duration_s"], json.dumps(row.get("hourly_profile", row.get("profiles", []))), row["weekday_ratio"]) for row in _rows(root / "patterns")))

                    cur.execute("SELECT COUNT(*) FROM stg_points")
                    loaded_points = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM stg_trajectories")
                    loaded_trajectories = cur.fetchone()[0]
                    if loaded_points != counts["trajectory_points"] or loaded_trajectories != counts["trajectories"]:
                        raise RuntimeError("COPY 行数校验失败，批次不会发布")

                    cur.execute("""INSERT INTO trajectories(run_id,trajectory_id,user_id,start_ts,end_ts,point_count,distance_m,duration_s,geom)
                      SELECT run_id,trajectory_id,user_id,start_ts,end_ts,point_count,distance_m,duration_s,ST_GeomFromText(geom_wkt,4326) FROM stg_trajectories
                      ON CONFLICT (trajectory_id) DO UPDATE SET run_id=EXCLUDED.run_id,user_id=EXCLUDED.user_id,start_ts=EXCLUDED.start_ts,end_ts=EXCLUDED.end_ts,point_count=EXCLUDED.point_count,distance_m=EXCLUDED.distance_m,duration_s=EXCLUDED.duration_s,geom=EXCLUDED.geom""")
                    cur.execute("DELETE FROM trajectory_points p USING stg_trajectories t WHERE p.trajectory_id=t.trajectory_id")
                    cur.execute("""INSERT INTO trajectory_points(run_id,user_id,trajectory_id,seq,ts,latitude,longitude,altitude_m)
                      SELECT run_id,user_id,trajectory_id,seq,ts,latitude,longitude,altitude_m FROM stg_points""")
                    # MobilityDB: build one tgeompoint per trajectory (time-aware queries).
                    cur.execute("""UPDATE trajectories t SET temporal_geom = tt.g
                      FROM (SELECT p.trajectory_id,
                                   tgeompointseq(ARRAY_AGG(tgeompoint(ST_SetSRID(ST_MakePoint(p.longitude,p.latitude),4326), p.ts) ORDER BY p.seq),'linear') AS g
                            FROM trajectory_points p WHERE p.run_id=%s GROUP BY p.trajectory_id) tt
                      WHERE t.trajectory_id=tt.trajectory_id AND t.run_id=%s""", (run_id, run_id))
                    cur.execute("DELETE FROM stay_points s USING stg_trajectories t WHERE s.trajectory_id=t.trajectory_id")
                    cur.execute("""INSERT INTO stay_points(run_id,user_id,trajectory_id,start_ts,end_ts,duration_s,center_geom,radius_m)
                      SELECT run_id,user_id,trajectory_id,start_ts,end_ts,duration_s,ST_SetSRID(ST_MakePoint(longitude,latitude),4326),radius_m FROM stg_stays""")
                    cur.execute("""INSERT INTO users(run_id,user_id,trajectory_count,point_count,distance_m)
                      SELECT run_id,user_id,trajectory_count,point_count,distance_m FROM stg_users
                      ON CONFLICT (run_id,user_id) DO UPDATE SET trajectory_count=EXCLUDED.trajectory_count,point_count=EXCLUDED.point_count,distance_m=EXCLUDED.distance_m""")
                    cur.execute("""INSERT INTO hotspots(hotspot_id,center_geom,geometry,visit_count,unique_users,avg_dwell_s,peak_hour,weekday_ratio,algorithm,run_id)
                      SELECT hotspot_id,ST_SetSRID(ST_MakePoint(longitude,latitude),4326),ST_Buffer(ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography,radius_m)::geometry,visit_count,unique_users,avg_dwell_s,peak_hour,weekday_ratio,algorithm,run_id FROM stg_hotspots
                      ON CONFLICT (hotspot_id) DO UPDATE SET center_geom=EXCLUDED.center_geom,geometry=EXCLUDED.geometry,visit_count=EXCLUDED.visit_count,unique_users=EXCLUDED.unique_users,avg_dwell_s=EXCLUDED.avg_dwell_s,peak_hour=EXCLUDED.peak_hour,weekday_ratio=EXCLUDED.weekday_ratio,algorithm=EXCLUDED.algorithm,run_id=EXCLUDED.run_id""")
                    cur.execute("""INSERT INTO temporal_patterns(pattern_id,cluster_id,label,user_count,avg_trip_count,avg_distance_m,avg_duration_s,hourly_profile,weekday_ratio,run_id)
                      SELECT pattern_id,cluster_id,label,user_count,avg_trip_count,avg_distance_m,avg_duration_s,hourly_profile,weekday_ratio,run_id FROM stg_patterns
                      ON CONFLICT (pattern_id) DO UPDATE SET cluster_id=EXCLUDED.cluster_id,label=EXCLUDED.label,user_count=EXCLUDED.user_count,avg_trip_count=EXCLUDED.avg_trip_count,avg_distance_m=EXCLUDED.avg_distance_m,avg_duration_s=EXCLUDED.avg_duration_s,hourly_profile=EXCLUDED.hourly_profile,weekday_ratio=EXCLUDED.weekday_ratio,run_id=EXCLUDED.run_id""")
                    cur.execute("UPDATE batch_runs SET status='validated', finished_at=now() WHERE run_id=%s", (run_id,))
                    cur.execute("""INSERT INTO current_run(singleton,run_id,published_at) VALUES (TRUE,%s,now())
                      ON CONFLICT (singleton) DO UPDATE SET run_id=EXCLUDED.run_id,published_at=EXCLUDED.published_at""", (run_id,))
                    cur.execute("UPDATE batch_runs SET status='published', finished_at=now() WHERE run_id=%s", (run_id,))
    except Exception as error:
        # Best-effort audit record. The original transaction is already
        # rolled back, so current_run remains pointed at the previous batch.
        try:
            with psycopg.connect(dsn) as audit_connection:
                audit_connection.execute(
                    "UPDATE batch_runs SET status='failed', finished_at=now(), error_message=%s WHERE run_id=%s",
                    (str(error)[:4000], run_id),
                )
                audit_connection.commit()
        except Exception:
            pass
        raise
    return {"run_id": run_id, **counts, "status": "published"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk-load full Spark Parquet artefacts into PostGIS")
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--dsn", default="postgresql://geotrack:geotrack@localhost:5432/geotrack")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--manifest-uri", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = inspect(args.input_root) if args.dry_run else load(args.input_root, args.dsn, args.run_id, args.manifest_uri)
    print(json.dumps(result, ensure_ascii=False))
