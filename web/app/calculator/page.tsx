"use client";

import ResultView from "@/components/result-view";
import { api, type CalcResult } from "@/lib/api";
import { useEffect, useState } from "react";

type Tab = "tco" | "mfu" | "memory";

const TABS: { id: Tab; label: string; hint: string }[] = [
    { id: "tco", label: "TCO", hint: "自建集群总拥有成本" },
    { id: "mfu", label: "MFU", hint: "训练 / 推理算力利用率" },
    { id: "memory", label: "显存", hint: "权重 / 梯度 / 优化器 / KV" },
];

export default function CalculatorPage() {
    const [tab, setTab] = useState<Tab>("tco");
    const [gpus, setGpus] = useState<any[]>([]);
    const [models, setModels] = useState<any[]>([]);
    const [result, setResult] = useState<CalcResult | null>(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    // TCO
    const [nodes, setNodes] = useState(8);
    const [gpusPerNode, setGpusPerNode] = useState(8);
    const [gpuId, setGpuId] = useState("h100-sxm5-80gb");
    const [years, setYears] = useState(3);
    const [util, setUtil] = useState(60);
    const [elec, setElec] = useState(0.8);
    const [pue, setPue] = useState(1.2);
    const [residual, setResidual] = useState(0);

    // MFU / Memory
    const [modelId, setModelId] = useState("llama3-70b");
    const [mfuGpu, setMfuGpu] = useState("h100-sxm5-80gb");
    const [nGpus, setNGpus] = useState(64);
    const [tp, setTp] = useState(8);
    const [pp, setPp] = useState(1);
    const [dp, setDp] = useState(8);
    const [seqLen, setSeqLen] = useState(4096);
    const [batch, setBatch] = useState(1);
    const [mode, setMode] = useState<"training" | "inference">("inference");

    useEffect(() => {
        api.catalog().then((c) => {
            setGpus(c.gpus);
            setModels(c.models);
        }).catch(() => { });
    }, []);

    async function run() {
        setLoading(true);
        setError("");
        setResult(null);
        try {
            if (tab === "tco") {
                const r = await api.tco({
                    nodes, gpus_per_node: gpusPerNode, gpu_id: gpuId, years,
                    utilization_pct: util, electricity_cny_per_kwh: elec, pue,
                    residual_value_pct: residual,
                });
                setResult(r);
            } else if (tab === "mfu") {
                const r = await api.mfu({
                    model_id: modelId, gpu_id: mfuGpu, n_gpus: nGpus, tp, pp, dp,
                    mode, seq_len: seqLen, batch_per_gpu: batch,
                });
                setResult(r);
            } else {
                const r = await api.memory({
                    model_id: modelId, gpu_id: mfuGpu, mode, tp,
                    seq_len: seqLen, batch, use_lora: false,
                });
                setResult(r);
            }
        } catch (e: any) {
            setError(e?.message || "请求失败");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold">计算器</h1>
                <p className="mt-2 text-sm text-slate-400">
                    所有数字由 Python 确定性引擎计算，返回 assumptions / warnings / provenance。
                </p>
            </div>

            <div className="flex flex-wrap gap-2">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        onClick={() => {
                            setTab(t.id);
                            setResult(null);
                            setError("");
                        }}
                        className={`rounded-lg border px-4 py-2 text-left text-sm transition ${tab === t.id
                                ? "border-accent/60 bg-accent/10 text-accent"
                                : "border-line text-slate-300 hover:border-accent/40"
                            }`}
                    >
                        <div className="font-medium">{t.label}</div>
                        <div className="text-xs opacity-70">{t.hint}</div>
                    </button>
                ))}
            </div>

            <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
                <div className="card space-y-4">
                    {tab === "tco" && (
                        <>
                            <div className="grid grid-cols-2 gap-3">
                                <Field label="节点数" value={nodes} onChange={setNodes} />
                                <Field label="每节点 GPU" value={gpusPerNode} onChange={setGpusPerNode} />
                            </div>
                            <Select label="GPU 型号" value={gpuId} onChange={setGpuId}
                                options={gpus.map((g) => ({ value: g.id, label: `${g.id} · ${g.memory_gb}GB` }))} />
                            <div className="grid grid-cols-2 gap-3">
                                <Field label="年限" value={years} onChange={setYears} />
                                <NumberField label="利用率 %" value={util} onChange={setUtil} step={1} />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <NumberField label="电价 ¥/kWh" value={elec} onChange={setElec} step={0.01} />
                                <NumberField label="PUE" value={pue} onChange={setPue} step={0.01} />
                            </div>
                            <NumberField label="残值 %" value={residual} onChange={setResidual} step={1} />
                        </>
                    )}

                    {(tab === "mfu" || tab === "memory") && (
                        <>
                            <Select label="模型" value={modelId} onChange={setModelId}
                                options={models.map((m) => ({
                                    value: m.id,
                                    label: `${m.id} · ${m.params_billion}B${m.is_moe ? " MoE" : ""}`,
                                }))} />
                            <Select label="GPU" value={mfuGpu} onChange={setMfuGpu}
                                options={gpus.map((g) => ({ value: g.id, label: `${g.id} · ${g.memory_gb}GB` }))} />
                            <div className="grid grid-cols-2 gap-3">
                                <Select label="模式" value={mode} onChange={(v) => setMode(v as any)}
                                    options={[{ value: "inference", label: "推理" }, { value: "training", label: "训练" }]} />
                                <Field label="TP" value={tp} onChange={setTp} />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <Field label="序列长度" value={seqLen} onChange={setSeqLen} />
                                <Field label="batch" value={batch} onChange={setBatch} />
                            </div>
                            {tab === "mfu" && (
                                <div className="grid grid-cols-3 gap-3">
                                    <Field label="GPU 总数" value={nGpus} onChange={setNGpus} />
                                    <Field label="PP" value={pp} onChange={setPp} />
                                    <Field label="DP" value={dp} onChange={setDp} />
                                </div>
                            )}
                        </>
                    )}

                    <button className="btn w-full" onClick={run} disabled={loading}>
                        {loading ? "计算中…" : "开始计算"}
                    </button>
                    {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">{error}</div>}
                </div>

                <div className="card min-h-[320px]">
                    {result ? (
                        <ResultView result={result} />
                    ) : (
                        <div className="flex h-full min-h-[300px] flex-col items-center justify-center text-center">
                            <div className="text-sm text-slate-400">填写左侧参数，点击「开始计算」</div>
                            <div className="mt-2 max-w-sm text-xs leading-5 text-slate-600">
                                结果会包含成本结构、关键假设、警告和数据来源；可以直接对比不同利用率下的成本变化。
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function Field({
    label, value, onChange,
}: { label: string; value: number; onChange: (v: number) => void }) {
    return (
        <div>
            <label className="label">{label}</label>
            <input type="number" className="input" value={value}
                onChange={(e) => onChange(Number(e.target.value))} />
        </div>
    );
}

function NumberField({
    label, value, onChange, step = 1,
}: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
    return (
        <div>
            <label className="label">{label}</label>
            <input type="number" step={step} className="input" value={value}
                onChange={(e) => onChange(Number(e.target.value))} />
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
                {options.length === 0 && <option value={value}>{value}</option>}
                {options.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                ))}
            </select>
        </div>
    );
}
