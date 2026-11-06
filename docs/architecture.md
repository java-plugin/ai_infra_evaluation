# 架构

## 设计目标

1. **数字可复算**：任何界面 / Agent / 报告里的数字，都必须能定位到某个 Python 函数和某条数据来源。
2. **LLM 不碰算术**：模型只做意图理解、参数补全、工具选择与解释。
3. **口径强约束**：用 Pydantic `extra="forbid"` 禁止字段混用，节点数与 GPU 数必须分开。
4. **离线可降级**：没有 LLM key 时，计算器、对比、报告仍然完整可用。

## 分层

```text
┌──────────────────────────────────────────────────────────┐
│  Presentation                                            │
│  Next.js 14 (App Router)                                  │
│  /  /calculator  /compare  /advisor  /knowledge  /agent   │
└───────────────▲──────────────────────────────────────────┘
                │ JSON over HTTP (CORS: localhost:3000)
┌───────────────┴──────────────────────────────────────────┐
│  Interface                                               │
│  FastAPI (src/ai_infra/api/main.py)                      │
│  /api/tco /api/compare /api/mfu /api/memory ...          │
│  /api/knowledge/{search,stats,tables}                    │
│  /api/agent/chat  /api/report                            │
└───────────────▲──────────────────────────────────────────┘
                │
┌───────────────┴──────────────────────────────────────────┐
│  Orchestration                                           │
│  Agent loop (agent/loop.py)                              │
│  Tool dispatch (agent/tools.py)  Trace (agent/trace.py)  │
│  RAG 检索（rag/{extract,chunker,build,search,store}.py）  │
└───────────────▲──────────────────────────────────────────┘
                │
┌───────────────┴──────────────────────────────────────────┐
│  Deterministic Core                                      │
│  calculators/{tco,compare,mfu,kv_cache,memory,recommender}│
│  统一返回 CalcResult(value / assumptions / warnings /     │
│  provenance / trace_id)                                  │
└───────────────▲──────────────────────────────────────────┘
                │
┌───────────────┴──────────────────────────────────────────┐
│  Data                                                    │
│  data/gpus.yaml  data/models.yaml                        │
│  data/knowledge/cards.yaml                               │
│  data/knowledge/corpus/{chapters.jsonl,tables.json,...}   │
│  data/knowledge/index.db（sqlite-vec + FTS5，可重建）      │
│  每条记录带 source / as_of / confidence                   │
└──────────────────────────────────────────────────────────┘
```

## 数据流

### 计算请求

```text
Browser form
  → POST /api/tco (TCOInput)
  → _safe_calc → calc_tco()
  → get_gpu() 读取 data/gpus.yaml（校验 provenance）
  → CalcResult
  → JSON 返回前端
  → ResultView：summary / 成本结构 / 假设 / 警告 / trace_id / 来源
```

失败时：`calc_tco` 内部把 `CatalogError` 转成空 `value` + warning；API 层统一把空结果转成 HTTP 400。
所以前端只会看到「400 + 可读原因」，不会看到半截结果。

### Agent 请求

```text
POST /api/agent/chat {message, history}
  → run_agent()
  → 构造 system prompt（注入当前数据目录中的 GPU / 模型 id）
  → DeepSeek chat.completions(tools=TOOL_SCHEMAS)
  → 若返回 tool_calls：
       dispatch_tool(name, args)
         → 参数别名归一化（h100 → h100-sxm5-80gb）
         → 调用确定性计算器
         → 返回 {ok, result} 或 {ok:false, error}
       trace.tool(...)
       把 tool result 回填 messages
  → 最多 5 轮
  → 最终自然语言回答 + 完整 trace
```

关键不变量：

- `dispatch_tool` **永远**返回 dict，不抛出异常，方便模型看到错误后自我修正。
- 工具输出被裁剪（`_compact`），只暴露 summary / rows / reasons / breakdown / assumptions / warnings / provenance，避免把大对象塞进上下文。
- trace 记录 LLM 轮次、工具名、参数、耗时、错误；前端右侧面板可回放。

### 报告

```text
POST /api/report {tco, model_id, tokens_per_sec}
  → calc_tco + calc_compare
  → 可选 calc_memory / calc_kv_cache / calc_mfu
  → 渲染 8 段 Markdown
  → 写入 reports/report-YYYYMMDD-HHMMSS.md
  → 返回 {markdown, filename, download_url}
```

### 知识库构建与检索

```text
原书 PDF（仅本地，不入库）
  → rag extract（pdfplumber）
      按页读文本行 + find_tables()
      表格单元格 → headers/rows JSON；跨页重复表头去重
  → data/knowledge/corpus/{chapters.jsonl,tables.json,figures.json}（提交）
  → rag build
      正文按句切 360/70；每张表拆 summary / row / group 三粒度（行块带表头字段名）
      嵌入（HashingEmbedder 或 OpenAI-compatible /embeddings）
      写入 .db.tmp 后原子替换 index.db
  → rag search(query)
      vector KNN（vec0，doc_type/chapter 过滤）+ FTS5 BM25
      RRF 融合 + 类型权重 + 词面覆盖率 + 章标题加成
      命中表格块时按 table_id 回取整表 JSON
```

Agent 的 `search_knowledge` 工具与前端 `/knowledge` 页面共用同一套检索函数；
索引缺失时 `agent/rag.py` 自动回退到 `cards.yaml` 精编卡片，接口结构不变。

## 模块职责

| 模块 | 职责 | 不做什么 |
|---|---|---|
| `models.py` | 输入/输出 schema，单位后缀，范围校验 | 不读数据、不算数 |
| `catalog.py` | 加载 YAML、补派生字段、校验 provenance | 不做业务计算 |
| `calculators/*` | 纯函数式计算 | 不访问网络、不读写文件（报告除外） |
| `agent/tools.py` | 工具白名单 + 参数归一化 + 错误包装 | 不直接拼自然语言 |
| `agent/loop.py` | LLM 多轮循环、system prompt、离线兜底 | 不实现任何公式 |
| `rag/extract.py` | PDF → 章节正文与表格 JSON（仅本机执行） | 不提交 PDF 原件 |
| `rag/chunker.py` | 正文切块 + 表格三粒度分块（行块保留表头） | 不做嵌入、不写库 |
| `rag/store.py` | sqlite-vec + FTS5 读写、元数据过滤 | 不决定排序策略 |
| `rag/search.py` | 混合召回、RRF 融合、权重与章节解析 | 不直接面向 HTTP |
| `rag/embedding.py` | 哈希嵌入 / OpenAI-compatible 嵌入 | 不感知语料结构 |
| `api/main.py` | HTTP 协议、CORS、错误映射 | 不包含业务逻辑 |
| `report.py` | 报告模板与文件落盘 | 不重新实现公式，只调用计算器 |
| `web/*` | 表单、图表、trace 面板 | 不复制任何计算公式 |

## 扩展点

### 新增计算器

1. 在 `models.py` 定义 `XxxInput`（`extra="forbid"`，字段带单位）。
2. 在 `calculators/xxx.py` 实现 `calc_xxx(params) -> CalcResult`。
3. 在 `api/main.py` 增加 `POST /api/xxx`。
4. 在 `agent/tools.py` 增加 dispatch 分支与 `TOOL_SCHEMAS`。
5. 在 `tests/` 增加 golden 手算基准。
6. 前端复用 `ResultView`，必要时补 `LABELS`。

### 新增数据

只改 YAML，不改代码。新增 GPU / 模型必须带 `source / as_of / confidence`，
否则 `catalog.load_gpus()/load_models()` 会拒绝加载。

### 新增知识语料

1. 本地 `ai-infra rag extract --pdf ...` 重新抽取（不提交 PDF），或直接编辑 `data/knowledge/corpus/*.json`。
2. `ai-infra rag build` 重建索引；`.db` 不入库，协作者拉代码后自行构建。
3. 调整检索效果时改 `rag/search.py` 的 `TYPE_WEIGHT` / `CHAPTER_BOOST`，跑 `tests/unit/test_rag.py`。

## 已知边界

- 云价格是静态参考值（`compare.py` 顶部常量），不是实时报价。
- `memory.py` 中 ZeRO 1/2/3 目前是简化处理，只作为量级估算，不替代实测。
- MoE 的通信与专家并行开销只做了经验系数，不是精确建模。
- 默认哈希嵌入只做词面级语义（bigram 哈希），跨义项改写（如「贵不贵」→「成本」）依赖 BM25 与其共现；生产环境建议切换到真实 embedding 服务。
- 原书图表目前仅保留图注文本（`figure` 块），尚未做多模态图像理解。
