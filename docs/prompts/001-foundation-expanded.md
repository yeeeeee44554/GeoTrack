# Prompt 001 · 项目初始化与四层架构（工程版）

## 背景

GeoTrack 是大数据综合实践课程项目，主题为“基于 GPS 轨迹的用户出行模式挖掘与热点区域分析系统”。课程要求 2–4 人分组、四层架构、真实 Git 历史、SDD、Vibe Coding 提示词和可复现演示。

## 提示词

```text
请按 docs/specs/001-foundation.md 和 docs/requirements-v2.md 初始化 GeoTrack。建立 frontend、backend、jobs、sql、docker、data、docs/specs、docs/prompts、tests 目录，并保持 React+ECharts+Leaflet、FastAPI、PostGIS/MobilityDB、HDFS+Spark 四层边界。

实现要求：
1. 原始 GeoLife 和课程材料不进入 Git；补充 .gitignore、README 数据许可、本地目录和官方规模说明。
2. API 或数据库不可用时，前端读取 data/demo_seed.json，展示明确的 demo 数据模式。
3. 所有时间输出 UTC ISO-8601，GeoJSON 使用 [longitude, latitude]。
4. 将启动方式整理为本地脚本、docker compose 和 Makefile 命令，不在本阶段伪造分布式运行结果。
5. 为目录、回退和关键入口写最小测试或检查命令。

完成后输出：变更文件、运行命令、验证结果、未完成项、课程风险和建议的语义化 Git 提交信息。
```

## 验收

`git ls-files` 不包含原始数据；本地前后端可启动；API 失败时页面不白屏；提交包含 README、SDD 和本阶段 Prompt。
