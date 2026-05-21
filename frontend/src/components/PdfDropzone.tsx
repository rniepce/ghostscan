import { useCallback, useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
}

export function PdfDropzone({ onFile, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [hover, setHover] = useState(false);

  const handle = useCallback(
    (f: File | null | undefined) => {
      if (!f) return;
      if (!f.name.toLowerCase().endsWith(".pdf")) {
        alert("Selecione um arquivo PDF.");
        return;
      }
      onFile(f);
    },
    [onFile]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setHover(true);
      }}
      onDragLeave={() => setHover(false)}
      onDrop={(e) => {
        e.preventDefault();
        setHover(false);
        if (disabled) return;
        handle(e.dataTransfer.files?.[0]);
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      className={`flex h-64 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed transition ${
        hover
          ? "border-indigo-500 bg-indigo-50"
          : "border-slate-300 bg-white hover:border-slate-400"
      } ${disabled ? "pointer-events-none opacity-60" : ""}`}
    >
      <svg
        className="mb-3 h-10 w-10 text-slate-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
          d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2"
        />
      </svg>
      <p className="text-sm font-medium text-slate-700">
        Arraste o PDF aqui ou <span className="text-indigo-600">clique para selecionar</span>
      </p>
      <p className="mt-1 text-xs text-slate-500">Apenas arquivos .pdf, até 50 MB</p>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => handle(e.target.files?.[0])}
      />
    </div>
  );
}
