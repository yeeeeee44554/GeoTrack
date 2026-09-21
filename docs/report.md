# GeoTrack 项目报告

## 一、项目概述

GeoTrack 面向微软亚洲研究院 GeoLife Trajectories 1.3 数据集，完成 GPS 轨迹数据的清洗、停留点提取、热点区域挖掘、时段模式聚类与 Web 交互展示。项目按"大数据综合实践"课程要求实现交互层、业务层、数据管理与挖掘层、大数据处理层四层架构。

数据规模：官方发行版包含 182 个用户、18,670 条轨迹、约 2,487 万个轨迹点；本项目实际完成全量处理 154 个用户、15,399 条轨迹、20,585,745 个轨迹点、8,438 个停留点、541 个热点、3 类时段模式。网页默认展示北京高密度演示子集以保证交互流畅。

<<<<<<< HEAD
## 二、系统架构
=======
- 交互层：React、ECharts、Leaflet，提供数据总览、轨迹探索、热点分析、出行模式和质量任务页面。
- 业务层：FastAPI，提供 REST API、参数校验和后台任务状态。
- 数据管理与挖掘层：目标环境使用 PostGIS/MobilityDB 服务表，保存轨迹线、空间索引和热点结果；无 Docker 时使用被忽略的 SQLite 全量索引作为本地答辩回退。
- 大数据处理层：HDFS 保存 raw/curated 数据，Spark 执行批处理和特征工程。
>>>>>>> upstream/main

项目采用四层架构，各层职责分离、通过明确接口协作：

```text
React + ECharts + Leaflet      （交互层）
        ↓ REST JSON
FastAPI                         （业务层）
        ↓ SQL / 参数校验
PostgreSQL / PostGIS / MobilityDB （数据管理与挖掘层）
        ↑ 批量装载
HDFS + Spark                     （大数据处理层）
```

1. **交互层**：React 单页应用，使用 Leaflet 渲染地图、ECharts 渲染图表，通过 REST JSON 与业务层交互，不直接访问数据库或执行全量挖掘。
2. **业务层**：FastAPI 提供查询接口、参数校验、分页和后台任务状态，HTTP 请求不阻塞执行全量 Spark 作业。
3. **数据管理与挖掘层**：PostgreSQL/PostGIS 保存空间几何与 GiST 索引，MobilityDB 的 `tgeompoint` 提供时态轨迹与时空查询（`valueAtTimestamp` / `atTime`）。
4. **大数据处理层**：HDFS 保存 raw 原始 PLT 与 curated 处理结果，Spark 完成批处理清洗、特征工程与聚类挖掘，输出扁平 Parquet 供服务层装载。

<<<<<<< HEAD
## 三、技术选型
=======
1. Haversine 距离计算。
2. 半径 200m、时长 20min 的停留点提取。
3. eps=500m、minPts=3 的可解释 DBSCAN 热点聚类。
4. 按用户聚合的 24 小时出行频率向量 KMeans 时段模式聚类，seed=42；若课程要求更细粒度，可进一步扩展为用户-日期样本并在报告中单独比较。
>>>>>>> upstream/main

| 层次 | 技术 | 选型理由 |
| --- | --- | --- |
| 交互层 | React + Vite | 组件化开发、快速热更新与生产构建 |
| 地图 | Leaflet + 高德瓦片 | 轻量、可交互，高德提供无密钥瓦片服务（GCJ-02） |
| 图表 | ECharts | 强大的时序与分布可视化能力 |
| 业务层 | FastAPI + uvicorn | 类型化请求校验、异步支持、自动 OpenAPI 文档 |
| 空间数据库 | PostgreSQL + PostGIS | 空间几何存储、GiST 索引、标准化 SQL 查询 |
| 时态数据库 | MobilityDB | `tgeompoint` 支持轨迹的时态存储与时空查询 |
| 大数据存储 | HDFS（Apache Hadoop 3.4.1） | 分布式文件系统，承载 raw/curated 数据 |
| 大数据计算 | Spark 3.5.4（bitnamilegacy） | 批处理、DataFrame/applyInPandas、MLlib KMeans |
| 容器编排 | Docker Compose | 一键启动四层服务，保证环境可复现 |

## 四、功能说明

### 4.1 数据清洗与处理

PLT 文件跳过前 6 行头部，统一解析为 UTC 时间、经纬度、米制海拔和轨迹序号；丢弃非法坐标，将海拔 `-777` 转为空值，删除连续重复点，并按 30 分钟时间断点切段。

### 4.2 挖掘算法

1. Haversine 米制距离计算。
2. 半径 200m、最短持续 20 分钟的停留点提取。
3. eps=500m、minPts=3 的热点聚类（Spark 批处理使用 spark-grid 实现），输出访问次数、独立用户数、平均停留、峰值小时等字段。
4. 用户 24 小时出行向量的 KMeans 时段模式聚类（k=3、seed=42），自动生成"早晚通勤型 / 高频全天型 / 午后夜间活动型"三类标签。

### 4.3 前端视图

<<<<<<< HEAD
1. **数据总览**：统计卡（轨迹点/轨迹数/覆盖用户）、北京地图轨迹密度、热点列表、一天出行节奏曲线。
2. **轨迹探索**：用户筛选、分页列表、轨迹详情，以及"时刻定位"滑块（调用 MobilityDB 时空查询显示该时刻位置红点）。
3. **热点分析**：最少用户筛选、热点排名、地图点击联动、峰值时段与平均停留详情。
4. **出行模式**：三类时段模式的 24 小时分布曲线，选中卡片时高亮对应曲线。

### 4.4 后台任务

任务接口支持 `queued / running / completed / failed` 四种状态，提交后立即返回 `job_id`，前端轮询任务状态，避免阻塞 HTTP 请求。

## 五、组内分工与贡献说明

小组共四人，分工与贡献占比如下：

| 成员 | 占比 | 负责模块 | 具体工作 |
| --- | ---: | --- | --- |
| 成员A | 30% | 大数据处理与挖掘算法 | PLT 解析与清洗、Haversine、停留点提取、热点聚类、KMeans 时段模式、Spark 批处理脚本 |
| 成员B | 30% | 后端与数据服务 | FastAPI 接口、PostGIS/MobilityDB 服务表、时空查询、后台任务、Docker 环境 |
| 成员C | 20% | 前端开发 | React 四个视图、Leaflet 地图、ECharts 图表、交互与响应式布局 |
| 成员D | 20% | 文档与交付 | SDD、Vibe Coding 提示词、项目报告、分工表、演示与验收材料 |

## 六、验收记录

- 全量数据已实际跑通（2026-09-21）：HDFS 存储 154 个用户原始 PLT；Spark 全量处理 2058 万点（15,399 条轨迹、8,438 个停留点、541 个热点、3 类时段模式）；PostGIS/MobilityDB 已入库并发布，`tgeompoint` 已填充并新增 `valueAtTimestamp` / `atTime` 时空查询接口。
- Python 单元/API 测试、前端生产构建、docker compose config 均通过。
- 一键入口：`scripts/acceptance.ps1` 与 `make acceptance`。

## 七、合规与局限

GeoLife 原始数据仅在本地使用，不提交 GitHub。交通方式标签仅覆盖部分用户，因此交通方式分类不作为第一版验收功能；高德底图为 GCJ-02 坐标，与 WGS-84 数据存在数百米偏移，属已知取舍。
=======
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
>>>>>>> upstream/main
