"use client";

import ResultView from "@/components/result-view";
import { api, downloadFile, type CalcResult, type ReportFiles } from "@/lib/api";
import { useState } from "react";

export default function AdvisorPage() {
  const [business, setBusiness] = useState("customer_service");
  const [modelSize, setModelSize] = useState(70);
  const [qps, setQps] = useState(200);
  const [ttft, setTtft] = useState(3000);
  const [tpot, setTpot] = useState(50);
  const [privacy, setPrivacy] = useState("high");
  const [teamSize, setTeamSize] = useState(3);
  const [budget, setBudget] = useState<number | "">("");
  const [result, setResult] = useState<CalcResult | null>(null);
  const [report, setReport] = useState<ReportFiles | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setLoading(true);
    setError("");
    setReport(null);
    try {
      const r = await api.recommend({
        business_type: business,
        model_size_billion: modelSize,
        qps,
        ttft_slo_ms: ttft,
        tpot_slo_ms: tpot,
        privacy_need: privacy,
        team_size: teamSize,
        budget_cny_per_year: budget === "" ? null : Number(budget) * 10000,
      });
      setResult(r);
    } catch (e: any) {
      setError(e?.message || "请求失败");
    } finally {
      setLoading(false);
    }
  }

  async function makeReport() {
    if (!result) return;
    const s = result.value.summary;
    try {
      const r = await api.report({
        tco: {
          nodes: s.recommended_nodes,
          gpus_per_node: s.recommended_gpus_per_node,
          gpu_id: s.recommended_gpu,
          years: 3,
          utilization_pct: 60,
        },
        model_id: modelSize >= 70 ? "llama3-70b" : "llama3-8b",
      });
      setReport(r);
    } catch (e: any) {
      setError(e?.message || "报告生成失败");
    }
  }

  function downloadMarkdown() {
    if (!report) return;
    const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = report.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function downloadPdf() {
    if (!report) return;
    try {
      await downloadFile(report.pdf_download_url, report.pdf_filename);
    } catch (e: any) {
      setError(e?.message || "PDF 下载失败");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">选型顾问</h1>
        <p className="mt-2 text-sm text-slate-400">
          8 个问题 → 可解释推荐 → 可下载的 Markdown / PDF 技术方案。
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="card space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Select label="业务类型" value={business} onChange={setBusiness}
              options={[
                ["general", "通用"], ["customer_service", "客服 RAG"],
                ["fintech", "金融"], ["medical", "医疗"],
                ["gaming", "游戏"], ["rnd", "研发训练"],
              ].map(([value, label]) => ({ value, label }))} />
            <Field label="模型规模 (B)" value={modelSize} onChange={setModelSize} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="QPS" value={qps} onChange={setQps} />
            <Field label="团队人数" value={teamSize} onChange={setTeamSize} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="TTFT SLO (ms)" value={ttft} onChange={setTtft} />
            <Field label="TPOT SLO (ms)" value={tpot} onChange={setTpot} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Select label="隐私/合规" value={privacy} onChange={setPrivacy}
              options={[
                { value: "none", label: "无要求" },
                { value: "low", label: "低" },
                { value: "high", label: "高" },
                { value: "max", label: "最高（必须私有化）" },
              ]} />
            <div>
              <label className="label">年预算 (万元，可空)</label>
              <input type="number" className="input" value={budget}
                onChange={(e) => setBudget(e.target.value === "" ? "" : Number(e.target.value))} />
            </div>
          </div>
          <button className="btn w-full" onClick={run} disabled={loading}>
            {loading ? "分析中…" : "生成推荐"}
          </button>
          {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">{error}</div>}
        </div>

        <div className="card min-h-[360px]">
          {result ? (
            <div className="space-y-4">
              <ResultView result={result} />
              <div className="flex flex-wrap gap-2">
                <button className="btn" onClick={makeReport}>生成报告</button>
                {report && (
                  <>
                    <button className="btn-ghost" onClick={downloadMarkdown}>下载 Markdown</button>
                    <button className="btn-ghost" onClick={downloadPdf}>下载 PDF</button>
                  </>
                )}
              </div>
              {report && (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-line/70 bg-ink/40 p-3 text-[11px] leading-5 text-slate-400">
                  {report.markdown}
                </pre>
              )}
            </div>
          ) : (
            <div className="flex min-h-[340px] flex-col items-center justify-center text-center">
              <div className="text-sm text-slate-400">填写左侧问卷，生成推荐</div>
              <div className="mt-2 max-w-sm text-xs leading-5 text-slate-600">
                推荐会给出 GPU 型号、节点数、最低成本模式与硬约束；报告包含假设、对比、成本结构、风险与实施路线。
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <label className="label">{label}</label>
      <input type="number" className="input" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function Select({
  label, value, onChange, options,
}: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div>
      <label className="label">{label}</label>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
