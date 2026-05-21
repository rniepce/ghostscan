import type { Signal, SignalType } from "../types";

const TIPO_LABEL: Record<SignalType, string> = {
  cor_camuflada: "Cor camuflada",
  fonte_minuscula: "Fonte minúscula",
  render_invisivel: "Render invisível",
  fora_da_pagina: "Fora da página",
  caractere_oculto: "Caractere oculto",
  divergencia_ocr: "Divergência OCR",
  ocr_indisponivel: "OCR indisponível",
  base64_instrucao: "Base64 com instrução",
  instrucao_embutida: "Instrução embutida (texto visível)",
};

function SignalRow({ s }: { s: Signal }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-slate-800">{TIPO_LABEL[s.tipo] ?? s.tipo}</span>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          página {s.pagina}
        </span>
      </div>
      {s.trecho && (
        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2 font-mono text-xs text-slate-700">
          {s.trecho}
        </pre>
      )}
      <p className="mt-2 text-xs text-slate-600">{s.detalhe}</p>
    </li>
  );
}

export function SignalsTable({ sinais }: { sinais: Signal[] }) {
  const ocultacao = sinais.filter((s) => s.tipo !== "instrucao_embutida");
  const observacoes = sinais.filter((s) => s.tipo === "instrucao_embutida");

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Sinais de ocultação ({ocultacao.length})
          <span className="ml-2 font-normal normal-case text-slate-400">— afetam o nível de risco</span>
        </h2>
        {ocultacao.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
            Nenhum sinal de ocultação detectado.
          </p>
        ) : (
          <ul className="space-y-2">
            {ocultacao.map((s, i) => (
              <SignalRow key={i} s={s} />
            ))}
          </ul>
        )}
      </section>

      {observacoes.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Observações para revisão humana ({observacoes.length})
            <span className="ml-2 font-normal normal-case text-slate-400">
              — linguagem de comando no texto visível; pode ser citação legítima
            </span>
          </h2>
          <ul className="space-y-2">
            {observacoes.map((s, i) => (
              <SignalRow key={i} s={s} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
