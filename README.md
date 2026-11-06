# AI Infra Advisor

把 AI 基础设施选型从「拍脑袋 + 各家报价表」变成**可复算、可追溯、可解释**的决策引擎。

项目基于《AI Infra 全栈实战：从硬件底座到行业落地》的知识体系，但不照搬书里的表格数字：
所有 TCO、MFU、显存、KV Cache 计算都由 Python 确定性内核重新计算，每一步都带
`assumptions / warnings / provenance / trace_id`。

> 核心原则：**LLM 不负责算数**。Agent 只负责理解问题、补全参数、选择工具和解释结果；
> 所有数字来自可测试的 Python 工具。

---

## 能力一览

| 能力 | 说明 |
|---|---|
| TCO 计算 | CapEx + OpEx×年限 + 隐藏成本 − 残值；区分 `nodes` 与 `gpus_per_node` |
| 每 GPU 小时 / 每百万 token | 统一分母，支持跨方案比较 |
| 自建 vs 云对比 | 按需 / 1 年预留 / 3 年预留 / Spot / 按月租赁；Spot 按可用率折算「有效每 GPUh」 |
| 盈亏平衡利用率 U* | 自建成本 ≤ 云成本时的最低利用率 |
| MFU | 训练 / 推理、Dense / MoE、实测或估算、通信开销 |
| KV Cache | GQA/MQA、上下文长度、batch、页式开销 |
| 显存估算 | 权重 / 梯度 / 优化器 / 激活 / KV / workspace；LoRA、ZeRO、梯度检查点、OOM 风险 |
| 选型顾问 | 业务问卷 → 硬约束 + GPU/节点数 → 最低有效成本模式 |
| 工具调用 Agent | DeepSeek（OpenAI-compatible），最多 5 轮工具调用，全程 trace 可回放 |
| 书籍知识库 RAG | 全 18 章正文 + 315 张表格入库；表格按行解析、保留表头字段名，以 JSON 结构存入 sqlite-vec，命中后可回取整表 |
| 报告生成 | Markdown + PDF 双格式：A4 封面、编号章节、表格、页眉页脚与页码，可直接对外交付 |

## 前端页面

| 路径 | 页面 | 作用 |
|---|---|---|
| `/` | 首页 | 项目定位、能力入口、示例结果 |
| `/calculator` | 计算器 | TCO / MFU / 显存 三个 Tab |
| `/compare` | 成本对比 | 自建 vs 云，有效每 GPUh 条形图 + 盈亏平衡利用率 |
| `/advisor` | 选型顾问 | 8 项问卷 → 推荐 → 生成并下载 Markdown / PDF 技术方案 |
| `/knowledge` | 知识库 | 书籍正文 / 表格检索：类型与章节过滤、命中行高亮、整表 JSON 渲染 |
| `/agent` | Agent | 对话 + 工具调用 + 执行轨迹面板，一次问答可导出 PDF 技术方案 |

## 产品使用指南

四个典型使用场景，按「我要解决什么问题」找入口即可。

### 场景一：自建到底划不划算 → `/compare`

1. 打开 <http://localhost:3000/compare>。
2. 填参数：节点数、每节点 GPU 数、GPU 型号、使用年限、利用率。默认值是 `8 节点 × 8 卡 H100 / 3 年 / 60%`。
3. 点「开始对比」，看三块内容：
   - **有效每 GPU 小时成本**条形图：云按需 / 1 年预留 / 3 年预留 / Spot / 按月租赁，统一分母后可直接比；
   - **盈亏平衡利用率**：自建成本 ≤ 云成本所需的最低利用率（显示「无法达到」说明自建即使 100% 利用率也不如该云模式便宜）；
   - **结果卡片**：自建每 GPU 小时与总卡数、各模式明细表（名义价 / 有效价 / 总成本 / 说明）、成本结构与关键假设。
4. 判断规则：你预计的**实际利用率高于 U\*** → 自建更划算；低于 U\* → 云更划算。
   Spot 不要看名义单价，看它折算出的「有效每 GPUh」（已按可用率折算）。

### 场景二：给定业务，该买什么配置 → `/advisor`

1. 打开 <http://localhost:3000/advisor>。
2. 填 8 项问卷：业务类型、模型规模（B）、QPS、团队人数、TTFT / TPOT SLO、隐私等级、年预算（可空）。
   不清楚的先按默认值走，结果里的「关键假设」会把你用到的口径全部列出来。
3. 点「生成推荐」，得到：硬约束判断、推荐 GPU 型号 / 节点数 / 每节点卡数、最低成本部署模式与推荐理由。
4. 点「生成报告」→ 「下载 Markdown」或「下载 PDF」，把整份技术方案保存下来，
   可直接用于内部评审或给客户（PDF 含封面、分级章节、表格与页码）。

隐私等级填 `high` / `max` 时，先确认推荐方案的**单机显存余量**和是否必须私有化，
再拿它去 `/compare` 复算自建成本。

### 场景三：查书里有明确答案的事实 → `/knowledge`

适合问「哪家的最低门槛是多少」「这张表里 H100 什么价格」这类有确切出处的问题。

1. 打开 <http://localhost:3000/knowledge>，输入问题回车，或点页面上的示例问题。
2. 结果卡片怎么读：
   - `doc_type` 为 `table_row` 时是**精确数值行**，卡片下方「命中行」高亮对应单元格；
   - 表格类结果会带**整表 JSON**（表头 + 全部行），可直接核对上下文；
   - 每张卡片标注章节、小节、页码、`score`，可回书里复核。
3. 查不到或结果发散时的技巧：
   - 用「章节」下拉（如 `第12章`）缩小范围；
   - 先按「片段类型 = 表格行」查数值，答案需要背景时再切回「全部类型」；
   - 检索默认是混合模式，想验证纯语义/纯关键词可切换「检索方式」。

### 场景四：让 Agent 端到端回答并交付 → `/agent`

1. 打开 <http://localhost:3000/agent>。
2. 提问时尽量带上**厂商 / 模型 / 规模 / 年限**，例如：
   「70B 模型、200 QPS、隐私要求高，自建还是用云？给我 3 年 TCO」。
3. 右侧 trace 面板会显示每个工具的调用参数、返回值和耗时：
   数字类问题走计算器，事实类问题走 `search_knowledge`，两者可同时用。
4. 回答满意后点「导出 PDF 技术方案」，得到带问题、结论、工具轨迹、假设与来源的 PDF。

> Agent 的规则是：**数字只来自 Python 计算器，事实只来自知识库**。
> 回答里的价格与页码都可在 trace 中找到对应来源；找不到来源的数字请当作不可信。

### 怎么读懂每个结果

| 字段 | 含义 | 使用建议 |
|---|---|---|
| `value` | 计算结果（summary / 明细行） | 对外引用前先确认单位 |
| `assumptions` | 本次计算采用的默认值（利用率、电价、PUE、年限等） | 与实际情况不符就改参数重算，别手工改结论 |
| `warnings` | 口径提醒与风险（Spot 可用率、托管费是否含电、OOM 风险等） | 出现在报告里时必须回应，否则结论不成立 |
| `provenance` | 数据来源 + `as_of` + 置信度 | 引用价格时一并带 `as_of`，避免把历史快照当现价 |
| `trace_id` | 本次计算的唯一 ID | 复现、对账、排障时提供它即可 |

### 常见误区

- **节点数与 GPU 数别混**：本项目强制两个字段，`总卡数 = 节点数 × 每节点卡数`。
- **别拿 Spot 名义价直接对比**：低单价对应低可用率，要比「有效每 GPUh」。
- **托管费可能已含电**：填了「含电」就不要再单独计电费，否则成本重复。
- **书里的价格是历史快照**：知识库给的是书中口径，采购前用厂商最新报价复核。
- **利用率是全局分母**：它影响每 GPU 小时成本和盈亏平衡点，不要只改结论。

## 快速开始

### 1. 环境

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

### 2. 安装后端

```bash
uv sync --extra dev
```

如不使用 uv：

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -e ".[dev]"
```

### 3. 配置环境变量（可选）

Agent 需要一个 OpenAI-compatible 的 LLM。默认接 DeepSeek：

```bash
cp .env.example .env
```

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

不配置 key 也能运行：Agent 会自动降级为规则兜底模式，计算器 / 对比 / 报告全部可用。

> `.env` 已被 `.gitignore` 忽略，不要把密钥提交到仓库。

### 4. 启动后端

```bash
uv run uvicorn ai_infra.api.main:app --reload --port 8000
```

- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/healthz>

### 5. 启动前端

```bash
npm --prefix web install
npm --prefix web run dev
```

打开 <http://localhost:3000>。

若后端不在 `8000` 端口，构建/启动前设置：

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001 npm --prefix web run dev
```

## CLI

```bash
# 64 张 H100，3 年，60% 利用率
uv run ai-infra tco --nodes 8 --gpus-per-node 8 --gpu h100-sxm5-80gb --years 3 --util 60

# 自建 vs 云
uv run ai-infra compare --nodes 8 --gpus-per-node 8 --gpu h100-sxm5-80gb --years 3 --util 60

# MFU
uv run ai-infra mfu --model llama3-70b --gpu h100-sxm5-80gb --n-gpus 64 --tp 8 --dp 8

# 显存 / KV Cache
uv run ai-infra memory --model llama3-70b --gpu h100-sxm5-80gb --tp 8
uv run ai-infra kv-cache --model llama3-70b --seq 131072

# 选型
uv run ai-infra recommend --business customer_service --model-size 70 --qps 200 --privacy high

# 数据目录
uv run ai-infra devices

# 书籍知识库：抽取 → 建索引 → 检索
uv sync --extra rag-extract                       # pdfplumber，仅抽取时需要
uv run ai-infra rag extract --pdf <原书 PDF>       # 产出 data/knowledge/corpus/*
uv run ai-infra rag build                          # 产出 data/knowledge/index.db（不入库）
uv run ai-infra rag search "字节跳动 GPU 总量" --top-k 3
uv run ai-infra rag search "私有化部署最低门槛" --chapter 第12章 --type table_row --detail
uv run ai-infra rag stats
```

## API 摘要

完整接口与示例见 [docs/api.md](docs/api.md)。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查与 LLM 就绪状态 |
| GET | `/api/catalog` | GPU / 模型数据目录 |
| POST | `/api/tco` | TCO |
| POST | `/api/compare` | 自建 vs 云 |
| POST | `/api/mfu` | MFU |
| POST | `/api/kv-cache` | KV Cache |
| POST | `/api/memory` | 显存 |
| POST | `/api/recommend` | 选型推荐 |
| GET | `/api/knowledge/search` | 书籍知识库混合检索（正文 / 表格三粒度） |
| GET | `/api/knowledge/stats` | 索引概览（块数、表数、嵌入模型、章节） |
| GET | `/api/knowledge/tables/{table_id}` | 回取整表 JSON |
| POST | `/api/agent/chat` | Agent 对话（返回 trace） |
| POST | `/api/agent/export` | 一次问答导出 PDF 技术方案 |
| POST | `/api/report` | 生成 Markdown + PDF 报告 |
| GET | `/api/report/{filename}` | 下载报告（md / pdf） |

所有计算端点返回统一结构：

```json
{
  "value": {"summary": {}, "...": {}},
  "assumptions": ["..."],
  "warnings": ["..."],
  "provenance": [{"source": "data/gpus.yaml#h100-sxm5-80gb", "as_of": "2025-06", "confidence": "medium"}],
  "trace_id": "tr_xxxxxxxxxxxx"
}
```

## 目录结构

```text
.
├── src/ai_infra/
│   ├── models.py            # Pydantic 输入/输出；字段强制带单位
│   ├── catalog.py           # 加载 + 校验 GPU / 模型数据
│   ├── calculators/         # tco / compare / mfu / kv_cache / memory / recommender
│   ├── agent/               # tools / loop / trace / rag（卡片回退）
│   ├── rag/                 # extract / chunker / build / store / search / embedding
│   ├── api/main.py          # FastAPI
│   ├── cli.py               # Typer + Rich
│   ├── report.py            # Markdown 报告
│   ├── pdf_export.py        # PDF 排版（封面 / 章节 / 表格 / 页码）
│   └── config.py            # .env 配置
├── data/
│   ├── gpus.yaml            # GPU 规格与价格（带 provenance）
│   ├── models.yaml          # 模型结构（带 provenance）
│   ├── knowledge/cards.yaml # 12 张知识卡片（索引缺失时兜底）
│   └── knowledge/corpus/    # 章节正文 + 表格 JSON（派生语料，提交仓库）
├── tests/
│   ├── golden/test_tco.py   # 手算基准 + 属性测试
│   └── unit/                # 数据目录 / RAG 分块 / API
├── web/                     # Next.js 14 + Tailwind
├── docs/                    # 架构 / API / 开发 / 口径说明
└── PROJECT_PLAN.md          # 项目路线图与阶段规划
```

## 口径与复算

原书部分表格存在「节点数 vs GPU 数」「托管费含电 vs 电费重复」等口径混用。本项目用强 schema 显式区分：

- `nodes` 与 `gpus_per_node` 必须是两个字段，`total_gpus = nodes × gpus_per_node`。
- `colocation_includes_power=True` 时不再单独计电费。
- Spot 名义单价低，但按 30% 可用率折算「有效每 GPUh」，避免误判为最低成本。
- 每条 GPU / 模型记录必须带 `source / as_of / confidence`。

公式与复算约定见 [docs/calculations.md](docs/calculations.md)。

## 测试与质量

```bash
uv run pytest -q          # golden + unit + API
uv run ruff check .
uv run mypy src tests
```

当前基准：`8 节点 × 8 H100 / 3 年 / 60% 利用率` 的 TCO 约 **¥19.99M**，每 GPU 小时约 **¥19.81**。

## 开发文档

- [docs/book/README.md](docs/book/README.md) — 全书 18 章 + 前言 Markdown（由知识库语料生成，含表格）
- [docs/architecture.md](docs/architecture.md) — 分层架构、数据流、Agent 循环
- [docs/api.md](docs/api.md) — API 端点、请求/响应示例
- [docs/development.md](docs/development.md) — 本地开发、测试、调试、前后端联调
- [docs/calculations.md](docs/calculations.md) — 公式、口径与复算说明

## 数据更新

`data/*.yaml` 是唯一数据源。新增 GPU / 模型时复制现有条目，并**必须**填写：

```yaml
as_of: "2025-06"       # YYYY-MM 或 YYYY-MM-DD
source: "厂商公开规格"
confidence: "medium"   # high / medium / low
```

API 启动时会校验 provenance；缺失或格式错误的条目会导致加载失败。

## License

- 代码：MIT，见 [LICENSE](LICENSE)
- 文档 / 知识卡片：CC BY-NC 4.0
- 引用范围与版权说明：见 [NOTICE.md](NOTICE.md)

## 安全提示

- 不要在 Issue、聊天或提交中粘贴真实 API Key。
- 若 key 曾出现在公开渠道，请立即在服务商控制台轮换。
- Agent 的工具层只接受白名单工具与结构化参数，不会执行任意代码。
