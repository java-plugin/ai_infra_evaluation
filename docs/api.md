# API

Base URL：`http://localhost:8000`

交互式文档：`/docs`（Swagger UI）、`/redoc`。

## 统一返回结构

所有计算端点返回 `CalcResult`：

```json
{
  "value": {
    "summary": { "tco_total_cny": 19986525.44, "per_gpu_hour_cny": 19.8053 },
    "...": "其余明细"
  },
  "assumptions": ["GPU: h100-sxm5-80gb ...", "规模: 8 节点 × 8 GPU = 64 GPU ..."],
  "warnings": ["GPU 价格取中位数 ¥225,000 (区间 ¥200,000 – ¥250,000)"],
  "provenance": [
    {
      "source": "data/gpus.yaml#h100-sxm5-80gb",
      "as_of": "2025-06",
      "confidence": "medium",
      "note": null
    }
  ],
  "trace_id": "tr_db5bedf7d71f"
}
```

约定：

- `value` 为空对象表示计算失败；API 层会转成 HTTP 400，`detail` 为 warnings 拼接。
- `trace_id` 每次请求自动生成，可用于日志关联。
- 所有金额单位是 CNY；`per_gpu_hour_cny` 的分母是**有效 GPU 小时**（含利用率）。

## 基础

### GET `/healthz`

```json
{ "status": "ok", "llm_ready": true, "model": "deepseek-chat" }
```

`llm_ready=false` 时 Agent 走规则兜底模式。

### GET `/api/catalog`

返回 `gpus` 与 `models` 全量记录。前端用它填充下拉框。

### GET `/api/agent/tools`

返回 OpenAI function-calling schema 列表（7 个工具）。

### GET `/api/knowledge/search?q=KV Cache&top_k=5`

书籍知识库检索（正文 + 表格 + 图表分块），默认走混合检索：

| 参数 | 默认 | 说明 |
|---|---|---|
| `q` | 必填 | 自然语言问题 |
| `top_k` | 5 | 1–20 |
| `mode` | `hybrid` | `hybrid` / `vector` / `keyword` |
| `doc_type` | 空 | `text` / `table_row` / `table_summary` / `table_group` / `figure` |
| `chapter` | 空 | 章节过滤，支持前缀，如 `第12章` |

```json
{
  "query": "四大厂商集群规模对比",
  "results": [
    {
      "chunk_id": "t12-260-r01",
      "doc_type": "table_row",
      "chapter": "第12章 四大厂商对照表与选型指南",
      "section": "12.2 硬件选型对比表（详细参数对比）",
      "title": "12.2 硬件选型对比表（详细参数对比）",
      "text": "12.2 硬件选型对比表（详细参数对比）｜对比维度: 最大集群规模｜字节: 10,000+ 卡｜阿里: 5,000+ 卡",
      "score": 3.505,
      "vector_score": 0.39,
      "keyword_score": 40.5,
      "source": "《AI Infra 全栈实战》第12章 ...",
      "page": 260,
      "row": { "对比维度": "最大集群规模", "字节": "10,000+ 卡", "阿里": "5,000+ 卡" },
      "table": { "table_id": "t12-260", "headers": ["对比维度", "字节", "阿里"], "rows": [ ... ] }
    }
  ]
}
```

索引尚未构建时自动回退到 `data/knowledge/cards.yaml` 的精编卡片（`doc_type` 为 `text`、`chapter` 为「知识卡片」），返回结构保持一致。

### GET `/api/knowledge/stats`

```json
{
  "ready": true,
  "stats": {
    "doc_type_counts": { "text": 1187, "table_row": 1573, "table_summary": 315, "table_group": 638 },
    "chapters": ["第1章 ...", "第2章 ..."],
    "tables": 315,
    "chunks": 3713,
    "embedding": "hashing-512",
    "dim": 512,
    "meta": { "built_at": "2026-11-05 03:25:23", "corpus_dir": "..." }
  }
}
```

索引未构建时返回 `{ "ready": false }`。

### GET `/api/knowledge/tables/{table_id}`

按 `table_id` 回取整表 JSON（`headers` + `rows`），供前端渲染或复核检索命中。不存在返回 404。

## 计算

### POST `/api/tco`

```bash
curl -X POST http://localhost:8000/api/tco \
  -H "Content-Type: application/json" \
  -d '{
    "nodes": 8,
    "gpus_per_node": 8,
    "gpu_id": "h100-sxm5-80gb",
    "years": 3,
    "utilization_pct": 60,
    "electricity_cny_per_kwh": 0.8,
    "pue": 1.2,
    "residual_value_pct": 5
  }'
```

字段：

| 字段 | 默认 | 说明 |
|---|---|---|
| `nodes` | 必填 | 物理节点数 |
| `gpus_per_node` | 必填 | 每节点 GPU 数 |
| `gpu_id` | 必填 | 必须是 `data/gpus.yaml` 中的 id |
| `years` | 3 | 1–10 |
| `utilization_pct` | 60 | 5–100 |
| `electricity_cny_per_kwh` | 0.8 | > 0 |
| `pue` | 1.2 | 1.0–2.5 |
| `include_network/storage/labor/software` | true | 成本项开关 |
| `colocation_fee_cny_per_node_per_month` | 0 | 托管费 |
| `colocation_includes_power` | false | true 时不再单独计电费 |
| `residual_value_pct` | 0 | 残值比例 |
| `gpu_price_cny` | null | 手动覆盖 GPU 单价 |

`value` 包含 `summary`、`cost_structure_pct` 以及 `TCOBreakdown` 的全部字段。

### POST `/api/compare`

```json
{ "base": { "nodes": 8, "gpus_per_node": 8, "gpu_id": "h100-sxm5-80gb", "years": 3, "utilization_pct": 60 } }
```

`value.rows[]` 每行：

| 字段 | 说明 |
|---|---|
| `mode` | 自建 / 云按需 / 云 1 年预留 / 云 3 年预留 / 云 Spot / 按月租赁 |
| `per_gpu_hour_cny` | 名义每 GPUh |
| `effective_per_gpu_hour_cny` | 有效每 GPUh；Spot = 名义价 / 0.30 |
| `tco_cny` | 该方案总成本 |
| `notes` | 口径说明 |

`value.break_even_util_pct` 为各云模式对应的盈亏平衡利用率（5% 步长搜索）。

### POST `/api/mfu`

```json
{
  "model_id": "llama3-70b",
  "gpu_id": "h100-sxm5-80gb",
  "n_gpus": 64,
  "tp": 8, "pp": 1, "dp": 8, "ep": 1,
  "mode": "inference",
  "seq_len": 4096,
  "batch_per_gpu": 1
}
```

可选 `step_time_s` 或 `tokens_per_sec` 进入实测模式；都不传时按经验 MFU 反推估算。

### POST `/api/kv-cache`

```json
{ "model_id": "llama3-70b", "seq_len": 131072, "batch": 1, "dtype": "bf16", "n_gpus": 8 }
```

### POST `/api/memory`

```json
{
  "model_id": "llama3-70b", "gpu_id": "h100-sxm5-80gb",
  "mode": "training", "tp": 8, "batch": 1, "seq_len": 4096,
  "use_lora": true, "lora_rank": 8, "gradient_checkpointing": true
}
```

`value.summary` 含 `total_gb`、`hbm_gb`、`utilization_pct`、`oom_risk`。

### POST `/api/recommend`

```json
{
  "business_type": "customer_service",
  "model_size_billion": 70,
  "qps": 200,
  "ttft_slo_ms": 3000,
  "tpot_slo_ms": 50,
  "privacy_need": "high",
  "team_size": 3,
  "budget_cny_per_year": 3000000
}
```

`value.summary`：

```json
{
  "recommended_gpu": "h100-sxm5-80gb",
  "recommended_nodes": 2,
  "recommended_gpus_per_node": 8,
  "cheapest_mode": "云 3 年预留",
  "cheapest_per_gpu_hour_cny": 12.0
}
```

`cheapest_mode` 按**有效**每 GPUh 选择，Spot 不会因名义低价被误判。

## Agent

### POST `/api/agent/chat`

```json
{
  "message": "64 张 H100，60% 利用率，3 年 TCO 多少？",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

响应：

```json
{
  "answer": "## 结论 ...",
  "trace": [
    { "type": "llm", "name": "deepseek-chat", "content": null, "tool_names": ["calc_tco"], "duration_ms": 2069 },
    { "type": "tool", "name": "calc_tco", "args": { "nodes": 8, "...": "..." }, "output": {...}, "duration_ms": 13 },
    { "type": "llm", "name": "deepseek-chat", "content": "...", "duration_ms": 4852 }
  ],
  "elapsed_ms": 9121,
  "model": "deepseek-chat",
  "llm_used": true
}
```

`history` 只取最近 8 条，每条截断到 2000 字符。

### POST `/api/agent/export`

把一次问答导出为 PDF 技术方案（不重复调用 LLM，直接排版前端已经拿到的内容）：

```json
{
  "question": "64 张 H100，60% 利用率，3 年 TCO 多少？",
  "answer": "## 结论 ...",
  "trace": [ { "type": "tool", "name": "calc_tco", "args": {...}, "output": {...}, "duration_ms": 13 } ],
  "model": "deepseek-chat",
  "elapsed_ms": 9121,
  "trace_id": "tr_xxx"
}
```

响应：

```json
{ "filename": "proposal-20261104-221530.pdf", "download_url": "/api/report/proposal-20261104-221530.pdf" }
```

PDF 结构：封面 → 一、问题背景 → 二、结论与建议 → 三、计算过程与工具调用 → 四、关键假设与复算说明（含数据来源） → 五、风险与边界 → 附录 A 工具输出明细。

## 报告

### POST `/api/report`

```json
{ "tco": { "nodes": 8, "gpus_per_node": 8, "gpu_id": "h100-sxm5-80gb", "years": 3, "utilization_pct": 60 }, "model_id": "llama3-70b" }
```

```json
{
  "markdown": "# AI Infra 选型与成本报告 ...",
  "filename": "report-20261104-183000.md",
  "download_url": "/api/report/report-20261104-183000.md",
  "pdf_filename": "report-20261104-183000.pdf",
  "pdf_download_url": "/api/report/report-20261104-183000.pdf"
}
```

Markdown 与 PDF 由同一份内容生成：Markdown 便于审阅与二次编辑，PDF 用于对外交付（A4 封面、编号章节、表格、页眉页脚与页码）。

报告写入 `reports/`（已被 `.gitignore` 忽略）。

### GET `/api/report/{filename}`

下载报告。`.md` 返回 `text/markdown`，`.pdf` 返回 `application/pdf`。做了目录穿越防护，非法路径返回 404。

## 错误码

| 状态 | 场景 |
|---|---|
| 400 | 参数校验失败、未知 GPU/模型、计算结果为空 |
| 404 | 报告不存在 |
| 500 | 计算器内部异常（会带异常类型与信息） |
| 422 | FastAPI 请求体 schema 校验失败 |
