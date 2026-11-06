from ai_infra.catalog import load_gpus, load_models


def test_catalog_loads() -> None:
    gpus = load_gpus()
    models = load_models()
    assert len(gpus) >= 3, "至少 3 个 GPU"
    assert len(models) >= 2, "至少 2 个模型"


def test_every_entry_has_provenance() -> None:
    # catalog 加载时已经校验 provenance, 这里再显式确认
    for g in load_gpus().values():
        assert getattr(g, "as_of", None), f"{g.id} 缺少 as_of"
    for m in load_models().values():
        assert getattr(m, "as_of", None), f"{m.id} 缺少 as_of"
