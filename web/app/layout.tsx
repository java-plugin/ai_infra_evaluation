import type { Metadata } from "next";
import Nav from "@/components/nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Infra Advisor",
  description:
    "A verifiable decision engine for AI infrastructure: MFU, KV Cache, memory, TCO, and a tool-using agent.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen antialiased">
        <Nav />
        <main className="mx-auto max-w-6xl px-6 pb-24 pt-10">{children}</main>
        <footer className="border-t border-line/60 py-8 text-center text-xs text-slate-500">
          AI Infra Advisor · 数字由确定性引擎计算，Agent 只负责解释
        </footer>
      </body>
    </html>
  );
}
