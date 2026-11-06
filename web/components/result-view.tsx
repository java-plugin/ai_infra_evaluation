"use client";

import type { CalcResult } from "@/lib/api";

const LABELS: Record<string, string> = {
  tco_total_cny: "TCO 总额",
  per_gpu_hour_cny: "每 GPU 小时",
  per_million_tokens_cny: "每百万 token",
  gpu_count: "GPU 数量",
  gpu_model: "GPU 型号",
  years: "年限",
  utilization_pct: "利用率 (%)",
  tokens_per_sec: "tokens/s",
  step_time_s: "step time (s)",
  achieved_tflops: "实测算力 (TFLOPS)",
  peak_tflops_total: "峰值算力 (TFLOPS)",
  mfu_pct: "MFU (%)",
  mfu_dedicated_pct: "扣通信 MFU (%)",
  kv_per_token_bytes: "每 token KV (B)",
  kv_per_request_mb: "每请求 KV (MB)",
  kv_total_gb: "总 KV (GB)",
  kv_per_gpu_gb: "单卡 KV (GB)",
  total_gb: "单卡总显存 (GB)",
  hbm_gb: "单卡 HBM (GB)",
  oom_risk: "OOM 风险",
  recommended_gpu: "推荐 GPU",
  recommended_nodes: "推荐节点数",
  recommended_gpus_per_node: "每节点 GPU",
  cheapest_mode: "最低成本模式",
  cheapest_per_gpu_hour_cny: "最低每 GPU 小时",
  self_per_gpu_hour_cny: "自建每 GPU 小时",
  total_gpus: "GPU 总数",
  break_even_util_pct: "盈亏平衡利用率 (%)",
};

function fmt(key: string, v: unknown): string {
  if (typeof v === "boolean") return v ? "是" : "否";
  if (typeof v === "number") {
    if (key.includes("cny")) return `¥${v.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
    return v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }
  return String(v ?? "—");
}

export default function ResultView({ result }: { result: CalcResult }) {
  const summary = result.value?.summary || {};
  const structure = result.value?.cost_structure_pct as Record<string, number> | undefined;
  const rows = result.value?.rows as Array<Record<string, any>> | undefined;
  const reasons = result.value?.reasons as string[] | undefined;

  return (
    <div className="space-y-5">
      {Object.keys(summary).length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(summary).map(([k, v]) => (
            <div key={k} className="rounded-xl border border-line/70 bg-ink/40 px-4 py-3">
              <div className="text-xs uppercase tracking-wider text-slate-500">{LABELS[k] || k}</div>
              <div className="mt-1 text-lg font-semibold text-slate-100">{fmt(k, v)}</div>
            </div>
          ))}
        </div>
      )}

      {structure && (
        <div>
          <div className="mb-2 text-sm font-medium text-slate-300">成本结构</div>
          <div className="space-y-2">
            {Object.entries(structure)
              .filter(([, v]) => v > 0)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => (
                <div key={k} className="flex items-center gap-3 text-xs">
                  <div className="w-24 shrink-0 text-slate-400">{k}</div>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-accent to-violet"
                      style={{ width: `${Math.min(100, v)}%` }}
                    />
                  </div>
                  <div className="w-14 text-right text-slate-300">{v.toFixed(1)}%</div>
                </div>
              ))}
          </div>
        </div>
      )}

      {rows && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-3">模式</th>
                <th className="py-2 pr-3">名义 ¥/GPUh</th>
                <th className="py-2 pr-3">有效 ¥/GPUh</th>
                <th className="py-2 pr-3">总成本</th>
                <th className="py-2">说明</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.mode} className="border-b border-line/50">
                  <td className="py-2 pr-3 font-medium text-slate-200">{r.mode}</td>
                  <td className="py-2 pr-3">¥{Number(r.per_gpu_hour_cny).toFixed(2)}</td>
                  <td className="py-2 pr-3 text-accent">
                    ¥{Number(r.effective_per_gpu_hour_cny ?? r.per_gpu_hour_cny).toFixed(2)}
                  </td>
                  <td className="py-2 pr-3">¥{Number(r.tco_cny).toLocaleString("zh-CN", { maximumFractionDigits: 0 })}</td>
                  <td className="py-2 text-slate-500">{r.notes || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {reasons && reasons.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-medium text-slate-300">推荐理由</div>
          <ul className="space-y-1 text-sm text-slate-400">
            {reasons.map((r) => (
              <li key={r}>· {r}</li>
            ))}
          </ul>
        </div>
      )}

      {result.assumptions.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-medium text-slate-300">关键假设</div>
          <ul className="space-y-1 text-xs leading-5 text-slate-400">
            {result.assumptions.map((a) => (
              <li key={a}>· {a}</li>
            ))}
          </ul>
        </div>
      )}

      {result.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3">
          <div className="mb-1 text-xs font-medium text-amber-300">警告</div>
          <ul className="space-y-1 text-xs leading-5 text-amber-100/80">
            {result.warnings.map((w) => (
              <li key={w}>! {w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="text-[11px] text-slate-600">
        trace_id: {result.trace_id} · 来源：{result.provenance.map((p) => p.source).join(", ") || "—"}
      </div>
    </div>
  );
}
