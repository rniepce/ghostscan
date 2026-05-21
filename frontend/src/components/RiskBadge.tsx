import type { RiskLevel } from "../types";

const STYLES: Record<RiskLevel, string> = {
  LIMPO: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  SUSPEITO: "bg-amber-100 text-amber-800 ring-amber-300",
  ALTO_RISCO: "bg-rose-100 text-rose-800 ring-rose-300",
};

const LABELS: Record<RiskLevel, string> = {
  LIMPO: "Limpo",
  SUSPEITO: "Suspeito",
  ALTO_RISCO: "Alto risco",
};

export function RiskBadge({ risco }: { risco: RiskLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-4 py-1.5 text-base font-semibold ring-1 ring-inset ${STYLES[risco]}`}
    >
      {LABELS[risco]}
    </span>
  );
}
