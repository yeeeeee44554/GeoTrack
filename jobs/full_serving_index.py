"""Build a disk-backed, browser-safe serving index for the complete GeoLife set.

The raw PLT files remain the source of truth.  This job reads one trajectory at
a time and writes SQLite summaries plus a bounded sample of points per
trajectory.  The resulting file is intentionally a local/generated artifact:
it is ignored by Git and can be rebuilt after a new ingest.  HDFS + Spark is
still the primary course architecture; this index is the reproducible local
serving fallback and is also useful for a classroom demo without Docker.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

try:
    from .geotrack_core import EARTH_RADIUS_M, extract_stay_points, haversine_m, parse_plt
    from .geotrack_core import build_patterns
except ImportError:  # pragma: no cover - script execution path
    from geotrack_core import EARTH_RADIUS_M, extract_stay_points, haversine_m, parse_plt
    from geotrack_core import build_patterns


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY, trajectory_count INTEGER NOT NULL,
  point_count INTEGER NOT NULL, distance_m REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS trajectories (
  trajectory_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
  start_ts TEXT NOT NULL, end_ts TEXT NOT NULL, point_count INTEGER NOT NULL,
  distance_m REAL NOT NULL, duration_s REAL NOT NULL, geometry_json TEXT NOT NULL,
  sample_stride INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_full_trajectories_user_time
  ON trajectories(user_id, start_ts, end_ts);
CREATE TABLE IF NOT EXISTS trajectory_points (
  trajectory_id TEXT NOT NULL, seq INTEGER NOT NULL, ts TEXT NOT NULL,
  latitude REAL NOT NULL, longitude REAL NOT NULL, altitude_m REAL,
  PRIMARY KEY (trajectory_id, seq)
);
CREATE TABLE IF NOT EXISTS stay_points (
  stay_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
  trajectory_id TEXT NOT NULL, start_ts TEXT NOT NULL, end_ts TEXT NOT NULL,
  duration_s REAL NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
  radius_m REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_full_stays_user_time
  ON stay_points(user_id, start_ts, end_ts);
CREATE TABLE IF NOT EXISTS hotspots (
  hotspot_id TEXT PRIMARY KEY, center_json TEXT NOT NULL, geometry_json TEXT NOT NULL,
  radius_m REAL NOT NULL, visit_count INTEGER NOT NULL, unique_users INTEGER NOT NULL,
  avg_dwell_s REAL NOT NULL, peak_hour INTEGER NOT NULL, weekday_ratio REAL NOT NULL,
  algorithm TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patterns (
  pattern_id TEXT PRIMARY KEY, cluster_id INTEGER NOT NULL, label TEXT NOT NULL,
  user_count INTEGER NOT NULL, avg_trip_count REAL NOT NULL,
  avg_distance_m REAL NOT NULL, avg_duration_s REAL NOT NULL,
  hourly_profile_json TEXT NOT NULL, weekday_ratio REAL NOT NULL
);
"""


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sample_indices(size: int, maximum: int) -> list[int]:
    if size <= maximum:
        return list(range(size))
    # Pick evenly spaced, unique indices and always retain the final point.
    # The previous stride/truncate implementation could already contain the
    # final index, then append it a second time (e.g. size=5, maximum=4),
    # violating the trajectory_points primary key during a full build.
    denominator = max(1, maximum - 1)
    return [(position * (size - 1)) // denominator for position in range(maximum)]


def _clean_points(path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    points: list[dict[str, Any]] = []
    quality = {"raw_rows": 0, "invalid_points": 0, "duplicate_points": 0, "time_gap_segments": 0}
    previous: dict[str, Any] | None = None
    # parse_plt already applies the documented header/coordinate/time/altitude
    # rules. Raw row count is recovered from the file for the quality report.
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        quality["raw_rows"] = max(0, sum(1 for _ in handle) - 6)
    for point in parse_plt(path):
        if previous and point["timestamp"] == previous["timestamp"] and point["latitude"] == previous["latitude"] and point["longitude"] == previous["longitude"]:
            quality["duplicate_points"] += 1
            continue
        if previous and (point["timestamp"] - previous["timestamp"]).total_seconds() > 30 * 60:
            quality["time_gap_segments"] += 1
        points.append(point)
        previous = point
    quality["invalid_points"] = max(0, quality["raw_rows"] - len(points) - quality["duplicate_points"])
    return points, quality


def _grid_dbscan(stays: list[dict[str, Any]], eps_m: float = 500.0, min_pts: int = 30) -> list[list[int]]:
    """DBSCAN with a spatial grid to avoid the O(n²) full pair scan."""
    if not stays:
        return []
    lat_step = eps_m / 111_195.0
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(stays):
        grid[(math.floor(row["latitude"] / lat_step), math.floor(row["longitude"] / lat_step))].append(index)

    def neighbors(index: int) -> list[int]:
        row = stays[index]
        cell = (math.floor(row["latitude"] / lat_step), math.floor(row["longitude"] / lat_step))
        result: list[int] = []
        for lat_cell in range(cell[0] - 1, cell[0] + 2):
            for lon_cell in range(cell[1] - 1, cell[1] + 2):
                for candidate in grid.get((lat_cell, lon_cell), []):
                    other = stays[candidate]
                    if haversine_m(row["latitude"], row["longitude"], other["latitude"], other["longitude"]) <= eps_m:
                        result.append(candidate)
        return result

    visited: set[int] = set()
    assigned: set[int] = set()
    clusters: list[list[int]] = []
    for index in range(len(stays)):
        if index in visited:
            continue
        visited.add(index)
        seed = neighbors(index)
        if len(seed) < min_pts:
            continue
        cluster: list[int] = []
        queue = list(seed)
        while queue:
            current = queue.pop()
            if current not in visited:
                visited.add(current)
                current_neighbors = neighbors(current)
                if len(current_neighbors) >= min_pts:
                    queue.extend(item for item in current_neighbors if item not in queue)
            if current not in assigned:
                assigned.add(current)
                cluster.append(current)
        clusters.append(cluster)
    return clusters


def _build_hotspots(stays: list[dict[str, Any]], eps_m: float, min_pts: int) -> list[dict[str, Any]]:
    hotspots: list[dict[str, Any]] = []
    for cluster_index, indexes in enumerate(_grid_dbscan(stays, eps_m, min_pts), start=1):
        rows = [stays[index] for index in indexes]
        lat = mean(row["latitude"] for row in rows)
        lon = mean(row["longitude"] for row in rows)
        radius = max(haversine_m(lat, lon, row["latitude"], row["longitude"]) for row in rows)
        hours = Counter(datetime.fromisoformat(row["start_ts"].replace("Z", "+00:00")).hour for row in rows)
        weekday = [datetime.fromisoformat(row["start_ts"].replace("Z", "+00:00")).weekday() < 5 for row in rows]
        hotspots.append({
            "hotspot_id": f"FHS-{cluster_index:03d}",
            "center": {"latitude": round(lat, 6), "longitude": round(lon, 6)},
            "radius_m": round(max(radius, eps_m / 2), 1),
            "visit_count": len(rows), "unique_users": len({row["user_id"] for row in rows}),
            "avg_dwell_s": round(mean(row["duration_s"] for row in rows), 1),
            "peak_hour": hours.most_common(1)[0][0],
            "weekday_ratio": round(sum(weekday) / max(1, len(weekday)), 3),
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "algorithm": "dbscan-grid",
        })
    return sorted(hotspots, key=lambda row: row["visit_count"], reverse=True)


def build_index(data_root: Path, output: Path, sample_points: int = 200, eps_m: float = 500.0, min_pts: int = 3) -> dict[str, Any]:
    if sample_points < 1:
        raise ValueError("sample_points must be at least 1")
    if eps_m <= 0:
        raise ValueError("eps_m must be positive")
    if min_pts < 1:
        raise ValueError("min_pts must be at least 1")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    connection = sqlite3.connect(output)
    connection.executescript(SCHEMA)
    trajectories: list[dict[str, Any]] = []
    stays: list[dict[str, Any]] = []
    users: dict[str, dict[str, Any]] = {}
    quality = {"raw_rows": 0, "valid_points": 0, "invalid_points": 0, "duplicate_points": 0, "time_gap_segments": 0}
    files = sorted(data_root.glob("*/Trajectory/*.plt"))
    if not files:
        connection.close()
        raise FileNotFoundError(f"未找到 PLT 文件: {data_root}")
    for file_index, path in enumerate(files, start=1):
        user_id = path.parent.parent.name
        trajectory_id = f"{user_id}_{path.stem}"
        points, file_quality = _clean_points(path)
        for key, value in file_quality.items():
            quality[key] += value
        if not points:
            continue
        for key in ("valid_points",):
            quality[key] += len(points)
        sample_indexes = _sample_indices(len(points), sample_points)
        sample = [points[index] for index in sample_indexes]
        distance_m = sum(haversine_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"]) for a, b in zip(points, points[1:]))
        start_ts, end_ts = points[0]["timestamp"], points[-1]["timestamp"]
        geometry = {"type": "LineString", "coordinates": [[round(row["longitude"], 6), round(row["latitude"], 6)] for row in sample]}
        trajectory = {
            "trajectory_id": trajectory_id, "user_id": user_id, "start_ts": _iso(start_ts), "end_ts": _iso(end_ts),
            "point_count": len(points), "distance_m": round(distance_m, 2),
            "duration_s": round(max(0.0, (end_ts - start_ts).total_seconds()), 1),
            "geometry": geometry, "points": [], "sample_stride": max(1, math.ceil(len(points) / max(1, len(sample)))),
        }
        trajectories.append(trajectory)
        user = users.setdefault(user_id, {"user_id": user_id, "trajectory_count": 0, "point_count": 0, "distance_m": 0.0})
        user["trajectory_count"] += 1; user["point_count"] += len(points); user["distance_m"] += distance_m
        for stay in extract_stay_points([{**row, "user_id": user_id, "trajectory_id": trajectory_id} for row in points]):
            stays.append(stay)
        connection.execute("INSERT INTO trajectories VALUES (?,?,?,?,?,?,?,?,?)", (trajectory_id, user_id, trajectory["start_ts"], trajectory["end_ts"], trajectory["point_count"], trajectory["distance_m"], trajectory["duration_s"], json.dumps(geometry, ensure_ascii=False), trajectory["sample_stride"]))
        connection.executemany("INSERT INTO trajectory_points VALUES (?,?,?,?,?,?)", [(trajectory_id, index, _iso(row["timestamp"]), row["latitude"], row["longitude"], row.get("altitude_m")) for index, row in zip(sample_indexes, sample)])
        if file_index % 500 == 0:
            connection.commit()
            print(f"[full-index] processed {file_index}/{len(files)} PLT files")
    connection.executemany("INSERT INTO users VALUES (?,?,?,?)", [(user_id, row["trajectory_count"], row["point_count"], round(row["distance_m"], 2)) for user_id, row in users.items()])
    connection.executemany("INSERT INTO stay_points(user_id,trajectory_id,start_ts,end_ts,duration_s,latitude,longitude,radius_m) VALUES (?,?,?,?,?,?,?,?)", [(row["user_id"], row["trajectory_id"], row["start_ts"], row["end_ts"], row["duration_s"], row["latitude"], row["longitude"], row["radius_m"]) for row in stays])
    hotspots = _build_hotspots(stays, eps_m, min_pts)
    connection.executemany("INSERT INTO hotspots VALUES (?,?,?,?,?,?,?,?,?,?)", [(row["hotspot_id"], json.dumps(row["center"]), json.dumps(row["geometry"]), row["radius_m"], row["visit_count"], row["unique_users"], row["avg_dwell_s"], row["peak_hour"], row["weekday_ratio"], row["algorithm"]) for row in hotspots])
    patterns = build_patterns(trajectories, k=3)
    connection.executemany("INSERT INTO patterns VALUES (?,?,?,?,?,?,?,?,?)", [(row["pattern_id"], row["cluster_id"], row["label"], row["user_count"], row["avg_trip_count"], row["avg_distance_m"], row["avg_duration_s"], json.dumps(row["hourly_profile"]), row["weekday_ratio"]) for row in patterns])
    starts = [row["start_ts"] for row in trajectories]; ends = [row["end_ts"] for row in trajectories]
    summary = {
        "dataset": "GeoLife Trajectories 1.3", "source": "Microsoft Research Asia (non-commercial academic use)",
        "scope": "full-index", "processing_mode": "local-full-serving-index", "user_count": len(users),
        "trajectory_count": len(trajectories), "point_count": quality["valid_points"], "raw_point_count": quality["raw_rows"],
        "total_distance_km": round(sum(row["distance_m"] for row in trajectories) / 1000, 1),
        "time_range": {"start": min(starts) if starts else None, "end": max(ends) if ends else None},
        "demo_scope": "前端只按页加载轨迹摘要，每条详情返回最多采样点",
    }
    manifest = {"summary": summary, "quality": {**quality, "trajectory_count": len(trajectories), "stay_point_count": len(stays), "hotspot_count": len(hotspots), "pattern_count": len(patterns)}, "parameters": {"sample_points": sample_points, "eps_m": eps_m, "min_pts": min_pts}, "generated_at": datetime.now(timezone.utc).isoformat()}
    connection.executemany("INSERT INTO metadata VALUES (?,?)", [("summary", json.dumps(summary, ensure_ascii=False)), ("quality", json.dumps(manifest["quality"], ensure_ascii=False)), ("manifest", json.dumps(manifest, ensure_ascii=False))])
    connection.commit(); connection.close()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a full GeoLife SQLite serving index")
    parser.add_argument("--data-root", type=Path, default=Path("Geolife Trajectories 1.3/Data"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/full-serving.sqlite"))
    parser.add_argument("--sample-points", type=int, default=200)
    parser.add_argument("--eps", type=float, default=500.0)
    parser.add_argument("--min-pts", type=int, default=3)
    args = parser.parse_args()
    result = build_index(args.data_root, args.output, args.sample_points, args.eps, args.min_pts)
    print(json.dumps({"output": str(args.output), **result["summary"], "quality": result["quality"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
