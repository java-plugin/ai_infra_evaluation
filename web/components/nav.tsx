import Link from "next/link";

const links = [
  { href: "/calculator", label: "计算器" },
  { href: "/compare", label: "成本对比" },
  { href: "/advisor", label: "选型顾问" },
  { href: "/knowledge", label: "知识库" },
  { href: "/agent", label: "Agent" },
];

export default function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-line/80 bg-ink/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-accent to-violet text-ink">
            AI
          </span>
          <span className="text-sm sm:text-base">AI Infra Advisor</span>
        </Link>
        <nav className="flex items-center gap-1 text-sm text-slate-300">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-1.5 transition hover:bg-white/5 hover:text-white"
            >
              {l.label}
            </Link>
          ))}
          <a
            href={`${process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"}/docs`}
            target="_blank"
            rel="noreferrer"
            className="ml-2 rounded-md border border-line px-3 py-1.5 transition hover:border-accent/60 hover:text-accent"
          >
            API
          </a>
        </nav>
      </div>
    </header>
  );
}
