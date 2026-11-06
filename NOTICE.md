# AI Infra Advisor — Notice

本项目代码以 MIT 许可证发布，文档、知识卡片和章节摘要以 CC BY-NC 4.0 发布。

## 内容来源

- 《AI Infra 全栈实战：从硬件底座到行业落地》
  - 作者：AI Infra 技术团队
  - 版本：2026 年 10 月第一版
  - 引用范围：项目中的章节摘要、知识卡片、结构化数据和图表基于该书内容进行原创提炼与统一口径复算；不提交 PDF 原件，不逐字复制原文。
  - 知识库语料：`data/knowledge/corpus/` 中的章节切分与表格 JSON 由本地 `ai-infra rag extract` 从已购 PDF 派生，仅用于检索与问答；PDF 原件被 `.gitignore` 排除，仓库内不含原书文件。若版权方要求，可删除该派生语料，仓库仍可通过 `cards.yaml` 与计算器独立运行。

## 数据来源

- GPU 规格与价格：公开渠道，标注 `as_of` 与 `confidence`。
- 云厂商价格：AWS / 阿里云 / 腾讯云 / 火山引擎官方公开文档，标注 `as_of`。
- 模型结构：模型卡与官方仓库。

## 口径与复算说明

原书部分表格中存在「节点数 vs GPU 数」「托管含电 vs 电费重复」等成本统计范围混用。本项目：

1. 用强 schema（Pydantic）统一口径，`nodes`、`gpus_per_node`、`colocation_includes_power` 等字段显式分离。
2. 所有表格类数字都重新计算，并输出 `assumptions`、`warnings`、`provenance`。
3. 详细公式与口径差异见 `docs/calculations.md`。

## 贡献

欢迎 Issue / PR。如果您是原书作者或版权方，并对引用范围有疑问，请在 Issue 中提出，我们会及时处理。
