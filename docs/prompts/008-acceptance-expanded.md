# Prompt 008 · 课程验收与最终交付（工程版）

## 提示词

```text
请阅读 docs/specs/008-acceptance.md、requirements-v2.md、design-v2.md 和全部阶段 Spec，生成最终验收清单和交付材料索引。

自动验证至少包括 Python 单元/API 测试、前端生产构建、docker compose config、服务载荷 dry-run 和 Git 合规检查。人工演示按总览→轨迹→热点→筛选/参数→模式→任务质量→四层架构执行，关键 API 目标不超过 3 秒。

报告必须同时写明官方规模和演示规模、数据集许可、清洗和算法参数、Spark/HDFS 实际运行证据、PostGIS/MobilityDB 证据、未完成项和交通方式识别延期原因。每个阶段列出 Spec、Prompt、提交号和测试结果。准备 PPT、5 分钟内 MP4 备份视频和 v1.0-course 标签。
```

## 交付检查

不要伪造未运行的性能或集群结果；任何待验证项写入报告和 Spec；提交信息使用 `docs: complete course acceptance package`。


## Follow-up: reproducible acceptance runner

Add scripts/acceptance.ps1 and make acceptance; run tests, serving dry-runs, Compose config and frontend build. Record exact demo counts and explicitly distinguish Docker configuration validation from unavailable daemon execution.
