"""RAG 分块与向量库测试。

重点验证用户明确要求的两条：
1) 表格必须按行解析，且每个行块都保留表头字段名（否则「哪家门槛最低」类检索会失真）；
2) 表格以 JSON 结构入库，命中行块后能按 ``table_id`` 回取整表。
"""

from __future__ import annotations

from pathlib import Path

from ai_infra.rag.chunker import table_chunks
from ai_infra.rag.embedding import HashingEmbedder
from ai_infra.rag.schema import TableData
from ai_infra.rag.store import VectorStore

TABLE = TableData(
    table_id="t99-001",
    chapter="第12章 四大厂商对照表与选型指南",
    section="12.3 成本策略对比表",
    title="12.3 成本策略对比表",
    headers=["对比维度", "字节", "阿里", "腾讯"],
    rows=[
        {
            "对比维度": "私有化部署最低门槛",
            "字节": "200-500 万元",
            "阿里": "150-300 万元",
            "腾讯": "50-100 万元",
        },
        {
            "对比维度": "最大集群规模",
            "字节": "10,000+ 卡",
            "阿里": "5,000+ 卡",
            "腾讯": "2,048 卡",
        },
        {
            "对比维度": "GPU 总量",
            "字节": "30,000+ 张",
            "阿里": "15,000+ 张",
            "腾讯": "6,000-8,000 张",
        },
    ],
    page=260,
    source="《AI Infra 全栈实战》第12章",
)


def test_table_row_chunks_keep_every_header() -> None:
    chunks = table_chunks(TABLE)
    rows = [c for c in chunks if c.doc_type == "table_row"]
    assert len(rows) == len(TABLE.rows)

    for index, chunk in enumerate(rows):
        assert chunk.table_id == TABLE.table_id
        assert chunk.row_index == index
        for header in TABLE.headers:
            assert header in chunk.text, f"行块缺少表头字段 {header}: {chunk.text}"

    # 精确值必须原样落在对应行块里
    assert "30,000+ 张" in rows[2].text
    assert "50-100 万元" in rows[0].text


def test_table_chunks_cover_three_granularities() -> None:
    chunks = table_chunks(TABLE)
    assert {c.doc_type for c in chunks} == {"table_summary", "table_row", "table_group"}

    summary = next(c for c in chunks if c.doc_type == "table_summary")
    for header in TABLE.headers:
        assert header in summary.text
    assert "共 3 行" in summary.text

    groups = [c for c in chunks if c.doc_type == "table_group"]
    assert len(groups) == 1  # 3 行 / GROUP_SIZE=3
    assert "私有化部署最低门槛" in groups[0].text
    assert "GPU 总量" in groups[0].text


def test_store_roundtrip_keyword_vector_and_table(tmp_path: Path) -> None:
    store = VectorStore(tmp_path / "index.db")
    store.create(dim=8, embedding_name="test-8")
    embedder = HashingEmbedder(dim=8)

    chunks = table_chunks(TABLE)
    store.add_chunks(chunks, embedder.embed([c.embed_text for c in chunks]))
    store.add_tables([TABLE])
    store.commit()

    # 关键词通路：中文 bigram 命中首行
    keyword_hits = store.search_keyword("私有化部署最低门槛", 3)
    assert keyword_hits
    assert any(chunk_id.endswith("-r00") for chunk_id, _ in keyword_hits)

    # 向量通路：按 doc_type 过滤，只回表格行
    vec_hits = store.search_vector(
        embedder.embed([chunks[0].embed_text])[0], 3, doc_type="table_row"
    )
    assert vec_hits
    assert all(chunk_id.startswith(f"{TABLE.table_id}-r") for chunk_id, _ in vec_hits)

    # 命中行块后可回取整表 JSON
    table = store.get_table(TABLE.table_id)
    assert table is not None
    assert table.headers == TABLE.headers
    assert table.rows[0]["腾讯"] == "50-100 万元"

    store.close()
