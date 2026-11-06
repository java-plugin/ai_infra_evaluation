"""Agent 主循环。

LLM 负责：意图识别、参数补全、选择工具、解释结果。
LLM 不负责：任何算术、任何价格记忆。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import get_settings
from .tools import TOOL_SCHEMAS, dispatch_tool
from .trace import TraceRecorder, TraceStep


class AgentResponse(BaseModel):
    answer: str
    trace: list[TraceStep] = Field(default_factory=list)
    elapsed_ms: int = 0
    model: str = ""
    llm_used: bool = False


def _system_prompt() -> str:
    from ..catalog import load_gpus, load_models

    gpus = ", ".join(load_gpus().keys())
    models = ", ".join(load_models().keys())
    return f"""你是 AI Infra Advisor，一个严谨的 AI 基础设施选型顾问。

可用 GPU: {gpus}
可用模型: {models}

规则（必须遵守）:
1. 任何 TCO、每 GPU 小时成本、MFU、显存、KV Cache 数字，必须调用工具计算，禁止自己心算或估算。
2. 涉及厂商架构、集群规模、GPU/云价格区间、行业案例、选型对照时，先调用 `search_knowledge` 检索书籍知识库；
   引用时标注章节与页码，表格数据以工具返回的 JSON 为准。
3. 用户缺少参数时，最多追问 2 个最关键的问题；能合理默认的先默认，并在回答中标注假设。
4. 回答结构固定为：结论 / 关键假设 / 计算依据 / 风险与边界 / 来源。
5. 不得编造 GPU 价格、云价格或厂商报价；价格只引用工具返回的 provenance 和 as_of。
6. 如果工具报错，先修正参数重试一次；仍失败则如实说明。
7. 超出 AI Infra 选型/成本/性能范围的问题，直接说明边界。
8. 用中文回答，简洁、具体、可执行。"""


def _parse_int(pattern: str, text: str, default: int | None = None) -> int | None:
    m = re.search(pattern, text)
    if not m:
        return default
    try:
        return int(m.group(1))
    except (ValueError, IndexError):
        return default


def _offline_answer(message: str) -> str:
    """无 LLM 时的规则兜底：至少让 TCO/显存/KV 能算。"""

    from .tools import dispatch_tool

    text = message.lower()
    total_gpus = _parse_int(r"(\d+)\s*(?:张|卡|块|gpu)", text)
    nodes = max(1, total_gpus // 8) if total_gpus else 8
    gpus_per_node = 8
    util = _parse_int(r"(\d+)\s*%", text, 60)
    years = _parse_int(r"(\d+)\s*年", text, 3)

    gpu = "h100-sxm5-80gb"
    for alias in ("h100", "h800", "a100", "l40s", "910b"):
        if alias in text:
            gpu = alias
            break

    if any(k in text for k in ("tco", "成本", "多少钱", "费用", "预算")):
        r = dispatch_tool(
            "calc_tco",
            {
                "nodes": nodes,
                "gpus_per_node": gpus_per_node,
                "gpu_id": gpu,
                "years": years,
                "utilization_pct": util,
            },
        )
        if not r.get("ok"):
            return f"离线模式计算失败：{r.get('error')}"
        s = r["result"]["summary"]
        return (
            f"**结论**：{s['gpu_count']} 张 {s['gpu_model']}，{s['years']} 年、利用率 {s['utilization_pct']}% 的 TCO 约 "
            f"¥{s['tco_total_cny']:,.0f}，每 GPU 小时约 ¥{s['per_gpu_hour_cny']:.2f}。\n\n"
            f"**关键假设**：电价 ¥0.8/kWh，PUE 1.2，含网络/存储/人力/软件，GPU 价格取数据目录中位数。\n\n"
            f"**计算依据**：调用 `calc_tco`，公式为 TCO = CapEx + OpEx×年限 + 隐藏成本 - 残值。\n\n"
            f"**风险与边界**：价格随供需波动；未考虑迁移、调试和故障损失。\n\n"
            f"**来源**：{', '.join(p['source'] for p in r['result']['provenance'])}"
        )

    if "kv" in text or "上下文" in text:
        seq = _parse_int(r"(\d+)\s*k", text, 4) or 4
        seq_len = seq * 1024 if seq < 1000 else seq
        model = "llama3-70b"
        if "8b" in text:
            model = "llama3-8b"
        elif "deepseek" in text or "671" in text:
            model = "deepseek-v3-671b"
        r = dispatch_tool("calc_kv_cache", {"model_id": model, "seq_len": seq_len, "batch": 1})
        if not r.get("ok"):
            return f"离线模式计算失败：{r.get('error')}"
        s = r["result"]["summary"]
        return (
            f"**结论**：{model} 在 {seq_len} 上下文、batch=1 时，KV Cache 约 {s['kv_per_request_mb']:.1f} MB，"
            f"单 token 约 {s['kv_per_token_bytes']:.0f} B。\n\n"
            f"**关键假设**：BF16、页式开销 5%、不含权重与激活。\n\n"
            f"**风险与边界**：实际还要叠加权重、激活和 workspace；并发数需用剩余 HBM 反推。"
        )

    return (
        "当前未配置 LLM，Agent 处于离线模式。\n\n"
        "我可以直接计算 TCO / KV Cache。例如：\n"
        "- `64 张 H100，60% 利用率，3 年 TCO 多少？`\n"
        "- `Llama3-70B 128K 上下文的 KV Cache 多大？`\n\n"
        "配置 `OPENAI_API_KEY` 后可获得完整的多工具、多轮分析。"
    )


def run_agent(message: str, history: list[dict[str, str]] | None = None) -> AgentResponse:
    settings = get_settings()
    trace = TraceRecorder()

    if not settings.llm_ready:
        return AgentResponse(
            answer=_offline_answer(message),
            trace=trace.steps,
            elapsed_ms=trace.elapsed_ms,
            model="offline",
            llm_used=False,
        )

    client = OpenAI(
        api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=60.0
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt()}]
    for h in (history or [])[-8:]:
        if h.get("role") in {"user", "assistant"} and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:2000]})
    messages.append({"role": "user", "content": message})

    last_content = ""
    for _ in range(5):
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=settings.openai_model,
                messages=cast(Any, messages),
                tools=cast(Any, TOOL_SCHEMAS),
                tool_choice="auto",
                temperature=0.2,
                max_tokens=1400,
            )
        except Exception as exc:  # noqa: BLE001
            trace.error(name="llm", error=f"{type(exc).__name__}: {exc}")
            return AgentResponse(
                answer=f"LLM 调用失败：{exc}",
                trace=trace.steps,
                elapsed_ms=trace.elapsed_ms,
                model=settings.openai_model,
                llm_used=True,
            )

        msg = resp.choices[0].message
        # 只处理 function tool calls；custom tool calls 不在本项目工具集内
        tool_calls: list[Any] = [
            tc for tc in (msg.tool_calls or []) if getattr(tc, "function", None) is not None
        ]
        trace.llm(
            model=settings.openai_model,
            content=msg.content,
            tool_names=[tc.function.name for tc in tool_calls],
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

        if not tool_calls:
            last_content = msg.content or ""
            break

        # 把 assistant 的 tool_calls 原样回填
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        }
        messages.append(assistant_msg)

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            t_tool = time.perf_counter()
            result = dispatch_tool(name, args)
            trace.tool(
                name=name,
                args=args,
                output=result if result.get("ok") else None,
                duration_ms=int((time.perf_counter() - t_tool) * 1000),
            )
            if not result.get("ok"):
                trace.error(name=name, error=str(result.get("error")))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:6000],
                }
            )

    if not last_content:
        last_content = "已达到工具调用上限，请补充更明确的参数后重试。"

    return AgentResponse(
        answer=last_content,
        trace=trace.steps,
        elapsed_ms=trace.elapsed_ms,
        model=settings.openai_model,
        llm_used=True,
    )
