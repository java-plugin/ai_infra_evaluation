# 开发指南

## 环境要求

- Python 3.11+（推荐 3.12）
- Node.js 18+（推荐 20/22）
- uv（推荐）或 pip / venv

## 后端

### 安装

```bash
uv sync --extra dev
```

`dev` extra 包含 pytest / ruff / mypy / hypothesis / playwright。

如果不用 uv：

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
```

### 配置

复制 `.env.example` 为 `.env`：

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
AI_INFRA_DATA_DIR=./data
AI_INFRA_REPORT_DIR=./reports
```

`OPENAI_API_KEY` 可留空，Agent 会自动走 `_offline_answer()` 规则兜底。

### 启动

```bash
# 开发（自动重载）
uv run uvicorn ai_infra.api.main:app --reload --port 8000

# 或
uv run ai-infra tco --nodes 8 --gpus-per-node 8 --gpu h100-sxm5-80gb --years 3 --util 60
```

### 测试

```bash
uv run pytest -q                          # 全部
uv run pytest tests/golden -q             # 手算基准
uv run pytest tests/unit/test_api.py -q   # API 冒烟
```

测试覆盖：

- `tests/golden/test_tco.py`：8 节点 × 8 H100 / 3 年 / 60% 的手算基准；利用率单调性属性测试。
- `tests/unit/test_catalog.py`：数据目录加载、provenance 完整性。
- `tests/unit/test_rag.py`：表格行分块保留表头、三粒度生成、sqlite-vec 入库与整表回取。
- `tests/unit/test_api.py`：health / catalog / tools / knowledge / TCO / compare / MFU / memory / recommend / report / 路径穿越。

### Lint 与类型

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

## 前端

```bash
cd web
npm install
npm run dev      # http://localhost:3000
npm run build    # 生产构建（含类型检查）
npm run start    # 运行构建产物
```

### 连接后端

默认请求 `http://localhost:8000`。如果后端端口不同：

```bash
# macOS / Linux
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001 npm run dev

# Windows PowerShell
$env:NEXT_PUBLIC_API_BASE='http://127.0.0.1:8001'; npm run dev
```

注意：`NEXT_PUBLIC_*` 在 **build 时**内联，所以生产构建要重新设置并重新 build。

### 页面与组件

| 文件 | 说明 |
|---|---|
| `web/app/layout.tsx` | 全局布局、导航、页脚 |
| `web/components/nav.tsx` | 顶部导航 |
| `web/components/result-view.tsx` | 通用结果渲染：summary、成本结构、对比表、假设、警告、trace_id |
| `web/lib/api.ts` | 所有 HTTP 调用与 `CalcResult` 类型 |
| `web/app/calculator/page.tsx` | TCO / MFU / 显存 |
| `web/app/compare/page.tsx` | 有效每 GPUh 条形图 + 盈亏平衡 |
| `web/app/advisor/page.tsx` | 问卷、推荐、报告生成与 Markdown / PDF 下载 |
| `web/app/knowledge/page.tsx` | 书籍知识库检索：类型/章节过滤、命中行高亮、整表 JSON 渲染 |
| `web/app/agent/page.tsx` | 对话 + trace 面板 + 问答导出 PDF |

样式集中在 `web/app/globals.css` 的组件类：`.card`、`.label`、`.input`、`.btn`、`.btn-ghost`、`.badge`。

### PDF 导出

`src/ai_infra/pdf_export.py` 用 reportlab 排版，不依赖浏览器：

- 字体：按平台探测系统 CJK 字体（Windows 雅黑 / 苹方 / Noto CJK），找不到时回退到内置 `STSong-Light`，跨平台可用。
- 版式：A4 封面、编号章节、斑马表格、提示框、页眉、页脚与「第 N 页 / 共 M 页」两遍绘制。
- 内容：报告 PDF 复用同一份 Markdown；Agent PDF 由问题、回答、工具 trace 与工具输出附录组成，不重复调用 LLM。

单独验证：

```bash
uv run python -c "
from pathlib import Path
from ai_infra.pdf_export import export_markdown_pdf, platform_font_info
print(platform_font_info())
export_markdown_pdf('# 测试报告\n\n- 一行内容', Path('reports/_test.pdf'), subtitle='测试', meta_items=[('口径','v1')])
"
```

## 知识库（RAG）

### 语料与索引

| 路径 | 是否入库 | 说明 |
|---|---|---|
| `data/knowledge/corpus/chapters.jsonl` | 提交 | 章节正文（按小节切分），派生自原书，不含 PDF 原件 |
| `data/knowledge/corpus/tables.json` | 提交 | 表格 JSON：`table_id / chapter / section / title / headers / rows / page` |
| `data/knowledge/corpus/figures.json` | 提交 | 图注 |
| `data/knowledge/index.db` | 忽略 | 可由 corpus 重建的 sqlite-vec + FTS5 索引 |
| 原书 PDF | 忽略 | `*.pdf` 已在 `.gitignore`；只在本地抽取用 |

### 三步构建

```bash
# 1) 抽取：需要可选依赖（pdfplumber），只在本机跑
uv sync --extra rag-extract
uv run ai-infra rag extract --pdf D:/path/AI-Infra-全栈实战.pdf

# 2) 建索引：分块 → 嵌入 → sqlite-vec（原子替换 index.db）
uv run ai-infra rag build

# 3) 检索
uv run ai-infra rag search "字节跳动 GPU 总量" --top-k 3
uv run ai-infra rag search "私有化部署最低门槛" --chapter 第12章 --type table_row --detail
uv run ai-infra rag stats
```

### 分块策略（为什么按行解析）

表格是本项目问题最集中的地方，整表 embedding 会把「2,048 卡」「50-80 万元」这类单值稀释掉，
所以每张表同时生成三种粒度，三者共享 `table_id`，命中后按 `table_id` 回取整表 JSON：

| 类型 | 内容 | 作用 |
|---|---|---|
| `table_summary` | 表名 + 全部表头 + 行标签 + 前 3 行示例 | 语义召回「这张表讲什么」 |
| `table_row` | 单行，**每个值前都带表头字段名**（`对比维度: 最大集群规模｜字节: 10,000+ 卡｜…`） | 精确值召回，且不丢列语义 |
| `table_group` | 连续 3 行（同样带表头） | 跨行对比类问题 |

正文按句边界切 360 字、重叠 70 字，块前缀带「书名 + 章节」，避免脱离上下文。

### 检索融合

`hybrid` 模式同时跑向量 KNN 与 FTS5 BM25，用 RRF（`k=60`，vector 1.0 / keyword 0.9）融合，再乘：

- 类型权重：`table_row 1.55 / table_group 1.25 / table_summary 1.2 / text 1.0`
- 查询词覆盖率系数 `0.55 + 0.45 × coverage`
- 章标题命中加成 ×1.2（查询词能对上章名时，说明问的是这一章的主题）
- 候选池取 `max(top_k × 8, 40)`：正确行常常只在单路排到 10 名开外，池子太小会被截断

查询侧会做厂商别名归一（字节跳动→字节、阿里巴巴→阿里、腾讯云→腾讯、英伟达→NVIDIA）。

### 嵌入模型

默认 `HashingEmbedder`（512 维、CRC32 哈希技巧、L2 归一化）：不下载模型、离线可复现，适合 CI 与演示。
接入语义嵌入服务时设置：

```dotenv
AI_INFRA_EMBED_BASE_URL=https://api.deepseek.com/v1
AI_INFRA_EMBED_API_KEY=sk-...
AI_INFRA_EMBED_MODEL=bge-m3
```

改完重新 `ai-infra rag build`（维度变化会重建 `chunk_vec`）。

### 测试

`tests/unit/test_rag.py` 验证两条硬要求：

- 每个 `table_row` 块都包含全部表头字段名，且 `row_index` 能定位回原行；
- 表格以 JSON 入库，命中行块后可 `get_table()` 回取整表。

## 数据维护

`data/*.yaml` 是唯一数据源。新增条目必须包含：

```yaml
as_of: "2025-06"
source: "厂商公开规格 / 官方定价页"
confidence: "medium"
```

`catalog.py` 加载时：

- 校验 `as_of` 格式（`YYYY-MM` 或 `YYYY-MM-DD`）
- 用 `price_cny_min / max` 中位数补 `price_cny`
- 用 `num_kv_heads`、`active_params_billion` 补派生字段

修改数据后跑一次：

```bash
uv run pytest tests/unit/test_catalog.py -q
uv run ai-infra devices
```

## 调试

### 后端

```bash
# 查看某个请求的完整返回
curl -s -X POST http://localhost:8000/api/tco \
  -H "Content-Type: application/json" \
  -d '{"nodes":8,"gpus_per_node":8,"gpu_id":"h100-sxm5-80gb","years":3,"utilization_pct":60}' | python -m json.tool
```

### Agent

```bash
uv run python -c "
from ai_infra.agent.loop import run_agent
r = run_agent('64 张 H100，60% 利用率，3 年 TCO 多少？')
print(r.answer)
for s in r.trace:
    print(s.type, s.name, s.duration_ms, 'ms')
"
```

trace 里每一步都记录参数与输出，可以直接判断是「模型没选对工具」还是「工具参数错」还是「数据缺失」。

### 前端

浏览器 DevTools 看 Network 面板的 `/api/*` 响应；`ResultView` 会把 `assumptions`、`warnings`、`provenance` 全部展示出来。

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 端口 8000 被占用 | 已有服务在监听 | 换端口 `--port 8001`，同步设置 `NEXT_PUBLIC_API_BASE` |
| 前端请求 404 | `NEXT_PUBLIC_API_BASE` 指错 | 重新设置环境变量并重启 dev / 重新 build |
| Agent 返回「离线模式」 | 未配置 key 或 `.env` 不在仓库根 | 检查 `/healthz` 的 `llm_ready` |
| PowerShell 输出中文乱码 | 控制台编码 | 用 Python / 浏览器验证；或 `chcp 65001` |
| `python -m pytest` 找不到模块 | 未安装项目 | `uv sync` 或 `pip install -e .` |
| Playwright 报缺浏览器 | 版本不匹配 | `uv run playwright install chromium` |

## 提交前检查

```bash
uv run ruff check .
uv run mypy src tests
uv run pytest -q
npm --prefix web run build
```
