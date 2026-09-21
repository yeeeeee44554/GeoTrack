# Spec 008 · 课程验收与最终交付

**Status**: Accepted
**Owner**: GeoTrack 小组
**Dependencies**: Spec 001–007
**Target commit**: `ed71b88`（本阶段 acceptance runner 已加入）

## Context

课程评分同时关注功能、架构、数据处理、算法解释、Git/Vibe Coding 过程和答辩材料。完成代码不等于完成课程交付，必须把证据、限制和实际贡献写入报告。

## Goals

- 用自动化测试和人工演示证明主要需求。
- 保留每个阶段的 Spec、Prompt、提交号和实际运行记录。
- 准备报告、PPT、分工表和不超过 5 分钟的备份视频。

## Non-goals

- 不伪造未实际运行的全量 Spark/HDFS 性能数据。

## Requirements

### R-008-01 自动化验收

统一命令：`make acceptance`，运行 Python 测试、载荷 dry-run、Compose 配置检查和前端生产构建。

必须运行 Python 算法/API 测试、前端生产构建、Compose 配置检查和服务载荷 dry-run，并记录日期、环境和结果。

### R-008-02 端到端演示

演示 SHALL 按“总览 → 轨迹 → 热点 → 参数/筛选 → 模式 → 任务质量 → 四层架构”顺序完成，目标关键 API 响应不超过 3 秒。

### R-008-03 过程证据

每个阶段 SHALL 有对应 Spec、Prompt 和 Git 提交；Prompt SHALL 记录用户输入、约束、验收命令和实际偏差。

### R-008-04 合规披露

报告 SHALL 说明数据集来源和许可证、官方规模与演示子集差异、未实现交通方式识别的理由和实际贡献。

## Scenarios

### Scenario: 正常答辩

- Given 服务和演示数据已经准备。
- When 按演示脚本操作。
- Then 五个页面和核心算法解释在 5 分钟内完成，出现故障时切换备份视频。

### Scenario: 现场故障

- Given Docker、地图底图或数据库不可用。
- When 启动本地回退模式或播放视频。
- Then 仍能展示架构、样例结果、限制和已验证证据，不声称故障环境已运行成功。

## Contracts

交付目录至少包含 `docs/specs/`、`docs/prompts/`、`docs/requirements.md`、`docs/design.md`、`docs/report.md`、`docs/contribution.md`、README、测试和 Git 历史。

## Acceptance

- [x] 全量数据已实际运行：2058 万点、15,399 条轨迹、8,438 个停留点、541 个热点、3 类时段模式；HDFS/Spark/PostGIS/MobilityDB 四层链路已在 Docker 中跑通。
- [ ] 生成 PPT 与 MP4 备份视频，并在报告中引用对应提交号。
- [ ] 发布 `v1.0-course` 标签。

## Risks and traceability

最终验收依赖教师、Docker 镜像和网络环境；任何未实际验证的项目必须标记为待验证。该 Spec 汇总 Spec 001–007 和课程内容说明的所有验收条款。
