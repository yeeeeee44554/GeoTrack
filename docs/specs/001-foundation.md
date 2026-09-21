# Spec 001 · 项目初始化与四层架构

**Status**: Implemented  
**Owner**: GeoTrack 小组  
**Dependencies**: 课程内容说明、GeoLife 许可证说明  
**Target commit**: `6bc21a1`

## Context

项目需要在三周课程周期内交付一个可演示的大数据 Web 应用。课程要求交互层、业务层、数据管理与挖掘层、大数据处理层分离，并要求提交真实 Git 历史、SDD、Vibe Coding 提示词和可复现演示方式。GeoLife 原始数据体积较大且带有非商业研究许可，不能进入 Git 仓库。

## Goals

- 建立 React + ECharts + Leaflet、FastAPI、PostgreSQL/PostGIS/MobilityDB、HDFS + Spark 四层目录和运行边界。
- 在没有数据库、Spark 或原始数据时，仍能通过内置 `data/demo_seed.json` 展示核心页面。
- 让每个阶段可以独立提交、回滚和验收。

## Non-goals

- 本阶段不上传原始 GeoLife 数据。
- 本阶段不承诺真实集群已经运行，也不实现交通方式分类。

## Requirements

### R-001-01 目录

仓库 SHALL 包含 `backend/`、`frontend/`、`jobs/`、`sql/`、`docker/`、`data/`、`docs/` 和 `tests/`。生成物、缓存、原始数据和依赖目录 SHALL 被 `.gitignore` 排除。

### R-001-02 四层边界

前端 SHALL 只通过 REST JSON 与业务层交互；批处理 SHALL 生成可落库的中间结果；数据库 SHALL 负责空间/时态查询；网页请求 SHALL 不直接执行全量挖掘。

### R-001-03 数据合规

README SHALL 记录 GeoLife 来源、非商业用途、官方规模、本地目录和不提交原始数据的原因。

### R-001-04 回退

API 或处理结果不可用时，前端 SHALL 使用小型脱敏种子数据显示加载、空数据和错误状态。

## Scenarios

### Scenario: 无数据库演示

- Given 本机没有 PostgreSQL 或 HDFS。
- When 启动 FastAPI 和 React 开发服务器。
- Then 总览、地图、热点、模式和质量页面仍显示 `demo_seed.json`，且页面不因 API 失败而白屏。

### Scenario: 原始数据误提交检查

- Given 本地存在 `Geolife Trajectories 1.3/`。
- When 执行 `git status` 和 `git ls-files`。
- Then 原始目录不出现在 Git 跟踪列表中。

## Contracts

入口命令为 `scripts/run_backend.ps1`、`npm run dev` 和 `docker compose up -d`。所有时间使用 UTC ISO-8601，几何使用 GeoJSON，演示结果默认位于 `data/processed/demo.json`。

## Acceptance

- [x] `git log` 至少包含初始化提交。
- [x] `git ls-files` 不包含原始数据和依赖目录。
- [x] 前端在 API 不可用时显示种子数据。

## Risks and traceability

对应 `docs/requirements.md` 的目标、合规和非功能需求，后续由 Spec 002–008 细化。
