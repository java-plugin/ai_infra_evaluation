"""Agent 执行轨迹。

每一步都可序列化，前端右侧 trace 面板直接渲染。
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field


class TraceStep(BaseModel):
    type: Literal["llm", "tool", "error"]
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    output: Any | None = None
    error: str | None = None
    duration_ms: int = 0


class TraceRecorder:
    def __init__(self) -> None:
        self.steps: list[TraceStep] = []
        self._start = time.perf_counter()

    def add(self, step: TraceStep) -> None:
        self.steps.append(step)

    def llm(
        self, *, model: str, content: str | None, tool_names: list[str], duration_ms: int
    ) -> None:
        self.add(
            TraceStep(
                type="llm",
                name=model,
                args={"tool_calls": tool_names},
                output=(content or "")[:500],
                duration_ms=duration_ms,
            )
        )

    def tool(self, *, name: str, args: dict[str, Any], output: Any, duration_ms: int) -> None:
        self.add(
            TraceStep(
                type="tool",
                name=name,
                args=args,
                output=output,
                duration_ms=duration_ms,
            )
        )

    def error(self, *, name: str, error: str) -> None:
        self.add(TraceStep(type="error", name=name, error=error))

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
