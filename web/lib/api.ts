export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type CalcResult = {
  value: Record<string, any>;
  assumptions: string[];
  warnings: string[];
  provenance: { source: string; as_of: string; confidence: string }[];
  trace_id: string;
};

export type ReportFiles = {
  markdown: string;
  filename: string;
  download_url: string;
  pdf_filename: string;
  pdf_download_url: string;
};

export type FileLink = { filename: string; download_url: string };

export type KnowledgeTable = {
  table_id: string;
  chapter: string;
  section: string;
  title: string;
  headers: string[];
  rows: Record<string, string>[];
  page: number;
  source: string;
};

export type KnowledgeHit = {
  chunk_id: string;
  doc_type: string;
  chapter: string;
  section: string;
  title: string;
  text: string;
  score: number;
  vector_score: number;
  keyword_score: number;
  source: string;
  page: number;
  row: Record<string, string> | null;
  table: KnowledgeTable | null;
};

export type KnowledgeStats = {
  doc_type_counts: Record<string, number>;
  chapters: string[];
  tables: number;
  chunks: number;
  embedding: string;
  dim: number;
  meta?: Record<string, string>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; llm_ready: boolean; model: string }>("/healthz"),
  catalog: () =>
    request<{ gpus: any[]; models: any[] }>("/api/catalog"),
  tco: (body: any) => request<CalcResult>("/api/tco", { method: "POST", body: JSON.stringify(body) }),
  compare: (body: any) => request<CalcResult>("/api/compare", { method: "POST", body: JSON.stringify(body) }),
  mfu: (body: any) => request<CalcResult>("/api/mfu", { method: "POST", body: JSON.stringify(body) }),
  memory: (body: any) => request<CalcResult>("/api/memory", { method: "POST", body: JSON.stringify(body) }),
  recommend: (body: any) => request<CalcResult>("/api/recommend", { method: "POST", body: JSON.stringify(body) }),
  chat: (body: any) =>
    request<{
      answer: string;
      trace: any[];
      elapsed_ms: number;
      model: string;
      llm_used: boolean;
    }>("/api/agent/chat", { method: "POST", body: JSON.stringify(body) }),
  report: (body: any) =>
    request<ReportFiles>("/api/report", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  exportAgent: (body: any) =>
    request<FileLink>("/api/agent/export", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  knowledgeSearch: (params: {
    q: string;
    top_k?: number;
    mode?: string;
    doc_type?: string;
    chapter?: string;
  }) => {
    const qs = new URLSearchParams();
    qs.set("q", params.q);
    qs.set("top_k", String(params.top_k ?? 5));
    if (params.mode) qs.set("mode", params.mode);
    if (params.doc_type) qs.set("doc_type", params.doc_type);
    if (params.chapter) qs.set("chapter", params.chapter);
    return request<{ query: string; results: KnowledgeHit[] }>(
      `/api/knowledge/search?${qs.toString()}`
    );
  },
  knowledgeStats: () =>
    request<{ ready: boolean; stats?: KnowledgeStats }>("/api/knowledge/stats"),
  knowledgeTable: (table_id: string) =>
    request<KnowledgeTable>(`/api/knowledge/tables/${encodeURIComponent(table_id)}`),
};

/** 跨域下载：先取 blob 再触发保存，避免 download 属性失效。 */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`下载失败：${res.status} ${res.statusText}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
