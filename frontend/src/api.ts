import type { ScanResult } from "./types";

export async function scanPdf(file: File): Promise<ScanResult> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/api/scan", { method: "POST", body: form });
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
