# GeoTrack 项目报告提纲

## 1. 项目概述

GeoTrack 面向 GeoLife Trajectories 1.3，完成 GPS 轨迹数据的清洗、停留点提取、热点区域挖掘、时段模式聚类和 Web 交互展示。全量数据规模为 182 个用户、18,670 条轨迹、约 2,487 万轨迹点；网页默认展示北京高密度演示子集。

## 2. 四层架构

- 交互层：React、ECharts、Leaflet，提供数据总览、轨迹探索、热点分析、出行模式和质量任务页面。
- 业务层：FastAPI，提供 REST API、参数校验和后台任务状态。
- 数据管理与挖掘层：目标环境使用 PostGIS/MobilityDB 服务表，保存轨迹线、空间索引和热点结果；无 Docker 时使用被忽略的 SQLite 全量索引作为本地答辩回退。
- 大数据处理层：HDFS 保存 raw/curated 数据，Spark 执行批处理和特征工程。

## 3. 数据处理

PLT 文件跳过前 6 行，统一解析为 UTC 时间、经纬度、米制海拔和轨迹序号。处理时删除非法坐标、连续重复点，并按 30 分钟时间断点切段。

## 4. 挖掘方法

1. Haversine 距离计算。
2. 半径 200m、时长 20min 的停留点提取。
3. eps=500m、minPts=3 的可解释 DBSCAN 热点聚类。
4. 按用户聚合的 24 小时出行频率向量 KMeans 时段模式聚类，seed=42；若课程要求更细粒度，可进一步扩展为用户-日期样本并在报告中单独比较。

## 5. 系统演示

演示顺序建议为：总览指标 → 地图轨迹 → 点击热点 → 调整最少用户 → 查看出行模式 → 触发挖掘任务 → 说明四层架构。

## 6. 合规与局限

GeoLife 原始数据只在本地使用，不提交 GitHub。当前标签仅覆盖部分用户，因此交通方式分类不作为第一版验收功能。单人项目是否符合课程 2–4 人分组要求，需以教师书面确认结果为准。



## 7. 验收记录（2026-09-06）

- Python 单元/API/服务载荷测试：当日记录为 12 项通过；后续回归测试扩展为 20 项。
- check_serving_payload.py 与 load_serving_tables.py --dry-run：通过，输出 60,000 点、72 条轨迹、46 个停留点、3 个热点、1 个模式。
- `npm run build`：通过；Vite 仍提示 ECharts 分包超过 500 kB，仅为优化建议。
- docker compose config：通过。
- Docker Desktop Linux daemon：本次 Windows 会话未运行（npipe 不存在），因此 HDFS、Spark、PostGIS/MobilityDB 容器的真实启动与 SQL 写入仍标记为待目标机验证。
- 一键入口：scripts/acceptance.ps1 与 make acceptance。

## 8. 最新复核（2026-09-14）

- 已从 GitHub `origin/main` 同步至提交 `438c5f5`；本地原有 `jobs/full_serving_index.py` 和 `tests/test_full_index.py` 修改通过 autostash 保留。
- 修复前端验收回归：恢复“任务与质量”第五个视图、页面主标题、全量/演示模式标识、日期筛选和方法说明。浏览器实测五个视图均可打开，任务提交可进入 `completed`，桌面 1440×900 与窄屏 390×844 均能渲染。
- 修正批处理编排：`spark-submit` 显式连接 `spark://spark-master:7077` 并依赖 Worker，避免容器启动后悄悄退回 `local[*]`。
- 静态验收：20 项 Python 测试通过；服务载荷 dry-run、`docker compose config` 和 `npm run build` 通过。前端仍有 ECharts 约 1.06 MB 分包警告，不影响构建。
- 全量本地索引证据：24,751,613 个有效点、18,670 条轨迹、182 个用户、9,651 个停留点；已按课程默认 `eps=500m / minPts=3` 重建并得到 363 个热点（旧的 `minPts=30` 产物另存为本地备份）。该结果是本地 SQLite serving fallback，不应表述成已完成 Spark/HDFS/MobilityDB 集群验证。
- 仍需在 Docker 可用的目标机补齐：HDFS raw 上传、Spark Parquet/MLlib 作业、MobilityDB `tgeompoint` 写入、PostGIS 查询性能（目标关键查询不超过 3 秒）以及录制不超过 5 分钟的 MP4 备份视频。
