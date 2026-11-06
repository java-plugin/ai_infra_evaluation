"use client";

import { api, KnowledgeHit, KnowledgeStats } from "@/lib/api";
import { useEffect, useState } from "react";

const EXAMPLES = [
  "字节跳动 GPU 总量和最大集群规模",
  "四大厂商私有化部署最低门槛对比",
  "H100 单卡价格与 8 卡整机价格",
  "医疗行业私有化单机整机配置",
];

const DOC_TYPES = [
  { value: "", label: "全部类型" },
  { value: "text", label: "正文" },
  { value: "table_row", label: "表格行" },
  { value: "table_summary", label: "表格摘要" },
  { value: "table_group", label: "行组" },
  { value: "figure", label: "图表" },
];

const MODES = [
  { value: "hybrid", label: "混合检索" },
  { value: "vector", label: "向量" },
  { value: "keyword", label: "关键词" },
];

function TableView({ hit }: { hit: KnowledgeHit }) {
  if (!hit.table) return null;
  const table = hit.table;
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-line/70">
      <table className="min-w-full text-xs">
        <thead className="bg-white/5 text-slate-300">
          <tr>
            {table.headers.map((h) => (
              <th key={h} className="whitespace-nowrap px-3 py-2 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => {
            const matched =
              hit.row !== null &&
              table.headers.every((h) => row[h] === hit.row?.[h]);
            return (
              <tr
                key={i}
                className={matched ? "bg-accent/10 text-slate-100" : "text-slate-400"}
              >
                {table.headers.map((h) => (
                  <td key={h} className="whitespace-nowrap px-3 py-2 align-top">
                    {row[h] || "-"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [mode, setMode] = useState("hybrid");
  const [docType, setDocType] = useState("");
  const [chapter, setChapter] = useState("");
  const [hits, setHits] = useState<KnowledgeHit[]>([]);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [ready, setReady] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .knowledgeStats()
      .then((r) => {
        setReady(r.ready);
        if (r.stats) setStats(r.stats);
      })
      .catch(() => setReady(false));
  }, []);

  async function search(text?: string) {
    const q = (text ?? query).trim();
    if (!q || loading) return;
    setQuery(q);
    setLoading(true);
    setError("");
    try {
      const r = await api.knowledgeSearch({
        q,
        top_k: topK,
        mode,
        doc_type: docType,
        chapter,
      });
      setHits(r.results);
    } catch (e: any) {
      setError(e?.message || "检索失败");
      setHits([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">知识库</h1>
          <p className="mt-2 text-sm text-slate-400">
            《AI Infra 全栈实战》正文与表格已分块入库：表格拆成摘要 / 单行 / 行组三种粒度，
            每一块都保留表头字段名，命中后回取整表 JSON。
          </p>
        </div>
        <div className="badge">
          {ready === null
            ? "检查索引…"
            : ready && stats
              ? `${stats.chunks} chunks · ${stats.tables} 表 · ${stats.embedding}`
              : "索引未构建"}
        </div>
      </div>

      <div className="card space-y-4">
        <div className="flex flex-wrap gap-2">
          <input
            className="input min-w-[260px] flex-1"
            value={query}
            placeholder="问一个书里有答案的问题，例如：字节跳动 GPU 总量是多少？"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                search();
              }
            }}
          />
          <button className="btn" onClick={() => search()} disabled={loading}>
            {loading ? "检索中…" : "检索"}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <label className="flex items-center gap-2">
            返回条数
            <select
              className="input h-8 w-20 py-0"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            >
              {[3, 5, 8, 10].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            检索方式
            <select
              className="input h-8 py-0"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            片段类型
            <select
              className="input h-8 py-0"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
            >
              {DOC_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            章节
            <select
              className="input h-8 max-w-[220px] py-0"
              value={chapter}
              onChange={(e) => setChapter(e.target.value)}
            >
              <option value="">全部章节</option>
              {(stats?.chapters || []).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              onClick={() => search(q)}
              className="badge hover:border-accent/50 hover:text-accent"
            >
              {q}
            </button>
          ))}
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
            {error}
          </div>
        )}

        {ready === false && (
          <div className="text-xs text-amber-300">
            索引尚未构建：先执行{" "}
            <code className="rounded bg-white/5 px-1">
              ai-infra rag extract --pdf &lt;原书 PDF&gt;
            </code>{" "}
            与{" "}
            <code className="rounded bg-white/5 px-1">ai-infra rag build</code>。
          </div>
        )}
      </div>

      <div className="space-y-4">
        {hits.map((hit) => (
          <div key={hit.chunk_id} className="card">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="rounded-md border border-line px-2 py-0.5 text-accent">
                {hit.doc_type}
              </span>
              <span className="text-slate-500">
                {hit.chapter} · {hit.section} · p{hit.page} · score {hit.score}
              </span>
            </div>
            <div className="mt-2 text-sm font-medium text-slate-200">{hit.title}</div>
            <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-400">
              {hit.text}
            </div>
            {hit.row && (
              <div className="mt-3 rounded-lg border border-line/70 bg-ink/40 p-3 text-xs text-slate-300">
                命中行：
                {Object.entries(hit.row).map(([k, v]) => (
                  <span key={k} className="ml-2">
                    <span className="text-slate-500">{k}:</span> {v}
                  </span>
                ))}
              </div>
            )}
            <TableView hit={hit} />
            <div className="mt-2 text-[11px] text-slate-600">{hit.source}</div>
          </div>
        ))}
        {!loading && hits.length === 0 && ready && (
          <div className="text-sm text-slate-500">
            输入问题后按 Enter，或点上方示例。
          </div>
        )}
      </div>
    </div>
  );
}
