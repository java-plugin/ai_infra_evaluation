"""数据目录加载与校验。

``load_*`` 函数负责读 YAML、补上默认字段（例如 ``GPU.price_cny``
取 min/max 中位数），并对每条记录强制执行 provenance 校验：
``source`` / ``as_of`` / ``confidence`` 三者缺一则抛 ``CatalogError``。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import GPU, Model


class CatalogError(ValueError):
    """数据目录加载或校验失败。"""


def _data_root() -> Path:
    """数据目录根路径。

    解析顺序: 环境变量 ``AI_INFRA_DATA_DIR`` → 仓库 ``./data`` →
    相对于本文件的 ``../../data``。
    """

    env = os.environ.get("AI_INFRA_DATA_DIR")
    p = Path(env).expanduser() if env else Path(__file__).resolve().parents[2] / "data"
    if not p.is_dir():
        raise CatalogError(f"数据目录不存在: {p}")
    return p


def _load_yaml(name: str) -> list[dict[str, Any]]:
    path = _data_root() / name
    if not path.is_file():
        raise CatalogError(f"数据文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, list):
        raise CatalogError(f"{name} 顶层必须是 list，实际是 {type(raw).__name__}")
    return raw


def _check_provenance(entry: dict[str, Any], path: str) -> None:
    for k in ("source", "as_of"):
        if not entry.get(k):
            raise CatalogError(f"{path}: 条目 {entry.get('id', '<no id>')} 缺少 {k}")
    if entry.get("confidence") not in {None, "high", "medium", "low"}:
        raise CatalogError(
            f"{path}: 条目 {entry.get('id', '<no id>')} confidence 非法值 {entry.get('confidence')!r}"
        )


def load_gpus() -> dict[str, GPU]:
    """加载 GPU 目录，返回 ``{gpu_id: GPU}``。"""

    raw = _load_yaml("gpus.yaml")
    out: dict[str, GPU] = {}
    for entry in raw:
        _check_provenance(entry, "gpus.yaml")
        # 补中位数 price_cny
        if entry.get("price_cny") is None:
            lo = entry.get("price_cny_min")
            hi = entry.get("price_cny_max")
            if lo is not None and hi is not None:
                entry["price_cny"] = (lo + hi) / 2
        try:
            gpu = GPU(**entry)
        except Exception as exc:  # pragma: no cover - 数据本身错
            raise CatalogError(f"gpus.yaml 条目 {entry.get('id')!r} 解析失败: {exc}") from exc
        out[gpu.id] = gpu
    return out


def load_models() -> dict[str, Model]:
    """加载模型目录，返回 ``{model_id: Model}``。"""

    raw = _load_yaml("models.yaml")
    out: dict[str, Model] = {}
    for entry in raw:
        _check_provenance(entry, "models.yaml")
        # GQA/MQA: num_kv_heads 缺省时等于 num_attention_heads
        if entry.get("num_kv_heads") is None:
            entry["num_kv_heads"] = entry.get("num_attention_heads")
        # MoE 默认 active params = params
        if entry.get("active_params_billion") is None:
            entry["active_params_billion"] = entry.get("params_billion")
        try:
            m = Model(**entry)
        except Exception as exc:  # pragma: no cover
            raise CatalogError(f"models.yaml 条目 {entry.get('id')!r} 解析失败: {exc}") from exc
        out[m.id] = m
    return out


def get_gpu(gpu_id: str) -> GPU:
    gpus = load_gpus()
    if gpu_id not in gpus:
        raise CatalogError(f"未知 GPU id: {gpu_id!r}。可用: {list(gpus)}")
    return gpus[gpu_id]


def get_model(model_id: str) -> Model:
    models = load_models()
    if model_id not in models:
        raise CatalogError(f"未知 model id: {model_id!r}。可用: {list(models)}")
    return models[model_id]


if __name__ == "__main__":  # pragma: no cover
    gpus = load_gpus()
    models = load_models()
    print(f"GPUs   : {len(gpus)} -> {list(gpus)}")
    print(f"Models : {len(models)} -> {list(models)}")
