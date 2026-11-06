# AI Infra Advisor — 项目规划

> 版本：v0.1（规划稿）  
> 来源材料：`AI-Infra-全栈实战.pdf`（443 页，18 章）  
> 目标：把「读过的书」变成「可运行、可验证、可演示」的 AI Infra 决策引擎，作为简历与面试的核心项目。

---

## 0. 结论先行

不要做成「读书笔记仓库」。要做成一个 **AI Infra 决策引擎**：

```text
确定性计算内核  +  版本化数据目录  +  工具调用 Agent  +  数据驱动文档站  +  报告生成器
```

最关键的一条设计原则：

> **Agent 不负责算数。Agent 负责理解意图、追问、调用工具、解释结果；所有数字由可测试的 Python 计算内核产生，并附带假设、来源和置信度。**

这样既有 Agent 的亮点，又不会出现「LLM 一本正经算错 TCO」的硬伤。

首个可演示版本只做三件事：
1. 算清一台 / 一个集群要花多少钱（TCO、每 GPUh、每百万 token）。
2. 算清 MFU、显存、KV Cache、并发能力。
3. 给出可解释、可复算的选型建议，并生成一份报告。

### 0.1 已确认决策

| 决策项 | 选择 | 对项目的影响 |
|---|---|---|
| 版权路线 | 作者/团队可公开章节 | 可以放章节内容；仍不提交 PDF，并保留来源与内容许可证 |
| 首期 MVP | 计算内核 + TCO CLI | P0 → P1 先交付 `ai-infra tco`，Web/Agent 后续复用 |
| LLM 接入 | OpenAI-compatible，默认 DeepSeek | 通过 `OPENAI_BASE_URL` 切换；无 Key 走离线规则模板 |
| 前端 | Next.js + FastAPI | P3 实现交互计算器、对比页、Agent trace 面板 |

---

## 1. 项目定位

| 项目 | 内容 |
|---|---|
| GitHub 仓库名 | `ai-infra-advisor` |
| 中文名 | AI Infra 决策引擎 |
| 一句话 | 先算清，再买卡。 |
| 英文 Tagline | Know the number before you buy the cluster. |
| 副标题 | A verifiable decision engine for AI infrastructure: MFU, KV Cache, memory, TCO, vendor selection, and a tool-using agent. |
| 目标用户 | AI Infra 工程师、架构师、CTO、正在做算力选型的技术团队 |
| 项目形态 | Python Library + CLI + Web Dashboard + Agent + Docs Site + Report Generator |
| 核心差异化 | 不是「知识摘要」，而是「可执行、可复算、可审计的决策工具」 |

### 1.1 电梯陈述

> 市面上大量 AI Infra 资料停留在论文、产品介绍或经验文章，缺少把硬件、通信、推理优化、集群、成本和行业方案串起来的可执行模型。  
> 我把一本 443 页的 AI Infra 实战书拆解成结构化数据、可测试的计算内核和工具调用 Agent：输入 GPU 型号、集群规模、利用率和电价，就能得到 TCO、每 GPUh 成本、MFU、KV Cache 占用和选型建议；Agent 负责追问和解释，但从不凭空算数。  
> 项目同时提供 24 张由数据自动生成的图表、18 章知识卡片和可下载的选型报告，完整展示从知识工程到产品交付的能力。

---

## 2. 简历亮点设计

| # | 亮点 | 具体做法 | 面试可讲 | 可验证证据 |
|---|---|---|---|---|
| H1 | **确定性计算内核** | 用 Pydantic 建模 GPU、模型、集群、成本；MFU、KV Cache、显存、TCO 全部是纯函数；每个公式有单元测试和手算基准 | 「为什么不让 LLM 算？」「如何保证结果可复现？」 | `pytest` 覆盖率 ≥ 85%，50+ golden cases |
| H2 | **工具调用型 Agent** | LLM 只做意图识别、槽位补全、工具编排和解释；工具层输出 assumptions / warnings / provenance / trace_id | 「Agent 的边界怎么划？」「如何评测？」 | 40 条金标场景，工具选择准确率、数值误差 < 5%、100% 引用覆盖 |
| H3 | **数据驱动文档站** | 24 张图表全部由 `data/*.yaml` 生成，图表带 `data_ref` 和 `as_of`；不是手画图 | 「数据变了图表怎么更新？」 | `make charts` 一键重生成，CI 校验数据 provenance |
| H4 | **口径复算与 QA** | 原书部分表格存在「节点数 vs GPU 数」「托管含电 vs 电费重复」等口径混用；项目用强 schema 统一口径，并单列「复算说明」页 | 「你如何验证资料可信度？」 | 复算页列出差异、公式、修正值，可逐项回放 |
| H5 | **端到端工程化** | Library + CLI + FastAPI + Next.js + MkDocs + Docker + GitHub Actions + PyPI | 「你如何保证质量？」 | 4 条 CI job：python / web / docs / docker |
| H6 | **产品化交付** | 8 题选型问卷 → 可解释推荐 → Markdown/PDF 报告；报告含假设、敏感性、风险、实施路线 | 「技术如何变成业务价值？」 | 一键生成 8 页报告，Demo 可下载 |
| H7 | **成本敏感性分析** | 利用率、电价、GPU 价格、残值、年限、PUE 六维敏感性；自建 vs 云盈亏平衡点 | 「如果电价涨了怎么办？」 | 交互滑块 + 瀑布图 / 龙卷风图 |

### 2.1 与普通「读书笔记项目」的差异

| 普通笔记项目 | 本项目 |
|---|---|
| 章节摘要、摘抄 | 结构化知识卡片 + 可执行公式 |
| 手画或截图图表 | 由版本化数据自动生成，可复现 |
| 聊天机器人套壳 | 工具调用 Agent + 评测集 + 全链路 trace |
| 数字靠手抄 | 数字靠计算，带假设、来源、置信度 |
| 无测试 | golden tests + property tests + CI |
| 只能读 | 能算、能比、能生成报告 |

---

## 3. 非目标（明确不做）

- 不做真实 GPU 跑分：没有硬件，不伪造 benchmark；预留 `benchmark import` 接口，后续可接入 DCGM / nccl-tests 结果。
- 不做 443 页全文搬运：公开仓库只放原创摘要、公式、结构化事实和图表。
- 不做通用聊天机器人：Agent 只服务 AI Infra 选型与成本问题，超出范围要拒答。
- 不做 Kubernetes Operator / 调度器 / 推理引擎：不是本项目重点。
- 不做 20 家云厂商实时价格爬虫：v1 用手工版本化数据，标注 `as_of`。
- 不做模型训练本身：只做基础设施决策。

---

## 4. 产品形态

### 4.1 五个入口

| 入口 | 形态 | 作用 | 技术 |
|---|---|---|---|
| Library | `pip install ai-infra-advisor` | 给工程师复用计算能力 | Python + Pydantic |
| CLI | `ai-infra tco ...` / `ai-infra report ...` | 快速算账、出报告 | Typer / Click |
| Web | 交互式 Dashboard | 滑块调参、图表对比、选型问卷 | Next.js + ECharts |
| Agent | 对话式顾问 | 追问、解释、调用工具 | OpenAI-compatible + tool calling |
| Docs | 知识站 | 18 章笔记、卡片、图表、复算说明 | MkDocs Material |

### 4.2 三个核心用户旅程

**旅程 A：10 秒算账**
```text
首页 → 选择 GPU 型号 / 卡数 / 利用率 / 电价 / 年限
     → 实时看到 3 年 TCO、每 GPUh、每百万 token 成本
     → 一键切换 自建 / 云按需 / 1 年预留 / 3 年预留 / 混合
```

**旅程 B：5 分钟选型**
```text
8 题问卷（业务类型、模型规模、QPS、SLO、预算、地区、合规、团队规模）
→ 规则引擎给出 Top 3 方案
→ 每个方案附成本、性能、风险、实施路线
→ 生成 Markdown / PDF 报告
```

**旅程 C：追问**
```text
用户：「70B 模型 128K 上下文，单卡 H100 80G 能跑吗？」
Agent：调用 calc_kv_cache + calc_memory
     → 给出「不能」+ 需要几张卡 + 并发数 + 假设 + 引用卡片
```

### 4.3 首屏信息架构

```text
Hero：一句话 + 三个实时数字（示例集群 TCO / 每 GPUh / 推荐方案）
├─ 交互计算器（TCO / MFU / KV Cache 三个 Tab）
├─ 对比区（GPU 性价比前沿、自建 vs 云、厂商雷达）
├─ 选型问卷入口
├─ Agent 入口
└─ 文档入口（18 章 / 24 图 / 知识卡片）
```

---

## 5. 核心能力设计

### 5.1 确定性计算内核

所有模块遵循同一套输出协议：

```python
class CalcResult(BaseModel):
    value: dict  # 主结果
    assumptions: list[str]  # 显式假设
    warnings: list[str]  # 口径冲突 / 数据过期 / 超出范围
    provenance: list[SourceRef]  # 数据来源 + as_of
    trace_id: str
```

| 模块 | 输入 | 输出 | 关键公式 / 规则 |
|---|---|---|---|
| `calc_mfu` | 模型参数量、激活参数量、层数、hidden、seq、batch、TP/PP/DP、step_time、GPU 峰值算力 | tokens/s、achieved TFLOPS、MFU、通信占比、气泡占比 | `MFU = tokens_per_sec × FLOPs_per_token / (peak_flops × n_gpus)` |
| `calc_kv_cache` | 层数、KV 头数、head_dim、seq、batch、dtype、GQA/MLA | 每 token / 每请求 / 总 KV 显存、最大并发 | `KV = 2 × L × H_kv × d_head × S × B × bytes × (1 + overhead)` |
| `calc_memory` | 参数量、精度、训练/推理、优化器、ZeRO、LoRA、并行度、activation | 权重 / 梯度 / 优化器 / 激活 / KV / 总计、OOM 风险 | 分项求和 + 10–20% workspace buffer |
| `calc_tco` | 节点数、每节点 GPU 数、GPU 单价、网络、存储、PUE、电价、人力、年限、利用率、残值 | CapEx、OpEx、TCO、每 GPUh、每百万 token、成本结构 | `TCO = CapEx + OpEx×years + Hidden + Refresh − Residual` |
| `compare_deployment` | 自建 / 云按需 / 1 年预留 / 3 年预留 / Spot / 混合 / 租赁 | 各方案 TCO、现金流、盈亏平衡利用率 | `U*` 使自建每 GPUh = 云每 GPUh |
| `recommend_config` | 业务类型、模型规模、QPS、TTFT/TPOT SLO、预算、地区、合规、团队规模 | Top 3 方案 + 评分 + 理由 + 风险 | 硬约束过滤 + 加权评分（成本/性能/合规/运维/扩展） |
| `generate_report` | 一个完整 scenario | Markdown / HTML / PDF | 8 段式模板 |

#### 关键公式说明

**MFU（训练）**
```text
FLOPs_per_token ≈ 6 × N_active + 12 × L × S × d_model
MFU = tokens_per_sec × FLOPs_per_token / (peak_flops × n_gpus)
```
- Dense 模型：`N_active = N_total`
- MoE 模型：`N_active` 只算共享参数 + 被激活的专家参数
- 同时输出 `MFU` 与 `HFU`（含重计算），避免把「重计算换显存」误读为效率提升
- 支持「实测模式」：用户输入 step_time / tokens/s，反推 MFU；支持「估算模式」：按模型和并行配置估算

**KV Cache**
```text
KV_bytes = 2 × L × H_kv × d_head × S × B × dtype_bytes × (1 + page_overhead)
max_concurrency = (HBM − weights − activations − workspace) / KV_per_request
```
- 支持 GQA / MQA / MLA 三种模型结构
- 支持 FP16 / BF16 / FP8 / INT8 KV 量化
- 输出「单卡能放多少并发」「128K 上下文需要几张卡」

**TCO**
```text
TCO = CapEx_hw + CapEx_network + CapEx_storage
    + (Electricity + Cooling + Colocation + Labor + Spare + Software + Insurance) × years
    + Hidden + Refresh − Residual

Electricity = nodes × node_kw × PUE × 8760 × price_per_kwh
per_gpu_hour = TCO / (total_gpus × 8760 × years × utilization)
per_million_tokens = TCO / (tokens_per_sec × 3600 × 8760 × years × utilization / 1e6)
```
- 强制区分 `nodes` 与 `gpus_per_node`，避免原书里「64 台 DGX」和「64 张卡」混用
- 托管费「含电」与「按电力计费」互斥，避免重复计算
- 输出成本结构（GPU / 电力 / 人力 / 网络 / 存储 / 其他）
- 输出 3 年 / 5 年现金流、NPV（可选）、静态回收期

**盈亏平衡**
```text
U* = TCO_self_build / (cloud_price_per_gpu_hour × total_gpus × 8760 × years)
```
- 同时给出「云按需 / 1 年预留 / 3 年预留 / Spot」四条基准线
- 交互图：利用率 10%–100% 滑动，实时显示自建与云的交点

**选型评分**
```text
score = w_cost × cost_score + w_perf × perf_score + w_compliance × compliance_score
      + w_ops × ops_score + w_scale × scale_score + w_support × support_score
```
- 硬约束：预算、地区、合规、模型规模、SLO
- 输出「为什么推荐 / 为什么不推荐」的逐项理由，而不是一个黑盒分数

#### 数据与单位规范

- 字段名带单位：`price_cny`、`tdp_w`、`memory_gb`、`bandwidth_gbps`、`tflops_bf16`
- 禁止裸数字：所有输入必须有单位、来源、`as_of`
- 金额统一人民币，保留原始币种和汇率
- 数据置信度：`high / medium / low`，低置信度必须在 UI 上提示

### 5.2 数据目录

```text
data/
├─ gpus.yaml           # 9 类 GPU：H100/H800/A100/A800/L40S/RTX Pro 6000/4090/MI300X/910B
├─ models.yaml         # 7B/70B/110B/MoE 等模型结构参数
├─ cloud_prices.yaml   # AWS / 阿里云 / 腾讯云 / 火山引擎：按需/预留/Spot
├─ vendors.yaml        # 字节 / 阿里 / 腾讯 / DeepSeek 四家画像
├─ industries.yaml     # 小微/中型/医疗/金融/国央企/云选型
└─ knowledge/          # 知识卡片 Markdown + frontmatter
```

单条数据示例：

```yaml
- id: h100-sxm5-80gb
  vendor: nvidia
  memory_gb: 80
  memory_type: HBM3
  bf16_tflops_dense: 989
  tdp_w: 700
  price_cny:
    min: 200000
    max: 250000
  as_of: 2025-06
  source: "公开渠道价，区间为批发/零售差异"
  confidence: medium
  notes: "价格随供需波动，UI 必须显示 as_of"
```

**Provenance 规则（CI 强制）**
- 每条记录必须有 `source`、`as_of`、`confidence`
- 缺少任一字段，CI 失败
- 价格类数据超过 12 个月，UI 显示「数据可能过期」
- 数据更新写 `data/CHANGELOG.md`，保留历史版本

### 5.3 Agent 设计

#### 设计原则

1. **LLM 不做算术**：所有数字来自工具。
2. **LLM 不做事实记忆**：所有事实来自数据目录或知识卡片。
3. **LLM 必须显式假设**：缺参数时最多追问 2 个问题，其余用默认值并标注。
4. **LLM 必须可审计**：每次回答附带工具调用链、输入、输出、引用。
5. **LLM 必须能拒答**：超出 AI Infra 范围的问题直接说明边界。

#### 工具清单

```python
calc_mfu(params: MFUInput) -> CalcResult
calc_kv_cache(params: KVCacheInput) -> CalcResult
calc_memory(params: MemoryInput) -> CalcResult
calc_tco(params: TCOInput) -> CalcResult
compare_deployment(params: CompareInput) -> CalcResult
recommend_config(params: WorkloadInput) -> CalcResult
search_knowledge(query: str, top_k: int = 5) -> list[KnowledgeCard]
generate_report(scenario: ScenarioInput, format: Literal["md", "pdf"]) -> ReportArtifact
```

每个工具返回：
```json
{
  "value": {"tco_cny": 30575120, "per_gpu_hour_cny": 14.54},
  "assumptions": ["利用率 60%", "电价 0.8 元/kWh", "PUE 1.2"],
  "warnings": ["GPU 价格区间取中位数"],
  "provenance": [{"source": "gpus.yaml", "as_of": "2025-06"}],
  "trace_id": "tr_xxx"
}
```

#### Agent 循环

```text
1. 意图识别（规则 + LLM）
2. 槽位补全（缺什么问什么，最多 2 问）
3. 规划工具调用（可并行则并行）
4. 执行工具
5. 自检（单位、量级、跨工具一致性）
6. 组织回答：结论 / 假设 / 计算 / 风险 / 来源
7. 持久化 trace，前端可回放
```

#### 护栏

- 价格只能来自 `cloud_prices.yaml` / `gpus.yaml`；缺失时返回区间 + `as_of`，不得编造。
- 任何数字必须能追溯到某次工具调用；否则不输出。
- 工具参数强类型校验，LLM 不能传自由文本进计算函数。
- 最多 6 次工具调用，超时 30s，超预算则返回部分结果 + 说明。
- 对「帮我写 CUDA kernel」「帮我选股票」等越界问题拒答。
- 工具结果互相矛盾时，必须把矛盾展示给用户，而不是静默选一个。

#### 评测体系

40 条金标场景：

| 类型 | 数量 | 示例 | 期望 |
|---|---|---|---|
| TCO | 15 | 64 卡 H100，60% 利用率，3 年 TCO | 工具 `calc_tco`，数值在 ±5% |
| MFU / KV / 显存 | 10 | 70B，128K，单卡 H80G 能否跑 | 工具 `calc_kv_cache` + `calc_memory` |
| 选型 | 8 | 预算 300 万，客服 RAG，选什么 | `recommend_config` + `calc_tco`，先追问 |
| 厂商对比 | 4 | 字节 vs DeepSeek，医疗行业 | `compare_vendors` + `search_knowledge` |
| 多轮 / 追问 | 3 | 改利用率、改电价、改模型 | 复用上下文，重新调用工具 |

指标：
- 工具选择准确率
- 槽位完整率
- 数值误差（相对金标）
- 引用覆盖率（每个结论至少 1 个来源）
- 澄清次数（越少越好，但不能缺关键参数）
- P95 延迟、单次会话成本

#### 离线模式

- `LLM_PROVIDER=none`：不调用 LLM，用规则 + 模板完成计算和报告。
- `LLM_PROVIDER=openai-compatible`：默认 DeepSeek / OpenAI 兼容端点，通过 `OPENAI_BASE_URL` 切换。
- Demo 必须无 API Key 也能跑；有 Key 才展示 Agent 对话。

### 5.4 展示型文档站

用 **MkDocs Material**，部署到 GitHub Pages。

内容结构：

```text
docs/
├─ index.md                 # 项目首页：是什么、怎么用、三个数字
├─ chapters/                # 18 章原创摘要（每章 600–1000 字）
├─ cards/                   # 60 张知识卡片
├─ charts/                  # 24 张自动生成图表 + 解读
├─ vendors/                 # 4 家厂商画像 + 对照矩阵
├─ industries/              # 6 个行业落地方案
├─ pitfalls/                # 20 条避坑清单 + 排查命令
├─ fact-check.md            # 口径复算与差异说明
├─ data-dictionary.md       # 数据字段、单位、来源
└─ assets/                  # 图表 SVG、架构图、截图
```

每个图表必须有：
```yaml
chart_id: tco-structure-64xh100
title: 64×H100 三年 TCO 成本结构
data_ref: data/gpus.yaml#h100-sxm5-80gb
as_of: 2025-06
generated_by: scripts/gen_charts.py
```

### 5.5 报告生成器

输入一个 `scenario.yaml`，输出 8 页报告：

```text
1. 执行摘要（结论 + 三个关键数字）
2. 现状与目标（业务、模型、QPS、SLO）
3. 关键假设（价格、利用率、电价、PUE、年限）
4. 方案对比（自建 / 云 / 混合 / 租赁）
5. 成本分析（TCO、每 GPUh、每百万 token、敏感性）
6. 性能与容量（MFU、显存、KV Cache、并发）
7. 风险与避坑（数据过期、口径风险、供应商锁定）
8. 实施路线（Phase 0–4 + 验收指标）
附录：数据来源与计算明细
```

实现：Jinja2 模板 + Playwright 打印 PDF（避免 Windows 上 WeasyPrint 的 GTK 依赖）。

### 5.6 Web Dashboard

页面：

| 路由 | 内容 |
|---|---|
| `/` | Hero + 实时数字 + 三个入口 |
| `/calculator` | TCO / MFU / KV Cache 三个 Tab，滑块实时计算 |
| `/compare` | GPU 性价比前沿、自建 vs 云、厂商雷达 |
| `/advisor` | 8 题问卷 → Top 3 方案 → 生成报告 |
| `/agent` | 对话 + 右侧 trace 面板（工具调用、假设、来源） |
| `/reports/[id]` | 报告预览与下载 |

技术：Next.js 15 + TypeScript + Tailwind + shadcn/ui + ECharts + zod + react-hook-form。

---

## 6. 技术选型

| 层 | 选择 | 理由 | 备选 |
|---|---|---|---|
| 语言 | Python 3.11+ | 计算生态、数据生态、部署简单 | — |
| 包管理 | `uv` | 快、锁文件、CI 友好 | pip / poetry |
| 数据建模 | Pydantic v2 | 强类型、校验、JSON Schema | dataclasses |
| CLI | Typer | 类型友好、自动帮助 | Click |
| API | FastAPI | OpenAPI、SSE、Pydantic 原生 | Flask |
| 前端 | Next.js 15 + TypeScript | 简历辨识度高、部署方便 | Vite + React |
| 图表 | ECharts（Web）+ matplotlib（文档 SVG） | 交互 + 静态可复现 | Recharts |
| 文档 | MkDocs Material | Python 原生、搜索好、CI 简单 | Docusaurus |
| 报告 | Jinja2 + Playwright PDF | 跨平台、样式可控 | WeasyPrint |
| 测试 | pytest + hypothesis + Playwright | 单测 / 属性测试 / E2E | — |
| 代码质量 | ruff + mypy strict + ESLint | 统一风格、类型安全 | — |
| CI/CD | GitHub Actions | 免费、矩阵构建 | — |
| 部署 | Docs: Pages；Web: Vercel/Cloudflare；API: Fly.io/Render/单容器 | 成本低、可公开演示 | 阿里云/腾讯云 |
| LLM | OpenAI-compatible（默认 DeepSeek） | 国内可用、可切换 | Ollama 本地 |
| 存储 | SQLite（trace / report） | 零运维、够用 | Postgres |

---

## 7. 仓库结构

```text
ai-infra-advisor/
├─ README.md
├─ README.zh-CN.md
├─ PROJECT_PLAN.md
├─ LICENSE                      # 代码 MIT
├─ NOTICE.md                    # 内容来源与授权说明
├─ pyproject.toml
├─ uv.lock
├─ Makefile
├─ .env.example
├─ .gitignore                   # 忽略 .source/、PDF、密钥
├─ .github/
│  ├─ workflows/ci.yml
│  └─ workflows/pages.yml
├─ data/
│  ├─ gpus.yaml
│  ├─ models.yaml
│  ├─ cloud_prices.yaml
│  ├─ vendors.yaml
│  ├─ industries.yaml
│  ├─ CHANGELOG.md
│  └─ knowledge/
│     ├─ cards/
│     └─ chapters/
├─ src/ai_infra/
│  ├─ models.py                 # Pydantic 输入/输出模型
│  ├─ catalog.py                # 数据加载 + provenance 校验
│  ├─ calculators/
│  │  ├─ mfu.py
│  │  ├─ kv_cache.py
│  │  ├─ memory.py
│  │  ├─ tco.py
│  │  └─ compare.py
│  ├─ recommender.py
│  ├─ charts.py                 # 生成 SVG / 图表数据
│  ├─ report.py                 # Jinja2 + PDF
│  ├─ agent/
│  │  ├─ loop.py
│  │  ├─ tools.py
│  │  ├─ rag.py
│  │  ├─ trace.py
│  │  └─ eval.py
│  ├─ api/
│  │  └─ main.py
│  └─ cli.py
├─ tests/
│  ├─ unit/
│  ├─ golden/
│  └─ e2e/
├─ docs/
│  ├─ mkdocs.yml
│  └─ ...                       # 见 5.4
├─ web/
│  ├─ app/
│  ├─ components/
│  └─ lib/
├─ scripts/
│  ├─ extract_source.py         # PDF → .source/（本地，gitignored）
│  ├─ gen_charts.py
│  └─ update_prices.py
└─ docker/
   ├─ Dockerfile.api
   └─ Dockerfile.web
```

---

## 8. 内容规划：从书到知识资产

### 8.1 内容分层

| 层级 | 数量 | 作用 |
|---|---|---|
| 章节摘要 | 18 章 | 建立完整知识框架 |
| 知识卡片 | 60 张 | 可检索、可引用、可被 Agent 调用 |
| 图表 | 24 张 | 展示性内容，全部由数据生成 |
| 避坑清单 | 20 条 | 症状 / 根因 / 检查命令 / 修复 |
| 厂商画像 | 4 家 | 字节 / 阿里 / 腾讯 / DeepSeek |
| 行业方案 | 6 个 | 小微 / 中型 / 医疗 / 金融 / 国央企 / 云选型 |
| 复算说明 | 1 页 | 口径差异、公式、修正值 |
| 数据字典 | 1 页 | 字段、单位、来源、更新周期 |

### 8.2 18 章 → 产出映射

| 章节 | 核心产出 | 对应工具 / 图表 |
|---|---|---|
| 第 1 章 AI 层级架构 | 三层架构图、成本分布、层级选型策略 | `tco`、架构图、TCO 饼图 |
| 第 2 章 底层硬件 | GPU 选型表、NVLink/NCCL/IB 带宽阶梯 | GPU 性价比前沿、带宽阶梯图 |
| 第 3 章 推理优化 | PD 分离、KV Cache、MoE 优化卡片 | `kv_cache`、`mfu`、KV 曲线、PD tradeoff |
| 第 4 章 集群分级 | 单卡→单机→小集群→中大集群方案 | 规模效应曲线、拓扑图 |
| 第 5 章 性能压测 | 四层压测方法、瓶颈排查树 | MFU waterfall、瓶颈决策树 |
| 第 6 章 TCO 模型 | 成本模型、部署对比、敏感性分析 | `tco`、`compare`、全部成本图表 |
| 第 7 章 工程避坑 | 20 条黄金法则、故障排查手册 | 避坑清单、runbook |
| 第 8 章 字节 | 超大高并发集群画像 | 厂商雷达、架构图 |
| 第 9 章 阿里 | 全栈政企私有云画像 | 厂商雷达、合规矩阵 |
| 第 10 章 腾讯 | 低成本产业 AI 画像 | 厂商雷达、成本对比 |
| 第 11 章 DeepSeek | 轻量高性能小集群画像 | 厂商雷达、MoE 效率图 |
| 第 12 章 四厂对标 | 对照矩阵、选型决策树 | 热力图、Mermaid 决策树 |
| 第 13 章 小微企业 | 低成本落地方案 | `recommend_config`、报告模板 |
| 第 14 章 中型企业 | 混合云架构方案 | `compare`、混合云现金流 |
| 第 15 章 医疗 | 私有化单机标杆 | 行业 playbook、合规清单 |
| 第 16 章 金融 | 低延迟高可用方案 | 行业 playbook、SLO 表 |
| 第 17 章 国央企 | 合规型私有云方案 | 行业 playbook、合规矩阵 |
| 第 18 章 云厂商选型 | 对外输出逻辑、选型框架 | 决策树、云价格对比 |

### 8.3 图表清单（24 张）

| 组 | 图表 |
|---|---|
| 成本 | GPU 性价比前沿（价格 vs BF16 TFLOPS，气泡=显存）、每 TFLOPSh 成本排行、64 卡 3 年 TCO 结构、自建 vs 云五种模式、利用率-盈亏平衡曲线、电价敏感性龙卷风图、规模效应曲线、5 年累计现金流、每百万 token 成本 vs 并发、残值对 TCO 影响 |
| 性能 | MFU 分解 waterfall、KV Cache vs 上下文长度、显存构成 stacked bar、PD 分离 TTFT/吞吐 tradeoff、MoE EP 通信开销、PCIe/NVLink/IB/RoCE 带宽阶梯、集群规模 vs 通信占比、batch size vs 吞吐/延迟 |
| 选型 | 四厂商雷达图、私有化门槛 vs 3 年 TCO、行业场景选型热力图、选型决策树（Mermaid）、GPU 场景适配矩阵、成本优化杠杆 waterfall |

### 8.4 复算与口径统一（重要亮点）

原书信息量很大，但部分表格存在口径混用。项目不直接搬运数字，而是「按统一口径复算」，并在 `fact-check.md` 中保留差异说明。

已发现的典型问题：

| 位置 | 现象 | 本项目处理 |
|---|---|---|
| 6.1.2 / 6.6.1 | 64 卡 3 年 TCO 约 ¥3,244 万 / ¥3,348 万，表中每 GPUh 为 ¥2.11 / ¥2.23；按公式 `TCO / (64×8760×3)` 应约 ¥19.3 / ¥19.9 | 用 `nodes × gpus_per_node` 强 schema 重算，输出正确量级 |
| 6.8 | 托管费「含电」与电费重复计算，原文中途自我修正 | 成本项互斥校验：`colocation_includes_power` 为 true 时禁用 electricity |
| 1.4.6 vs 6.3.1 | 1000 卡按 10MW 计电费；按 6.3.1 单节点 10.2kW 推算，1000 卡（125 台 8 卡机）IT 功耗约 1.3MW | 输出「节点功耗 × 节点数 × PUE」的显式推导，避免节点/卡混淆 |
| 6.6.1 | 云按需 3 年 ¥1.296 亿，但 8 实例 × ¥706/h × 26,280h ≈ ¥1.485 亿 | 用同一公式重算，标注差异 |

> 公开表述建议：不写「原书错误」，写「原书口径 A / 本项目口径 B / 差异原因」。这样既体现严谨，也不会显得在贬低来源。

### 8.5 知识卡片 schema

```markdown
---
id: kv-cache-formula
title: KV Cache 显存公式
chapter: 3
tags: [推理优化, 显存, KV Cache]
formula: "KV = 2 × L × H_kv × d_head × S × B × bytes"
assumptions:
  - BF16 精度
  - 不含内存碎片
pitfalls:
  - 忘记乘 batch
  - 把 num_attention_heads 当成 num_kv_heads
related_tools: [calc_kv_cache]
sources:
  - AI Infra 全栈实战 第 3 章
---

## 一句话
...

## 什么时候用
...

## 怎么算
...

## 常见错误
...
```

---

## 9. 实施阶段

| 阶段 | 目标 | 交付物 | 验收标准 |
|---|---|---|---|
| **P0 骨架** | 仓库能跑、CI 能过 | `pyproject.toml`、目录结构、LICENSE/NOTICE、`.gitignore`、数据 schema、`extract_source.py`、CI | `uv run pytest` 绿；`uv run ai-infra --help` 可用；CI badge 绿 |
| **P1 计算内核** | 先把「算账」做扎实 | `models.py`、`catalog.py`、`tco.py`、`mfu.py`、`kv_cache.py`、`memory.py`、`compare.py`、`recommender.py`、CLI、50+ golden tests | 手算基准一致；覆盖率 ≥ 85%；每个公式有注释和来源；`ai-infra tco` 输出完整表格 |
| **P2 数据与图表** | 让内容可展示 | `gpus/models/cloud_prices/vendors/industries.yaml`、24 张图表、MkDocs 骨架、18 章摘要 v1 | `make charts` 可重现；docs 构建零警告；每条数据有 provenance |
| **P3 API + Web** | 做出可演示的界面 | FastAPI 6 个端点、Next.js 5 个页面、交互滑块、对比页、部署 | 手机端可用；Lighthouse ≥ 90；API P95 < 200ms；Demo URL 可访问 |
| **P4 Agent** | 做出简历 headline | 8 个工具、RAG、trace、40 条评测、离线 fallback、聊天 UI | 工具选择准确率 ≥ 90%；数值误差 < 5%；引用覆盖 100%；无 Key 可 Demo |
| **P5 报告与包装** | 变成「可交付产品」 | 报告生成器、README、截图/GIF、90 秒演示脚本、博客、Release v1.0、PyPI | 一键生成 8 页 PDF；README 首屏清晰；公开 Demo + Docs 链接 |
| **P6 内容深化** | 拉满项目厚度 | 60 张卡片、4 厂商、6 行业、20 避坑、复算页 | 所有页面有图/表/来源；无死链；内容可被 Agent 检索 |

**首期执行**：P0 → P1，先交付 `ai-infra tco`；P3/P4 复用同一计算内核。

依赖关系：

```text
P0 → P1 → P2 → P3
           └→ P6（可与 P3 并行）
P1 → P4（Agent 依赖工具）
P2 → P4（RAG 依赖卡片）
P3/P4 → P5
```

---

## 10. 工程质量标准

### 10.1 代码

- `ruff check` + `ruff format` 零告警
- 核心模块 `mypy --strict`
- 核心覆盖率 ≥ 85%
- 每个公式至少 1 个 golden test（手算值）
- 属性测试：
  - TCO 随利用率单调递减（每 GPUh）
  - KV Cache 随 seq_len 线性增长
  - 显存随 batch 单调递增
  - 自建 vs 云盈亏平衡点随电价上升而下降
- 不允许出现魔法数字：所有常量进 `data/` 或 `constants.py` 并注明来源

### 10.2 CI

4 条 job：
```text
python: ruff + mypy + pytest + coverage
web:    tsc + eslint + playwright smoke
docs:   mkdocs build --strict + link check
docker: build api + web images
```
数据校验单独一步：`python -m ai_infra.catalog validate`，缺 provenance 直接失败。

### 10.3 API / Agent

- 所有输入 Pydantic 校验
- 所有输出带 `assumptions / warnings / provenance / trace_id`
- Agent 最多 6 次工具调用，30s 超时
- SSE 流式输出，首 token < 3s（有 LLM 时）
- 结构化日志 + trace_id
- 速率限制 + CORS 白名单
- 不在仓库里放任何密钥；`.env.example` 只放变量名

### 10.4 文档 / 前端

- MkDocs `--strict` 零警告，无死链
- 每张图表有 `data_ref` 和 `as_of`
- Lighthouse Performance / Accessibility ≥ 90
- 移动端 375px 可用
- 所有表单有错误态、空态、加载态

### 10.5 Definition of Done

一个功能算完成，必须同时满足：
1. 有类型
2. 有单测
3. 有 UI 或 CLI 入口
4. 有文档或 tooltip 解释假设
5. 有 provenance
6. CI 绿

---

## 11. 简历与传播包装

### 11.1 README 首屏结构

```text
# AI Infra Advisor
> Know the number before you buy the cluster.

[Live Demo] [Docs] [PyPI] [CI]

三张截图：TCO 计算器 / Agent trace / 报告

## Why this
一段话：从经验判断到可复算决策。

## What's inside
- Deterministic calculators: MFU / KV Cache / Memory / TCO / Break-even
- Tool-using agent with trace & eval
- 24 data-generated charts, 60 cards, 18 chapter digests
- Report generator

## Quickstart
uv sync
uv run ai-infra tco --gpus 64 --years 3 --util 0.6
uv run ai-infra serve

## Architecture
一张图：Core → API → Web / Agent / Report / Docs

## Numbers I can defend
3–5 个关键数字 + 来源

## Roadmap
```

### 11.2 90 秒演示脚本

```text
0–10s   一句话 + 首页三个数字
10–30s  拖动利用率 30% → 70%，展示盈亏平衡点
30–50s  问 Agent：「100 人公司，预算 300 万，客服 RAG，选什么？」
50–70s  展示 trace：调用了哪些工具、假设是什么、数字从哪来
70–90s  一键生成报告并下载
```

### 11.3 简历 Bullet（中文）

> - 独立设计并实现 **AI Infra 决策引擎**（Python / FastAPI / Next.js），把 MFU、KV Cache、显存与 TCO 建模为可测试的确定性计算内核，覆盖 9 类 GPU、4 家厂商、6 个行业场景。
> - 构建 **工具调用型 Agent**：LLM 只负责意图理解与解释，计算全部下沉到带 provenance 的工具层；40 条金标评测，工具选择准确率 __%，数值误差 < 5%，全链路 trace 可回放。
> - 用代码复算原书 18 章关键数据，统一「节点/GPU」「托管/电费」等成本口径，产出 24 张自动生成图表、60 张知识卡片与选型报告生成器；CI 覆盖单测/类型/文档/镜像，Demo 无需 API Key 即可运行。

### 11.4 简历 Bullet（英文）

> - Built **AI Infra Advisor**, a verifiable decision engine (Python / FastAPI / Next.js) that models MFU, KV Cache, memory footprint and TCO as deterministic, unit-tested calculators across 9 GPUs, 4 vendors and 6 industry scenarios.
> - Designed a **tool-using agent** where the LLM never does arithmetic: intent parsing and explanation only, with all numbers produced by provenance-aware tools. 40 golden scenarios, __% tool-selection accuracy, <5% numeric error, fully replayable traces.
> - Recomputed the source book's 18 chapters with a unified cost model, shipping 24 data-generated charts, 60 knowledge cards and a report generator; CI covers tests, typing, docs and Docker; demo runs without an API key.

### 11.5 博客选题

1. 《不要让 Agent 算数：AI Infra 决策引擎的三层架构》
2. 《一张 H100 到底多少钱一小时？用 200 行 Python 算清 TCO》
3. 《从 443 页到 24 张图：如何把技术书变成可执行知识库》
4. 《Agent 评测不是聊天：40 条金标场景怎么做》
5. 《节点数还是 GPU 数？AI Infra 成本核算里最容易错的单位》

### 11.6 GitHub 设置

- Topics: `ai-infra`、`gpu`、`tco`、`llm`、`agent`、`fastapi`、`nextjs`
- Social preview：一张架构图 + 一句话
- Pin 2 个 Issue：`Roadmap`、`Good first issue`
- Release v1.0 附 Demo 视频和报告样例
- About：一句话 + Demo + Docs 链接

---

## 12. 风险与边界

| 风险 | 影响 | 对策 |
|---|---|---|
| **版权** | 公开仓库搬运原文会侵权 | 不提交 PDF；不逐字复制章节；只放原创摘要、公式、结构化事实和图表；代码 MIT，笔记 CC BY-NC 4.0；`NOTICE.md` 标注来源；如作者要求可下架 |
| 数据过期 | 价格/型号变化导致结论失真 | 每条数据带 `as_of`；UI 显示「数据截至」；提供敏感性和区间；`data/CHANGELOG.md` |
| 源材料口径不一致 | 复算结果与原书不同 | 单列 `fact-check.md`；用「口径 A / 口径 B」表述；所有差异可回放 |
| LLM 幻觉 | Agent 编造价格/结论 | 工具化计算；prompt 禁止编造；输出必须带 provenance；无来源不输出数字 |
| 范围膨胀 | 项目做不完 | MVP 只做 TCO + MFU + KV + 选型 + 报告；K8s operator、实时爬虫、模型训练明确不做 |
| 无真实硬件 | 缺少第一手 benchmark | 使用公开规格；标注「估算」；预留 benchmark import；不伪造实测数据 |
| 部署成本 | Demo 无法长期在线 | Docs 用 Pages；API 用免费额度；提供本地 Docker 一键启动 |
| 维护成本 | 数据更新耗时 | 数据与代码分离；更新脚本 + CI 校验；只维护 9 类 GPU / 4 家云 |

### 版权路线（已确认：路线 B）

- **已确认**：你是作者/团队，可以公开章节内容。
- 仍建议：不提交 PDF 原件；仓库内放内容许可证与来源说明；代码 MIT，内容 CC BY-NC 4.0（或你指定的许可证）。
- `NOTICE.md` 记录：书名、作者、版本、引用范围。

---

## 13. 验收清单

### 项目层

- [ ] 公开 Demo 可访问，手机端可用
- [ ] Docs 站可访问，18 章 / 24 图 / 60 卡片完整
- [ ] `pip install ai-infra-advisor` 可用（可选）
- [ ] Docker 一键启动
- [ ] CI 全绿，覆盖率 ≥ 85%
- [ ] README 首屏有截图、Demo、Quickstart、架构图

### 计算层

- [ ] TCO 覆盖：自建 / 云按需 / 1 年预留 / 3 年预留 / Spot / 混合 / 租赁
- [ ] 每 GPUh、每百万 token、成本结构、敏感性、盈亏平衡
- [ ] MFU 支持 Dense / MoE、训练 / 推理
- [ ] KV Cache 支持 GQA / MQA / MLA、量化、并发
- [ ] 显存支持训练 / 推理 / LoRA / QLoRA / ZeRO
- [ ] 所有结果有 assumptions / warnings / provenance

### Agent 层

- [ ] 8 个工具可调用
- [ ] 40 条评测可跑
- [ ] 工具选择准确率 ≥ 90%
- [ ] 数值误差 < 5%
- [ ] 引用覆盖 100%
- [ ] 无 Key 可离线 Demo
- [ ] trace 可回放

### 内容层

- [ ] 18 章摘要原创完成
- [ ] 60 张卡片可检索
- [ ] 24 张图表由数据生成
- [ ] 4 家厂商画像
- [ ] 6 个行业方案
- [ ] 20 条避坑清单
- [ ] 复算说明页
- [ ] 数据字典

---

## 14. 下一步生成顺序

建议按下面顺序逐个文件生成，避免一次性铺太大：

1. `README.md`（先立住项目叙事）
2. `pyproject.toml`、`Makefile`、`.gitignore`、`.env.example`
3. `src/ai_infra/models.py`（Pydantic 输入/输出协议）
4. `data/gpus.yaml`、`data/models.yaml`（先 5 个 GPU + 3 个模型）
5. `src/ai_infra/calculators/tco.py` + `tests/golden/test_tco.py`（先做最亮的算账能力）
6. `src/ai_infra/cli.py`（`ai-infra tco` 可跑）
7. `src/ai_infra/calculators/{mfu,kv_cache,memory}.py` + tests
8. `src/ai_infra/recommender.py` + tests
9. `scripts/gen_charts.py` + 6 张核心图表
10. `docs/mkdocs.yml` + 首页 + 第 6 章摘要
11. `src/ai_infra/api/main.py`
12. `web/` 首屏 + `/calculator`
13. `src/ai_infra/agent/` 工具层 + loop + trace
14. 报告生成器 + 部署 + 包装

**第一个里程碑：**

```bash
uv run ai-infra tco --gpus 64 --gpu h100 --years 3 --util 0.6
```

能输出：
- 成本结构表
- 3 年 TCO
- 每 GPUh
- 每百万 token
- 与云按需 / 1 年 / 3 年预留的对比
- 一句话结论

---

## 附录 A：工具接口草案

```python
from typing import Literal
from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    source: str
    as_of: str
    confidence: Literal["high", "medium", "low"] = "medium"


class CalcResult(BaseModel):
    value: dict
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: list[SourceRef] = Field(default_factory=list)
    trace_id: str


class TCOInput(BaseModel):
    gpu_id: str = "h100-sxm5-80gb"
    nodes: int = 8
    gpus_per_node: int = 8
    years: int = 3
    utilization: float = 0.6
    electricity_cny_per_kwh: float = 0.8
    pue: float = 1.2
    include_network: bool = True
    include_storage: bool = True
    include_labor: bool = True


def calc_tco(params: TCOInput) -> CalcResult: ...
```

```python
class MFUInput(BaseModel):
    model_id: str = "llama3-70b"
    gpu_id: str = "h100-sxm5-80gb"
    n_gpus: int = 64
    tp: int = 8
    pp: int = 1
    dp: int = 8
    batch_per_gpu: int = 1
    seq_len: int = 4096
    step_time_s: float | None = None
    tokens_per_sec: float | None = None
```

```python
class KVCacheInput(BaseModel):
    model_id: str = "llama3-70b"
    seq_len: int = 4096
    batch: int = 1
    dtype: Literal["fp16", "bf16", "fp8", "int8"] = "bf16"
    kv_heads: int | None = None
    head_dim: int | None = None
```

---

## 附录 B：Agent 评测样例

| # | 用户问题 | 期望工具 | 期望行为 |
|---|---|---|---|
| 1 | 64 张 H100，60% 利用率，3 年 TCO 多少？ | `calc_tco` | 直接计算，给出成本结构与假设 |
| 2 | 70B 模型 128K 上下文，单卡 H100 80G 能跑吗？ | `calc_kv_cache` + `calc_memory` | 回答不能，给出所需卡数和并发 |
| 3 | 预算 300 万，做客服 RAG，选什么？ | `recommend_config` + `calc_tco` | 先追问 QPS / SLO / 地区，再给 Top 3 |
| 4 | 字节和 DeepSeek 哪个适合我们？ | `compare_vendors` + `search_knowledge` | 追问行业/规模/合规，给出条件化结论 |
| 5 | 把利用率从 40% 调到 70%，成本怎么变？ | `calc_tco` 两次 | 展示前后对比与盈亏平衡 |
| 6 | 帮我写一个 CUDA kernel | 无 | 拒答，说明范围 |

---

> 本规划文档用于指导后续逐步生成。四个决策已确认，下一步从 P0 + P1 开始：仓库骨架 → Pydantic 模型 → `data/gpus.yaml` → `tco.py` → golden tests → `ai-infra tco` CLI。
