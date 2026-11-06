"""HTTP API。

所有计算端点都复用同一套确定性计算器，返回结构包含
``assumptions / warnings / provenance / trace_id``。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..agent.loop import AgentResponse, run_agent
from ..agent.tools import TOOL_SCHEMAS
from ..agent.trace import TraceStep
from ..calculators.compare import calc_compare
from ..calculators.kv_cache import calc_kv_cache
from ..calculators.memory import calc_memory
from ..calculators.mfu import calc_mfu
from ..calculators.recommender import WorkloadInput, recommend_config
from ..calculators.tco import calc_tco
from ..catalog import CatalogError, load_gpus, load_models
from ..config import get_settings
from ..models import (
    CalcResult,
    CompareInput,
    KVCacheInput,
    MemoryInput,
    MFUInput,
    TCOInput,
)
from ..pdf_export import export_agent_pdf
from ..rag.search import get_table as get_knowledge_table
from ..rag.search import knowledge_stats, search_knowledge
from ..report import ReportRequest, generate_report, generate_report_pdf

app = FastAPI(
    title="AI Infra Advisor API",
    version="0.1.0",
    description=(
        "Deterministic AI Infra calculators + tool-using agent. "
        "Every number carries assumptions, warnings and provenance."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    s = get_settings()
    return {
        "status": "ok",
        "llm_ready": s.llm_ready,
        "model": s.openai_model if s.llm_ready else "offline",
    }


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    gpus = load_gpus()
    models = load_models()
    return {
        "gpus": [g.model_dump() for g in gpus.values()],
        "models": [m.model_dump() for m in models.values()],
    }


@app.get("/api/agent/tools")
def agent_tools() -> list[dict[str, Any]]:
    return TOOL_SCHEMAS


@app.get("/api/knowledge/search")
def knowledge_search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
    mode: str = Query("hybrid", pattern="^(hybrid|vector|keyword)$"),
    doc_type: str = Query("", description="text / table_row / table_summary / table_group / figure"),
    chapter: str = Query("", description="章节过滤，如「第12章」"),
) -> dict[str, Any]:
    results = search_knowledge(
        q,
        top_k,
        mode=mode,
        doc_type=doc_type or None,
        chapter=chapter or None,
    )
    return {"query": q, "results": results}


@app.get("/api/knowledge/stats")
def knowledge_stats_api() -> dict[str, Any]:
    stats = knowledge_stats()
    if stats is None:
        return {"ready": False}
    return {"ready": True, "stats": stats}


@app.get("/api/knowledge/tables/{table_id}")
def knowledge_table(table_id: str) -> dict[str, Any]:
    table = get_knowledge_table(table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="表格不存在")
    return table


# ---------------------------------------------------------------------------
# 计算
# ---------------------------------------------------------------------------


def _safe_calc(fn: Callable[..., CalcResult], *args: Any, **kwargs: Any) -> CalcResult:
    try:
        result = fn(*args, **kwargs)
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    if not result.value:
        detail = "; ".join(result.warnings) or "计算失败：无结果"
        raise HTTPException(status_code=400, detail=detail)
    return result


@app.post("/api/tco")
def api_tco(params: TCOInput) -> CalcResult:
    return _safe_calc(calc_tco, params)


@app.post("/api/compare")
def api_compare(params: CompareInput) -> CalcResult:
    return _safe_calc(calc_compare, params)


@app.post("/api/mfu")
def api_mfu(params: MFUInput) -> CalcResult:
    return _safe_calc(calc_mfu, params)


@app.post("/api/kv-cache")
def api_kv_cache(params: KVCacheInput) -> CalcResult:
    return _safe_calc(calc_kv_cache, params)


@app.post("/api/memory")
def api_memory(params: MemoryInput) -> CalcResult:
    return _safe_calc(calc_memory, params)


@app.post("/api/recommend")
def api_recommend(params: WorkloadInput) -> CalcResult:
    return _safe_calc(recommend_config, params)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list)


@app.post("/api/agent/chat")
def api_agent_chat(req: AgentChatRequest) -> AgentResponse:
    return run_agent(req.message, req.history)


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


@app.post("/api/report")
def api_report(req: ReportRequest) -> dict[str, Any]:
    try:
        markdown, path = generate_report(req)
        pdf_path = generate_report_pdf(markdown, path, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - PDF 渲染失败不应影响 Markdown 产出
        raise HTTPException(
            status_code=500, detail=f"PDF 渲染失败 {type(exc).__name__}: {exc}"
        ) from exc
    return {
        "markdown": markdown,
        "filename": path.name,
        "download_url": f"/api/report/{path.name}",
        "pdf_filename": pdf_path.name,
        "pdf_download_url": f"/api/report/{pdf_path.name}",
    }


class AgentExportRequest(BaseModel):
    """Agent 问答导出请求：前端回传已生成的回答与轨迹，不重复调用 LLM。"""

    question: str = Field(..., min_length=1, max_length=4000)
    answer: str = Field(..., min_length=1)
    trace: list[TraceStep] = Field(default_factory=list)
    model: str = ""
    elapsed_ms: int = 0
    trace_id: str | None = None


@app.post("/api/agent/export")
def api_agent_export(req: AgentExportRequest) -> dict[str, str]:
    out_dir = get_settings().report_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"proposal-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    path = export_agent_pdf(
        question=req.question,
        answer=req.answer,
        trace=req.trace,
        out_path=out_dir / name,
        model=req.model,
        elapsed_ms=req.elapsed_ms,
        trace_id=req.trace_id,
    )
    return {
        "filename": path.name,
        "download_url": f"/api/report/{path.name}",
    }


@app.get("/api/report/{filename}")
def api_report_download(filename: str) -> FileResponse:
    report_dir = get_settings().report_dir
    path = (report_dir / filename).resolve()
    # 防目录穿越
    if report_dir.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="报告不存在")
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "text/markdown"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AI Infra Advisor API",
        "docs": "/docs",
        "health": "/healthz",
    }
