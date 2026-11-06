import Link from "next/link";

const stats = [
  { value: "5", label: "GPU 型号", hint: "H100 / H800 / A100 / L40S / 910B" },
  { value: "3", label: "模型结构", hint: "Llama 3 8B / 70B / DeepSeek V3" },
  { value: "7", label: "Agent 工具", hint: "TCO / MFU / KV / 显存 / 选型 / 检索" },
  { value: "1", label: "确定性引擎", hint: "同一套公式，Web 与 Agent 复用" },
];

const features = [
  {
    title: "算清 TCO",
    body: "自建、云按需、1/3 年预留、Spot、租赁六种模式对比；每 GPU 小时、每百万 token、盈亏平衡利用率一次算清。",
    href: "/calculator",
  },
  {
    title: "算清性能",
    body: "MFU、KV Cache、显存构成、OOM 风险；支持 Dense / MoE、GQA、LoRA、量化与并行配置。",
    href: "/calculator",
  },
  {
    title: "Agent 不负责算数",
    body: "LLM 只做意图理解、追问与解释；所有数字由带 provenance 的确定性工具产生，trace 可回放。",
    href: "/agent",
  },
  {
    title: "5 分钟选型报告",
    body: "业务、模型、QPS、SLO、隐私、团队规模 → Top 方案 + 成本 + 风险 + 实施路线，Markdown 可下载。",
    href: "/advisor",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-16">
      <section className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
        <div>
          <div className="badge mb-5">AI Infra · Decision Engine</div>
          <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-6xl">
            先算清，
            <span className="bg-gradient-to-r from-accent to-violet bg-clip-text text-transparent">
              再买卡。
            </span>
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-slate-300">
            把硬件、通信、推理优化、集群、成本和行业方案串成一个可执行模型。
            输入 GPU 型号、集群规模、利用率和电价，得到 TCO、每 GPU 小时成本、MFU、
            KV Cache 和可解释的选型建议。
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/calculator" className="btn">
              打开计算器
            </Link>
            <Link href="/agent" className="btn-ghost">
              问问 Agent
            </Link>
            <Link href="/advisor" className="btn-ghost">
              生成选型报告
            </Link>
          </div>
          <div className="mt-8 rounded-xl border border-line bg-ink/60 p-4 font-mono text-xs text-slate-400">
            <div className="mb-2 text-slate-500"># 命令行也能算</div>
            ai-infra tco --nodes 8 --gpus-per-node 8 --gpu h100-sxm5-80gb --years 3 --util 60
          </div>
        </div>

        <div className="card relative overflow-hidden">
          <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-accent/10 blur-2xl" />
          <div className="text-xs uppercase tracking-widest text-slate-500">示例结果</div>
          <div className="mt-3 text-3xl font-semibold">¥19.81 / GPU·h</div>
          <div className="mt-1 text-sm text-slate-400">64 × H100 · 3 年 · 60% 利用率</div>
          <div className="mt-6 space-y-3 text-sm">
            {[
              ["三年 TCO", "¥1,998.7 万"],
              ["云 3 年预留", "¥12.00 / GPU·h"],
              ["盈亏平衡利用率", "约 33%"],
              ["估算 MFU", "约 55%（未实测）"],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between border-b border-line/60 pb-2">
                <span className="text-slate-400">{k}</span>
                <span className="font-medium text-slate-100">{v}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs leading-5 text-slate-500">
            数字来自 data/gpus.yaml 与统一成本口径；页面会显示 as_of 与警告。
          </p>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="card">
            <div className="text-3xl font-bold text-accent">{s.value}</div>
            <div className="mt-1 text-sm font-medium">{s.label}</div>
            <div className="mt-1 text-xs text-slate-500">{s.hint}</div>
          </div>
        ))}
      </section>

      <section>
        <h2 className="text-2xl font-semibold">四个入口，一条计算内核</h2>
        <p className="mt-2 text-sm text-slate-400">
          Web、CLI、API、Agent 全部复用同一套计算器；不会出现「页面算一套、Agent 算另一套」。
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {features.map((f) => (
            <Link key={f.title} href={f.href} className="card group transition hover:border-accent/40">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">{f.title}</h3>
                <span className="text-accent opacity-0 transition group-hover:opacity-100">→</span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-400">{f.body}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="card border-accent/20 bg-gradient-to-br from-panel to-ink">
        <h2 className="text-xl font-semibold">为什么不是普通读书笔记</h2>
        <div className="mt-4 grid gap-3 text-sm text-slate-300 sm:grid-cols-3">
          {[
            ["可执行", "公式是代码，不是摘抄；每个结果带 assumptions 与 provenance。"],
            ["可验证", "golden test 手算基准 + 属性测试；数字可回放。"],
            ["可审计", "Agent 每次回答附带工具调用链，前端右侧 trace 面板可见。"],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl border border-line/70 bg-ink/40 p-4">
              <div className="font-medium text-accent">{k}</div>
              <p className="mt-1 leading-6 text-slate-400">{v}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
