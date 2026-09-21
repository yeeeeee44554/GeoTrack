# Spec 005 · PostGIS / MobilityDB 服务层

**Status**: Implemented
**Owner**: GeoTrack 小组
**Dependencies**: Spec 002、Spec 004
**Target commit**: `ed71b88`

## Context

浏览器需要按用户、时间和空间范围快速查询预计算结果。PostGIS 保存空间几何和 GiST 索引，MobilityDB 的 `tgeompoint` 为时态轨迹保留扩展空间。批处理结果必须通过 `run_id` 可追踪，重复导入不能产生重复记录。

## Goals

- 建立课程要求的轨迹点、轨迹摘要、停留点、热点、时段模式和任务表。
- 提供幂等载入器和无需数据库连接的载荷检查。
- 让未来 API 可以从 JSON demo 平滑切换到 SQL 查询。

## Non-goals

- 本阶段不要求所有本机 Docker 镜像都已拉取成功。
- 本阶段不把原始 PLT 直接写入服务表。

## Requirements

### R-005-01 表与索引

`trajectory_points` SHALL 有 `(user_id, ts)`、`geom` 和 `(trajectory_id, seq)` 索引；`trajectories` SHALL 有用户时间索引和轨迹几何 GiST 索引；停留点和热点 SHALL 有空间索引。

### R-005-02 字段

轨迹摘要 SHALL 保存起止时间、点数、距离、时长、LineString 和可选 `tgeompoint`；热点 SHALL 保存访问次数、独立用户数、平均停留、峰值小时、算法和 `run_id`；模式 SHALL 保存中心特征和 `hourly_profile` JSONB。

### R-005-03 幂等

按 `trajectory_id`、`(trajectory_id, seq)`、`hotspot_id` 和 `pattern_id` upsert。再次载入同一输入 SHALL 更新结果，不增加重复行。

### R-005-04 数据版本

每批载入 SHALL 生成或接收 `run_id`，并写入热点、模式和任务记录，便于报告展示最后处理批次。

## Scenarios

### Scenario: dry-run

- Given 数据库未启动。
- When 执行 `python jobs/check_serving_payload.py`。
- Then 输出待载入的点、轨迹、热点和模式数量，不连接数据库。

### Scenario: 重复载入

- Given 同一 `demo.json` 已载入一次。
- When 再次执行载入器。
- Then 冲突键行被更新，表中没有重复轨迹或点。

## Contracts

Schema 位于 `sql/001_schema.sql`；加载器为 `jobs/load_serving_tables.py`；默认 DSN 为 `postgresql://geotrack:geotrack@localhost:5432/geotrack`。几何 SRID 为 4326。

## Acceptance

- [x] Schema 包含课程要求的核心表和索引。
- [x] 载荷检查输出 `60000` 点、`72` 条演示轨迹、`46` 个停留点、3 个热点和 1 个模式。
- [x] MobilityDB 容器已实际初始化；`tgeompoint` 已由 `sql/002_mobilitydb_tgeompoint.sql` 填充（15,399 条轨迹），API 新增 `valueAtTimestamp` / `atTime` 时空查询接口。
- [x] 处理产物持久化 `stay_points`；加载器 dry-run 不依赖 psycopg，并通过轨迹/时间窗口避免停留点重复。

## Risks and traceability

`mobilitydb/mobilitydb:latest` 可能随时间变化，课程交付前应固定可用镜像标签并记录版本。对应 Spec 003、006、008。
