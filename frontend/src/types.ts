export type RiskLevel = "LIMPO" | "SUSPEITO" | "ALTO_RISCO";

export type SignalType =
  | "cor_camuflada"
  | "fonte_minuscula"
  | "render_invisivel"
  | "fora_da_pagina"
  | "caractere_oculto"
  | "divergencia_ocr"
  | "ocr_indisponivel"
  | "base64_instrucao"
  | "instrucao_embutida";

export interface Signal {
  tipo: SignalType;
  pagina: number;
  trecho: string;
  detalhe: string;
  bbox?: [number, number, number, number] | null;
}

export interface ScanResult {
  arquivo: string;
  risco: RiskLevel;
  paginas_analisadas: number;
  ocr_executado: boolean;
  total_sinais: number;
  sinais: Signal[];
  erro: string | null;
}
