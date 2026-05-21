import { useState } from "react";
import { scanPdf } from "./api";
import type { ScanResult } from "./types";
import { PdfDropzone } from "./components/PdfDropzone";
import { RiskBadge } from "./components/RiskBadge";
import { SignalsTable } from "./components/SignalsTable";

type State =
  | { kind: "idle" }
  | { kind: "scanning"; filename: string }
  | { kind: "done"; result: ScanResult }
  | { kind: "error"; message: string };

export default function App() {
  const [state, setState] = useState<State>({ kind: "idle" });

  async function handleFile(file: File) {
    setState({ kind: "scanning", filename: file.name });
    try {
      const result = await scanPdf(file);
      setState({ kind: "done", result });
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-4xl px-6 py-5">
          <h1 className="text-xl font-semibold text-slate-900">GhostScan</h1>
          <p className="text-sm text-slate-600">
            Detector determinístico de injeção fantasma em peças processuais em PDF
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        {state.kind === "idle" && <PdfDropzone onFile={handleFile} />}

        {state.kind === "scanning" && (
          <div className="flex h-64 flex-col items-center justify-center rounded-2xl border-2 border-dashed border-indigo-300 bg-white">
            <div className="mb-3 h-8 w-8 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
            <p className="text-sm font-medium text-slate-700">Analisando peça…</p>
            <p className="mt-1 text-xs text-slate-500">{state.filename}</p>
          </div>
        )}

        {state.kind === "error" && (
          <div className="rounded-2xl border border-rose-300 bg-rose-50 p-6">
            <p className="font-semibold text-rose-800">Falha na análise</p>
            <p className="mt-1 text-sm text-rose-700">{state.message}</p>
            <button
              onClick={() => setState({ kind: "idle" })}
              className="mt-4 rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700"
            >
              Tentar outro arquivo
            </button>
          </div>
        )}

        {state.kind === "done" && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-slate-200 bg-white p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500">Arquivo</p>
                  <p className="font-medium text-slate-900">{state.result.arquivo}</p>
                </div>
                <RiskBadge risco={state.result.risco} />
              </div>

              <dl className="mt-5 grid grid-cols-3 gap-4 text-sm">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Páginas</dt>
                  <dd className="font-medium text-slate-900">
                    {state.result.paginas_analisadas}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Total de sinais</dt>
                  <dd className="font-medium text-slate-900">{state.result.total_sinais}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">
                    Teste forte (OCR)
                  </dt>
                  <dd className="font-medium text-slate-900">
                    {state.result.ocr_executado ? "executado" : "NÃO executado"}
                  </dd>
                </div>
              </dl>
            </div>

            <SignalsTable sinais={state.result.sinais} />

            <div className="flex justify-end">
              <button
                onClick={() => setState({ kind: "idle" })}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Analisar outro PDF
              </button>
            </div>
          </div>
        )}
      </main>

      <footer className="mx-auto max-w-4xl px-6 py-6 text-center text-xs text-slate-400">
        Camada GEX-IA / TJMG · análise determinística, não baseada em LLM
      </footer>
    </div>
  );
}
