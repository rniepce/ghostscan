import type { ScanResult } from "./types";

// Em dev (npm run dev), VITE_API_URL é vazio e o Vite faz proxy de /api para o backend.
// Em prod, defina VITE_API_URL=https://seu-backend.up.railway.app no Railway.
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export async function scanPdf(file: File): Promise<ScanResult> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(`${API_BASE}/api/scan`, { method: "POST", body: form });
  if (!resp.ok) {
    let msg = `Erro ${resp.status}`;
    try {
      const data = await resp.json();
      if (data?.detail) msg = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await resp.json()) as ScanResult;
}
