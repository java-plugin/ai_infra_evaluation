"""API 冒烟测试。

覆盖健康检查、数据目录、核心计算端点和报告生成/下载。
Agent 端点依赖外部 LLM，这里只做脱机路径测试由其它测试覆盖。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_infra.api.main import app
from ai_infra.config import get_settings

client = TestClient(app)

BASE_TCO = {
    "nodes": 8,
    "gpus_per_node": 8,
    "gpu_id": "h100-sxm5-80gb",
    "years": 3,
    "utilization_pct": 60,
}


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["llm_ready"], bool)


def test_catalog_has_gpus_and_models() -> None:
    r = client.get("/api/catalog")
    assert r.status_code == 200
    body = r.json()
    assert len(body["gpus"]) >= 5
    assert len(body["models"]) >= 3
    assert all("source" in g and "as_of" in g for g in body["gpus"])


def test_agent_tools_schema() -> None:
    r = client.get("/api/agent/tools")
    assert r.status_code == 200
    names = {t["function"]["name"] for t in r.json()}
    assert {"calc_tco", "calc_compare", "calc_mfu", "calc_memory", "calc_kv_cache"} <= names


def test_knowledge_search() -> None:
    r = client.get("/api/knowledge/search", params={"q": "KV Cache", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "KV Cache"
    # 索引已构建时走向量检索，未构建时自动回退知识卡片；两种路径都应命中
    assert len(body["results"]) >= 1
    assert {"chunk_id", "doc_type", "text", "score"} <= set(body["results"][0])


def test_knowledge_stats_and_table() -> None:
    r = client.get("/api/knowledge/stats")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["ready"], bool)
    if body["ready"]:
        assert body["stats"]["chunks"] > 0
        assert body["stats"]["dim"] > 0

    missing = client.get("/api/knowledge/tables/no-such-table")
    assert missing.status_code == 404


def test_tco_endpoint_matches_golden() -> None:
    r = client.post("/api/tco", json=BASE_TCO)
    assert r.status_code == 200
    body = r.json()
    summary = body["value"]["summary"]
    assert summary["gpu_count"] == 64
    assert 18_500_000 <= summary["tco_total_cny"] <= 20_000_000
    assert body["trace_id"].startswith("tr_")
    assert body["assumptions"] and body["provenance"]


def test_tco_rejects_bad_gpu() -> None:
    r = client.post("/api/tco", json={**BASE_TCO, "gpu_id": "no-such-gpu"})
    assert r.status_code == 400


def test_compare_effective_cost() -> None:
    r = client.post("/api/compare", json={"base": BASE_TCO})
    assert r.status_code == 200
    rows = r.json()["value"]["rows"]
    spot = next(row for row in rows if row["mode"] == "云 Spot")
    assert spot["effective_per_gpu_hour_cny"] > spot["per_gpu_hour_cny"]


def test_mfu_and_memory() -> None:
    r = client.post(
        "/api/mfu",
        json={
            "model_id": "llama3-70b",
            "gpu_id": "h100-sxm5-80gb",
            "n_gpus": 64,
            "tp": 8,
            "dp": 8,
            "mode": "inference",
            "seq_len": 4096,
        },
    )
    assert r.status_code == 200
    assert r.json()["value"]["summary"]["mfu_pct"] > 0

    r = client.post(
        "/api/memory",
        json={"model_id": "llama3-70b", "gpu_id": "h100-sxm5-80gb", "mode": "inference", "tp": 8},
    )
    assert r.status_code == 200
    assert r.json()["value"]["summary"]["total_gb"] > 0


def test_recommend() -> None:
    r = client.post(
        "/api/recommend",
        json={
            "business_type": "customer_service",
            "model_size_billion": 70,
            "qps": 200,
            "privacy_need": "high",
            "team_size": 3,
        },
    )
    assert r.status_code == 200
    summary = r.json()["value"]["summary"]
    assert summary["recommended_gpu"] == "h100-sxm5-80gb"
    assert summary["recommended_nodes"] >= 1
    assert summary["cheapest_mode"]


def test_report_generate_and_download() -> None:
    r = client.post("/api/report", json={"tco": BASE_TCO, "model_id": "llama3-70b"})
    assert r.status_code == 200
    body = r.json()
    assert body["filename"].endswith(".md")
    assert "执行摘要" in body["markdown"]
    assert "每 GPU 小时" in body["markdown"]

    d = client.get(body["download_url"])
    assert d.status_code == 200

    # PDF 与 Markdown 同源生成，两者都可下载
    assert body["pdf_filename"].endswith(".pdf")
    p = client.get(body["pdf_download_url"])
    assert p.status_code == 200
    assert p.headers["content-type"].startswith("application/pdf")
    assert p.content[:4] == b"%PDF"

    # 清理测试产物
    path = get_settings().report_dir / body["filename"]
    path.unlink(missing_ok=True)
    (get_settings().report_dir / body["pdf_filename"]).unlink(missing_ok=True)


def test_agent_export_pdf() -> None:
    payload = {
        "question": "64 张 H100，60% 利用率，3 年 TCO 多少？",
        "answer": "## 结论\n\n三年 TCO 约 ¥2,000 万，每 GPU 小时约 ¥19.81。",
        "model": "deepseek-chat",
        "elapsed_ms": 1234,
        "trace": [
            {
                "type": "tool",
                "name": "calc_tco",
                "args": {"nodes": 8, "gpus_per_node": 8},
                "duration_ms": 12,
                "output": {
                    "ok": True,
                    "result": {
                        "summary": {"gpu_count": 64},
                        "assumptions": ["电价 ¥0.8/kWh", "PUE 1.2"],
                        "provenance": [
                            {
                                "source": "data/gpus.yaml#h100",
                                "as_of": "2026-09",
                                "confidence": "medium",
                            }
                        ],
                    },
                },
            }
        ],
    }
    r = client.post("/api/agent/export", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["filename"].endswith(".pdf")

    f = client.get(body["download_url"])
    assert f.status_code == 200
    assert f.headers["content-type"].startswith("application/pdf")
    assert f.content[:4] == b"%PDF"

    (get_settings().report_dir / body["filename"]).unlink(missing_ok=True)


def test_report_download_rejects_traversal() -> None:
    r = client.get("/api/report/..%2F..%2Fpyproject.toml")
    assert r.status_code == 404
