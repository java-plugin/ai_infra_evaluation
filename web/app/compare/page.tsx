"use client";

import ResultView from "@/components/result-view";
import { api, type CalcResult } from "@/lib/api";
import { useEffect, useState } from "react";

export default function ComparePage() {
  const [gpus, setGpus] = useState<any[]>([]);
  const [nodes, setNodes] = useState(8);
  const [gpusPerNode, setGpusPerNode] = useState(8);
  const [gpuId, setGpuId] = useState("h100-sxm5-80gb");
  const [years, setYears] = useState(3);
  const [util, setUtil] = useState(60);
  const [result, setResult] = useState<CalcResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.catalog().then((c) => setGpus(c.gpus)).catch(() => { });
  }, []);

  async function run() {
    setLoading(true);
    setError("");
    try {
      const r = await api.compare({
        base: {
          nodes, gpus_per_node: gpusPerNode, gpu_id: gpuId, years,
          utilization_pct: util,
        },
      });
      setResult(r);
    } catch (e: any) {
      setError(e?.message || "请求失败");
    } finally {
      setLoading(false);
    }
  }

  const rows = (result?.value?.rows || []) as any[];
  const max = Math.max(1, ...rows.map((r) => Number(r.effective_per_gpu_hour_cny ?? r.per_gpu_hour_cny)));
  const breakEven = (result?.value?.break_even_util_pct || {}) as Record<string, number>;
  const MODE_LABELS: Record<string, string> = {
    cloud_ondemand: "云按需",
    cloud_1y_reserved: "云 1 年预留",
    cloud_3y_reserved: "云 3 年预留",
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">成本对比</h1>
        <p className="mt-2 text-sm text-slate-400">
          自建 vs 云按需 / 预留 / Spot / 租赁；Spot 按 30% 可用率折算有效成本。
        </p>
      </div>

      <div className="card grid gap-3 sm:grid-cols-5">
        <Field label="节点数" value={nodes} onChange={setNodes} />
        <Field label="每节点 GPU" value={gpusPerNode} onChange={setGpusPerNode} />
        <div>
          <label className="label">GPU</label>
          <select className="input" value={gpuId} onChange={(e) => setGpuId(e.target.value)}>
            {gpus.map((g) => <option key={g.id} value={g.id}>{g.id}</option>)}
          </select>
        </div>
        <Field label="年限" value={years} onChange={setYears} />
        <Field label="利用率 %" value={util} onChange={setUtil} />
        <div className="sm:col-span-5">
          <button className="btn w-full sm:w-auto" onClick={run} disabled={loading}>
            {loading ? "对比中…" : "开始对比"}
          </button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">{error}</div>}

      {rows.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="card">
            <div className="mb-4 text-sm font-medium text-slate-300">有效每 GPU 小时成本</div>
            <div className="space-y-3">
              {rows.map((r) => {
                const v = Number(r.effective_per_gpu_hour_cny ?? r.per_gpu_hour_cny);
                return (
                  <div key={r.mode} className="text-xs">
                    <div className="mb-1 flex justify-between text-slate-400">
                      <span>{r.mode}</span>
                      <span className="font-medium text-slate-200">¥{v.toFixed(2)}</span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-white/5">
                      <div
                        className={`h-full rounded-full ${v === max ? "bg-slate-500" : "bg-gradient-to-r from-accent to-violet"}`}
                        style={{ width: `${Math.max(4, (v / max) * 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            {Object.keys(breakEven).length > 0 && (
              <div className="mt-6">
                <div className="mb-2 text-sm font-medium text-slate-300">盈亏平衡利用率</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(breakEven).map(([k, v]) => (
                    <span key={k} className="badge">
                      {MODE_LABELS[k] || k}: {Number.isFinite(v) ? `${v.toFixed(0)}%` : "无法达到"}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="card">
            <ResultView result={result!} />
          </div>
        </div>
      )}
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
