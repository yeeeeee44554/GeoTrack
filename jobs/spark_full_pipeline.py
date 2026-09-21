"""Spark job for the complete GeoLife serving contract.

The job keeps point-level data distributed in Parquet and materialises only
small aggregate tables (trajectory summaries, stays, hotspots and user
patterns).  It is intentionally separate from ``spark_distributed.py`` so
the demo pipeline can remain lightweight and deterministic on a laptop.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath


def _parse_file(item: tuple[str, str]):
    path, content = item
    parts = PurePosixPath(path.split("?", 1)[0]).parts
    try:
        index = next(i for i, part in enumerate(parts) if part == "Trajectory")
        user_id = parts[index - 1]
    except (StopIteration, IndexError):
        user_id = "unknown"
    trajectory_id = f"{user_id}_{PurePosixPath(path).stem}"
    reader = csv.reader(io.StringIO(content))
    for _ in range(6):
        next(reader, None)
    previous = None
    seq = 0
    for row in reader:
        if len(row) < 7:
            continue
        try:
            latitude, longitude = float(row[0]), float(row[1])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            timestamp = datetime.strptime(f"{row[5]} {row[6]}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            altitude_ft = float(row[3])
            altitude_m = None if altitude_ft <= -777 else round(altitude_ft * 0.3048, 2)
        except (TypeError, ValueError):
            continue
        key = (timestamp, latitude, longitude)
        if key == previous:
            continue
        previous = key
        yield {"user_id": user_id, "trajectory_id": trajectory_id, "seq": seq, "timestamp": timestamp.isoformat().replace("+00:00", "Z"), "latitude": latitude, "longitude": longitude, "altitude_m": altitude_m}
        seq += 1


def _trajectory_summary(pdf):
    import math
    import pandas as pd

    pdf = pdf.sort_values(["ts", "seq"])
    rows = list(pdf.itertuples(index=False))
    distance = 0.0
    coords = []
    geometry_stride = max(1, math.ceil(len(rows) / 2000))
    geometry_rows = rows[::geometry_stride]
    if geometry_rows[-1] is not rows[-1]:
        geometry_rows.append(rows[-1])
    for row in geometry_rows:
        coords.append(f"{row.longitude} {row.latitude}")
    if len(coords) == 1:
        coords.append(coords[0])
    for left, right in zip(rows, rows[1:]):
        p1, p2 = math.radians(left.latitude), math.radians(right.latitude)
        dlat = p2 - p1
        dlon = math.radians(right.longitude - left.longitude)
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        distance += 2 * 6371000.0 * math.asin(math.sqrt(min(1.0, a)))
    start, end = rows[0].ts, rows[-1].ts
    return pd.DataFrame([{
        "run_id": rows[0].run_id, "user_id": rows[0].user_id,
        "trajectory_id": rows[0].trajectory_id, "start_ts": start, "end_ts": end,
        "point_count": len(rows), "distance_m": float(distance),
        "duration_s": max(0.0, (end - start).total_seconds()),
        "geom_wkt": "LINESTRING(" + ",".join(coords) + ")",
    }])


def _stay_points(pdf):
    import math
    import pandas as pd

    pdf = pdf.sort_values(["ts", "seq"])
    points = [
        {"timestamp": row.ts.to_pydatetime().replace(tzinfo=timezone.utc), "latitude": float(row.latitude),
         "longitude": float(row.longitude), "altitude_m": row.altitude_m,
         "user_id": row.user_id, "trajectory_id": row.trajectory_id}
        for row in pdf.itertuples(index=False)
    ]
    stays = []
    start_index = 0
    for end_index in range(1, len(points) + 1):
        close = end_index == len(points)
        if not close:
            close = (points[end_index]["timestamp"] - points[end_index - 1]["timestamp"]).total_seconds() > 1800
        if not close:
            anchor, candidate = points[start_index], points[end_index]
            p1, p2 = math.radians(anchor["latitude"]), math.radians(candidate["latitude"])
            dlat = p2 - p1; dlon = math.radians(candidate["longitude"] - anchor["longitude"])
            a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
            close = 2 * 6371000.0 * math.asin(math.sqrt(min(1.0, a))) > 200.0
        if close:
            window = points[start_index:end_index]
            if window and (window[-1]["timestamp"] - window[0]["timestamp"]).total_seconds() >= 1200:
                lat = sum(row["latitude"] for row in window) / len(window)
                lon = sum(row["longitude"] for row in window) / len(window)
                radius = 0.0
                for row in window:
                    p1, p2 = math.radians(lat), math.radians(row["latitude"])
                    dlat = p2 - p1; dlon = math.radians(row["longitude"] - lon)
                    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
                    radius = max(radius, 2 * 6371000.0 * math.asin(math.sqrt(min(1.0, a))))
                stays.append({"run_id": pdf.iloc[0].run_id, "user_id": window[0]["user_id"], "trajectory_id": window[0]["trajectory_id"], "start_ts": window[0]["timestamp"].isoformat().replace("+00:00", "Z"), "end_ts": window[-1]["timestamp"].isoformat().replace("+00:00", "Z"), "duration_s": (window[-1]["timestamp"] - window[0]["timestamp"]).total_seconds(), "latitude": lat, "longitude": lon, "radius_m": radius})
            start_index = end_index
    return pd.DataFrame(stays, columns=["run_id", "user_id", "trajectory_id", "start_ts", "end_ts", "duration_s", "latitude", "longitude", "radius_m"])


def main() -> None:
    parser = argparse.ArgumentParser(description="GeoTrack full GeoLife Spark pipeline")
    parser.add_argument("--input", required=True, help="PLT glob or hdfs:/// URI")
    parser.add_argument("--output-root", required=True, help="Root directory for curated Parquet")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--manifest", default=None, help="Optional full-summary manifest for quality counters")
    parser.add_argument("--eps-m", type=float, default=500.0)
    parser.add_argument("--min-pts", type=int, default=3)
    parser.add_argument("--partitions", type=int, default=32)
    args = parser.parse_args()
    if args.eps_m <= 0 or args.min_pts < 1 or args.partitions < 1:
        raise SystemExit("eps-m、min-pts 和 partitions 必须为正数")
    run_id = args.run_id or f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    try:
        from pyspark.sql import SparkSession, functions as F, types as T, Window
    except ImportError as error:  # pragma: no cover
        raise SystemExit("PySpark is required; run this job in the Spark batch image") from error

    spark = SparkSession.builder.appName("GeoTrack-Full-Pipeline").config("spark.sql.session.timeZone", "UTC").getOrCreate()
    sc = spark.sparkContext
    point_schema = T.StructType([
        T.StructField("run_id", T.StringType(), False),
        T.StructField("user_id", T.StringType(), False),
        T.StructField("trajectory_id", T.StringType(), False),
        T.StructField("seq", T.IntegerType(), False),
        T.StructField("ts", T.TimestampType(), False),
        T.StructField("latitude", T.DoubleType(), False),
        T.StructField("longitude", T.DoubleType(), False),
        T.StructField("altitude_m", T.DoubleType(), True),
    ])
    input_files = sc.wholeTextFiles(args.input, minPartitions=args.partitions)
    if input_files.isEmpty():
        raise SystemExit(f"输入路径没有匹配 PLT 文件: {args.input}")
    records = input_files.flatMap(
        lambda item: [{**row, "run_id": run_id, "ts": datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)} for row in _parse_file(item)]
    )
    points = spark.createDataFrame(records, schema=T.StructType([
        T.StructField("run_id", T.StringType(), False), T.StructField("user_id", T.StringType(), False),
        T.StructField("trajectory_id", T.StringType(), False), T.StructField("seq", T.IntegerType(), False),
        T.StructField("timestamp", T.StringType(), False), T.StructField("ts", T.TimestampType(), False),
        T.StructField("latitude", T.DoubleType(), False), T.StructField("longitude", T.DoubleType(), False),
        T.StructField("altitude_m", T.DoubleType(), True),
    ])).select("run_id", "user_id", "trajectory_id", "seq", "ts", "latitude", "longitude", "altitude_m")
    # Keep the curated point layer physically partitioned for downstream
    # user-scoped scans and serving loads. The year column is derived from
    # the normalized UTC timestamp so the layout is deterministic.
    points = points.withColumn("year", F.year("ts"))
    points = points.repartition("user_id", "year").sortWithinPartitions("trajectory_id", "ts", "seq")
    root = args.output_root.rstrip("/")
    points.write.mode("overwrite").partitionBy("user_id", "year").parquet(f"{root}/points")

    trajectory_schema = T.StructType([
        T.StructField("run_id", T.StringType(), False), T.StructField("user_id", T.StringType(), False),
        T.StructField("trajectory_id", T.StringType(), False), T.StructField("start_ts", T.TimestampType(), False),
        T.StructField("end_ts", T.TimestampType(), False), T.StructField("point_count", T.IntegerType(), False),
        T.StructField("distance_m", T.DoubleType(), False), T.StructField("duration_s", T.DoubleType(), False),
        T.StructField("geom_wkt", T.StringType(), False),
    ])
    trajectories = points.groupBy("run_id", "user_id", "trajectory_id").applyInPandas(_trajectory_summary, trajectory_schema)
    trajectories.write.mode("overwrite").parquet(f"{root}/trajectories")

    stay_schema = T.StructType([
        T.StructField("run_id", T.StringType(), False), T.StructField("user_id", T.StringType(), False),
        T.StructField("trajectory_id", T.StringType(), False), T.StructField("start_ts", T.StringType(), False),
        T.StructField("end_ts", T.StringType(), False), T.StructField("duration_s", T.DoubleType(), False),
        T.StructField("latitude", T.DoubleType(), False), T.StructField("longitude", T.DoubleType(), False),
        T.StructField("radius_m", T.DoubleType(), False),
    ])
    stays = points.groupBy("run_id", "user_id", "trajectory_id").applyInPandas(_stay_points, stay_schema)
    stays = stays.withColumn("start_ts", F.to_timestamp("start_ts")).withColumn("end_ts", F.to_timestamp("end_ts"))
    stays.write.mode("overwrite").parquet(f"{root}/stay_points")

    lat_step = args.eps_m / 111195.0
    lon_step = args.eps_m / 111195.0
    cells = stays.withColumn("cell_lat", F.floor(F.col("latitude") / F.lit(lat_step))).withColumn("cell_lon", F.floor(F.col("longitude") / F.lit(lon_step)))
    base = cells.groupBy("run_id", "cell_lat", "cell_lon").agg(
        F.avg("latitude").alias("latitude"), F.avg("longitude").alias("longitude"),
        F.count("*").alias("visit_count"), F.approx_count_distinct("user_id").alias("unique_users"),
        F.avg("duration_s").alias("avg_dwell_s"), F.avg(F.when(F.dayofweek("start_ts").between(2, 6), 1.0).otherwise(0.0)).alias("weekday_ratio"),
    )
    base = base.where(F.col("visit_count") >= F.lit(args.min_pts))
    by_hour = cells.groupBy("run_id", "cell_lat", "cell_lon", F.hour("start_ts").alias("peak_hour")).count()
    win = Window.partitionBy("run_id", "cell_lat", "cell_lon").orderBy(F.desc("count"), F.asc("peak_hour"))
    peak = by_hour.withColumn("rank", F.row_number().over(win)).where("rank = 1").drop("rank", "count")
    hotspots = base.join(peak, ["run_id", "cell_lat", "cell_lon"]).withColumn("hotspot_id", F.concat(F.lit("FHS-"), F.format_string("%08d", F.abs(F.hash("cell_lat", "cell_lon"))))) \
        .withColumn("radius_m", F.lit(args.eps_m / 2)).withColumn("algorithm", F.lit("spark-grid")) \
        .select("run_id", "hotspot_id", "latitude", "longitude", "radius_m", "visit_count", "unique_users", "avg_dwell_s", "peak_hour", "weekday_ratio", "algorithm")
    hotspots.write.mode("overwrite").parquet(f"{root}/hotspots")

    user_stats = trajectories.groupBy("run_id", "user_id").agg(
        F.count("*").alias("trajectory_count"), F.sum("point_count").alias("point_count"),
        F.sum("distance_m").alias("distance_m"), F.avg("duration_s").alias("avg_duration_s"),
    )
    users = user_stats.select("run_id", "user_id", "trajectory_count", "point_count", "distance_m")
    users.write.mode("overwrite").parquet(f"{root}/users")
    hourly = trajectories.groupBy("run_id", "user_id", F.hour("start_ts").alias("hour")).count()
    pivoted = hourly.groupBy("run_id", "user_id").pivot("hour", list(range(24))).sum("count").fillna(0)
    for hour in range(24):
        source = str(hour)
        pivoted = pivoted.withColumn(f"h{hour}", F.col(source).cast("double") if source in pivoted.columns else F.lit(0.0))
        if source in pivoted.columns:
            pivoted = pivoted.drop(source)
    pivoted = pivoted.withColumn("total", sum(F.col(f"h{h}") for h in range(24)))
    profile = pivoted.select(
        "run_id", "user_id",
        *[F.when(F.col("total") > 0, F.col(f"h{h}") / F.col("total")).otherwise(0.0).alias(f"h{h}") for h in range(24)],
    )
    from pyspark.ml.clustering import KMeans
    from pyspark.ml.feature import VectorAssembler
    assembler = VectorAssembler(inputCols=[f"h{h}" for h in range(24)], outputCol="features")
    model_input = assembler.transform(profile)
    distinct_users = profile.select("user_id").distinct().count()
    model = KMeans(k=max(1, min(3, distinct_users)), seed=42, featuresCol="features", predictionCol="cluster_id").fit(model_input)
    clustered = model.transform(model_input).withColumn("hourly_profile", F.array(*[F.col(f"h{h}") for h in range(24)]))
    patterns = clustered.groupBy("run_id", "cluster_id").agg(F.count("*").alias("user_count"), F.collect_list("hourly_profile").alias("profiles"))
    patterns = patterns.withColumn("hourly_profile", F.expr("transform(sequence(0, 23), i -> aggregate(profiles, cast(0.0 as double), (acc, x) -> acc + x[i]) / size(profiles))"))
    pattern_stats = clustered.join(user_stats, ["run_id", "user_id"]).groupBy("run_id", "cluster_id").agg(
        F.avg("trajectory_count").alias("avg_trip_count"), F.avg("distance_m").alias("avg_distance_m"),
        F.avg("avg_duration_s").alias("avg_duration_s"),
    )
    patterns = patterns.join(pattern_stats, ["run_id", "cluster_id"], "left")
    patterns = patterns.withColumn("pattern_id", F.concat(F.lit("PT-"), (F.col("cluster_id") + 1).cast("string"))).withColumn("label", F.lit("多时段活动型")).withColumn("avg_trip_count", F.coalesce(F.col("avg_trip_count"), F.lit(0.0))).withColumn("avg_distance_m", F.coalesce(F.col("avg_distance_m"), F.lit(0.0))).withColumn("avg_duration_s", F.coalesce(F.col("avg_duration_s"), F.lit(0.0))).withColumn("weekday_ratio", F.lit(0.0)).select("run_id", "pattern_id", "cluster_id", "label", "user_count", "avg_trip_count", "avg_distance_m", "avg_duration_s", "hourly_profile", "weekday_ratio")
    patterns.write.mode("overwrite").parquet(f"{root}/patterns")

    manifest = {}
    if args.manifest and Path(args.manifest).exists():
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    quality = {**manifest.get("counts", {}), "run_id": run_id, "spark_valid_points": points.count(), "spark_trajectory_count": trajectories.count(), "spark_user_count": users.count(), "output_root": args.output_root, "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    quality_path = f"{root}/quality"
    spark.createDataFrame([(json.dumps(quality, ensure_ascii=False),)], ["json"]).coalesce(1).write.mode("overwrite").text(quality_path)
    print(json.dumps(quality, ensure_ascii=False))
    spark.stop()


if __name__ == "__main__":
    main()
