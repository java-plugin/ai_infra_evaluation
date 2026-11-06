"use client";

import { api, downloadFile } from "@/lib/api";
import { useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "assistant"; content: string };

type Exchange = {
  question: string;
  answer: string;
  trace: any[];
  model: string;
  elapsed_ms: number;
};

const EXAMPLES = [
  "64 张 H100，60% 利用率，3 年 TCO 多少？",
  "Llama3-70B 128K 上下文的 KV Cache 多大？",
  "预算 300 万，做客服 RAG，选什么？",
  "自建和云 3 年预留哪个划算？",
];

export default function AgentPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [trace, setTrace] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [last, setLast] = useState<Exchange | null>(null);
  const [exporting, setExporting] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => { });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || loading) return;
    setInput("");
    setError("");
    setMessages((m) => [...m, { role: "user", content }]);
    setLoading(true);
    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const r = await api.chat({ message: content, history });
      setMessages((m) => [...m, { role: "assistant", content: r.answer }]);
      setTrace(r.trace || []);
      setMeta(r);
      setLast({
        question: content,
        answer: r.answer,
        trace: r.trace || [],
        model: r.model,
        elapsed_ms: r.elapsed_ms,
      });
    } catch (e: any) {
      setError(e?.message || "请求失败");
    } finally {
      setLoading(false);
    }
  }

  async function exportPdf() {
    if (!last || exporting) return;
    setExporting(true);
    setError("");
    try {
      const link = await api.exportAgent(last);
      await downloadFile(link.download_url, link.filename);
    } catch (e: any) {
      setError(e?.message || "PDF 导出失败");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">Agent</h1>
          <p className="mt-2 text-sm text-slate-400">
            LLM 负责理解、追问、编排与解释；数字由工具计算，右侧 trace 可回放。
          </p>
        </div>
        <div className="badge">
          {health ? (health.llm_ready ? `LLM: ${health.model}` : "离线模式") : "检查中…"}
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="card flex min-h-[560px] flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto pr-1">
            {messages.length === 0 && (
              <div className="rounded-xl border border-line/70 bg-ink/40 p-4">
                <div className="text-sm font-medium text-slate-200">试试这些问题</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {EXAMPLES.map((q) => (
                    <button key={q} onClick={() => send(q)} className="badge hover:border-accent/50 hover:text-accent">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[92%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6 ${m.role === "user"
                    ? "bg-accent/15 text-slate-100"
                    : "border border-line bg-panel text-slate-200"
                    }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="text-xs text-slate-500">Agent 正在调用工具计算…</div>
            )}
            <div ref={bottomRef} />
          </div>

          {error && <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">{error}</div>}

          <div className="mt-4 flex gap-2">
            <input
              className="input"
              value={input}
              placeholder="描述你的场景、集群规模或问题…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button className="btn" onClick={() => send()} disabled={loading}>
              发送
            </button>
          </div>
          {meta && (
            <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-600">
              <span>
                {meta.model} · {meta.elapsed_ms} ms · {meta.llm_used ? "LLM + tools" : "offline"}
              </span>
              {last && (
                <button
                  className="badge hover:border-accent/50 hover:text-accent"
                  onClick={exportPdf}
                  disabled={exporting}
                >
                  {exporting ? "生成 PDF…" : "导出 PDF 技术方案"}
                </button>
              )}
            </div>
          )}
        </div>

        <div className="card min-h-[560px]">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium text-slate-300">执行轨迹</div>
            <div className="badge">{trace.length} steps</div>
          </div>
          {trace.length === 0 ? (
            <div className="text-xs leading-6 text-slate-500">
              发送问题后，这里会显示：
              <br />· LLM 决策
              <br />· 工具调用与参数
              <br />· 工具输出摘要
              <br />· 耗时与错误
            </div>
          ) : (
            <div className="space-y-3">
              {trace.map((s, i) => (
                <div key={i} className="rounded-xl border border-line/70 bg-ink/40 p-3">
                  <div className="flex items-center justify-between text-xs">
                    <span
                      className={`font-medium ${s.type === "tool" ? "text-accent" : s.type === "error" ? "text-red-300" : "text-violet"
                        }`}
                    >
                      {s.type} · {s.name}
                    </span>
                    <span className="text-slate-600">{s.duration_ms} ms</span>
                  </div>
                  {s.args && Object.keys(s.args).length > 0 && (
                    <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-[10px] leading-4 text-slate-500">
                      {JSON.stringify(s.args, null, 2)}
                    </pre>
                  )}
                  {s.output && (
                    <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap text-[10px] leading-4 text-slate-400">
                      {JSON.stringify(s.output, null, 2)}
                    </pre>
                  )}
                  {s.error && <div className="mt-2 text-[10px] text-red-300">{s.error}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
