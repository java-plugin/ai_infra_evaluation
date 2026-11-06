"""命令行入口。

子命令:
    tco        算一台/一个集群的 TCO, 输出表格与云对比
    mfu        算 MFU
    memory     算显存
    compare    自建 vs 云各模式
    devices    列出数据目录里的 GPU / 模型
    rag        书籍知识库：抽取 / 建索引 / 检索 / 统计
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .calculators.compare import calc_compare
from .calculators.kv_cache import calc_kv_cache
from .calculators.memory import calc_memory
from .calculators.mfu import calc_mfu
from .calculators.recommender import WorkloadInput, recommend_config
from .calculators.tco import calc_tco
from .catalog import load_gpus, load_models
from .models import CalcResult, CompareInput, KVCacheInput, MemoryInput, MFUInput, TCOInput

app = typer.Typer(
    help="AI Infra Advisor — verifiable decision engine for AI infrastructure.",
    add_completion=False,
)
console = Console()


def _print_result(result: CalcResult, detail: bool) -> None:
    if not result.value:
        console.print("[red]计算失败 / 无结果[/red]")
        for w in result.warnings:
            console.print(f"  ! {w}")
        return

    summary = result.value.get("summary")
    if summary:
        console.print("[bold]结果[/bold]")
        for k, v in summary.items():
            if isinstance(v, float):
                console.print(f"  {k}: {v:,.2f}")
            else:
                console.print(f"  {k}: {v}")

    # 对比表
    rows = result.value.get("rows")
    if rows:
        tbl = Table(title="部署模式对比")
        for col in rows[0]:
            tbl.add_column(col, header_style="bold")
        for r in rows:
            tbl.add_row(*[str(v) for v in r.values()])
        console.print(tbl)

    # 假设 / 警告
    if result.assumptions:
        console.print("[bold green]假设:[/bold green]")
        for a in result.assumptions:
            console.print(f"  · {a}")
    if result.warnings:
        console.print("[bold yellow]警告:[/bold yellow]")
        for w in result.warnings:
            console.print(f"  ! {w}")

    if detail:
        console.print("[bold]原始值 (JSON)[/bold]")
        console.print(json.dumps(result.value, ensure_ascii=False, indent=2))


@app.command("tco")
def tco_cmd(
    nodes: int = typer.Option(8, help="节点数"),
    gpus_per_node: int = typer.Option(8, "--gpus-per-node", "-g", help="每节点 GPU 数"),
    gpu: str = typer.Option("h100-sxm5-80gb", help="GPU id (见 devices 命令)"),
    years: int = typer.Option(3, help="使用年限"),
    util: float = typer.Option(60.0, help="利用率 %% (5–100)"),
    price: float = typer.Option(0.8, help="电价 CNY/kWh"),
    pue: float = typer.Option(1.2, help="PUE"),
    tokens_per_sec: float | None = typer.Option(
        None, "--tokens-per-sec", help="可选, 算每百万 token 成本"
    ),
    detail: bool = typer.Option(False, "--detail", help="打印完整 JSON"),
) -> None:
    """算 TCO。"""

    params = TCOInput(
        nodes=nodes,
        gpus_per_node=gpus_per_node,
        gpu_id=gpu,
        years=years,
        utilization_pct=util,
        electricity_cny_per_kwh=price,
        pue=pue,
    )
    _print_result(calc_tco(params, tokens_per_sec=tokens_per_sec), detail)


@app.command("compare")
def compare_cmd(
    nodes: int = typer.Option(8),
    gpus_per_node: int = typer.Option(8, "--gpus-per-node"),
    gpu: str = typer.Option("h100-sxm5-80gb"),
    years: int = typer.Option(3),
    util: float = typer.Option(60.0),
) -> None:
    """自建 vs 云各模式对比。"""

    base = TCOInput(
        nodes=nodes,
        gpus_per_node=gpus_per_node,
        gpu_id=gpu,
        years=years,
        utilization_pct=util,
    )
    params = CompareInput(base=base)
    result = calc_compare(params)
    _print_result(result, detail=False)


@app.command("mfu")
def mfu_cmd(
    model: str = typer.Option("llama3-70b"),
    gpu: str = typer.Option("h100-sxm5-80gb"),
    n_gpus: int = typer.Option(64),
    tp: int = 8,
    pp: int = 1,
    dp: int = 8,
    seq: int = 4096,
    batch_per_gpu: int = 1,
    step_time: float | None = typer.Option(None, "--step-time", help="实测 step_time 秒"),
    tokens_per_sec: float | None = typer.Option(None, "--tokens-per-sec"),
    mode: str = typer.Option("training", "--mode", help="training / inference"),
) -> None:
    """算 MFU。"""

    params = MFUInput(
        model_id=model,
        gpu_id=gpu,
        n_gpus=n_gpus,
        tp=tp,
        pp=pp,
        dp=dp,
        mode=mode,
        seq_len=seq,
        batch_per_gpu=batch_per_gpu,
        step_time_s=step_time,
        tokens_per_sec=tokens_per_sec,
    )
    _print_result(calc_mfu(params), detail=False)


@app.command("memory")
def memory_cmd(
    model: str = typer.Option("llama3-70b"),
    gpu: str = typer.Option("h100-sxm5-80gb"),
    mode: str = typer.Option("inference"),
    tp: int = 8,
    seq: int = 4096,
    batch: int = 1,
    lora: bool = typer.Option(False),
) -> None:
    """算显存。"""

    params = MemoryInput(
        model_id=model,
        gpu_id=gpu,
        mode=mode,
        tp=tp,
        seq_len=seq,
        batch=batch,
        use_lora=lora,
    )
    _print_result(calc_memory(params), detail=False)


@app.command("kv-cache")
def kv_cache_cmd(
    model: str = typer.Option("llama3-70b"),
    seq: int = typer.Option(4096),
    batch: int = typer.Option(1),
    dtype: str = typer.Option("bf16"),
) -> None:
    """算 KV Cache。"""

    params = KVCacheInput(
        model_id=model,
        seq_len=seq,
        batch=batch,
        dtype=dtype,
    )
    _print_result(calc_kv_cache(params), detail=False)


@app.command("recommend")
def recommend_cmd(
    business: str = typer.Option("general", help="业务类型"),
    model_size: float = typer.Option(7.0, "--model-size"),
    qps: float = typer.Option(100.0),
    privacy: str = typer.Option("low", "--privacy", help="none/low/high/max"),
    team_size: int = typer.Option(5),
) -> None:
    """推荐选型。"""

    wl = WorkloadInput(
        business_type=business,
        model_size_billion=model_size,
        qps=qps,
        privacy_need=privacy,
        team_size=team_size,
    )
    _print_result(recommend_config(wl), detail=False)


@app.command("devices")
def devices_cmd() -> None:
    """列出数据目录中的 GPU 和模型。"""

    gpus = load_gpus()
    models = load_models()
    console.print(f"[bold]GPUs ({len(gpus)})[/bold]")
    for g in gpus.values():
        price = g.price_cny or g.price_cny_min or "?"
        console.print(
            f"  {g.id:<25} {g.memory_gb:>5} GB  TDP {g.tdp_w:>4}W  ¥{price:>10,.0f}  (as_of {g.as_of})"
        )
    console.print(f"[bold]Models ({len(models)})[/bold]")
    for m in models.values():
        extra = ""
        if m.is_moe:
            extra = f" MoE active={m.active_params_billion:.1f}B"
        console.print(
            f"  {m.id:<25} {m.params_billion:>6.1f}B  L={m.num_layers}  H={m.hidden_size}{extra}"
        )


rag_app = typer.Typer(help="书籍知识库：抽取、建索引、检索。", add_completion=False)
app.add_typer(rag_app, name="rag")


@rag_app.command("extract")
def rag_extract_cmd(
    pdf: Annotated[Path, typer.Option("--pdf", help="原书 PDF 路径（仅本地使用，不入库）")],
    out: Annotated[Path, typer.Option("--out", help="语料输出目录")] = Path(
        "data/knowledge/corpus"
    ),
) -> None:
    """从 PDF 抽取章节正文与表格 JSON。"""

    from .rag.extract import extract_pdf

    try:
        stats = extract_pdf(pdf, out)
    except ImportError as exc:  # pragma: no cover - 缺少可选依赖时
        console.print(f"[red]缺少依赖：{exc}[/red] 请安装 pdfplumber")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]抽取完成[/green] → {out}")
    for key, value in stats.items():
        console.print(f"  {key}: {value}")


@rag_app.command("build")
def rag_build_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="索引文件路径，默认 data/knowledge/index.db")
    ] = None,
) -> None:
    """建/重建向量索引。"""

    from .rag.build import build_index

    stats = build_index(db_path=db)
    console.print("[green]索引构建完成[/green]")
    console.print(f"  chunks: {stats.chunks}  tables: {stats.tables}  embedding: {stats.embedding}")
    console.print(f"  类型分布: {stats.doc_type_counts}")


@rag_app.command("search")
def rag_search_cmd(
    query: str = typer.Argument(..., help="自然语言问题"),
    top_k: int = typer.Option(5, "--top-k"),
    mode: str = typer.Option("hybrid", "--mode", help="hybrid / vector / keyword"),
    doc_type: str = typer.Option("", "--type", help="text / table_row / table_summary / table_group"),
    chapter: str = typer.Option("", "--chapter", help="限定章节，如 第12章"),
    detail: bool = typer.Option(False, "--detail", help="打印完整 JSON（含整表）"),
) -> None:
    """检索知识库。"""

    from .rag.search import search_knowledge

    hits = search_knowledge(
        query,
        top_k,
        mode=mode,
        doc_type=doc_type or None,
        chapter=chapter or None,
    )
    if not hits:
        console.print("[yellow]没有命中，请确认已执行 rag build[/yellow]")
        return
    for i, hit in enumerate(hits, 1):
        console.print(
            f"[bold]{i}. {hit['title']}[/bold] "
            f"[dim]({hit['doc_type']} · {hit['chapter']} · score {hit['score']})[/dim]"
        )
        console.print(f"   {hit['text'][:220]}")
        console.print(f"   [dim]{hit['source']} · p{hit['page']}[/dim]")
        if detail:
            console.print(json.dumps(hit, ensure_ascii=False, indent=2))


@rag_app.command("stats")
def rag_stats_cmd() -> None:
    """查看索引统计。"""

    from .rag.build import index_path
    from .rag.store import VectorStore

    path = index_path()
    if not path.is_file():
        console.print(f"[yellow]索引不存在：{path}，先执行 rag build[/yellow]")
        return
    store = VectorStore(path)
    try:
        stats = store.stats()
        meta = store.meta()
    finally:
        store.close()
    table = Table(title=f"知识库索引 {path}")
    table.add_column("指标")
    table.add_column("值")
    table.add_row("chunks", str(stats.chunks))
    table.add_row("tables", str(stats.tables))
    table.add_row("embedding", stats.embedding)
    table.add_row("dim", str(stats.dim))
    for key, value in stats.doc_type_counts.items():
        table.add_row(f"  {key}", str(value))
    table.add_row("built_at", meta.get("built_at", ""))
    table.add_row("chapters", ", ".join(stats.chapters))
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
