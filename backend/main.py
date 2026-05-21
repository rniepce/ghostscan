"""API HTTP que expõe o detector ghostscan para uso via web.

Camada fina: recebe o PDF, salva em arquivo temporário, delega para
scan_pdf() e devolve o ScanResult serializado em JSON. Nenhuma lógica
de detecção mora aqui.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# importa o módulo ghostscan que vive um diretório acima
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ghostscan import scan_pdf, Config  # noqa: E402


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — peça processual razoável


app = FastAPI(title="GhostScan API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/scan")
async def scan(file: UploadFile = File(...)) -> dict:
    # validação de boundary: só PDF
    nome = file.filename or "arquivo.pdf"
    if not nome.lower().endswith(".pdf"):
        raise HTTPException(400, "arquivo deve ter extensão .pdf")
    if file.content_type and file.content_type not in (
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
    ):
        raise HTTPException(400, f"mimetype inesperado: {file.content_type}")

    conteudo = await file.read()
    if len(conteudo) == 0:
        raise HTTPException(400, "arquivo vazio")
    if len(conteudo) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"arquivo excede {MAX_UPLOAD_BYTES // (1024*1024)} MB")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(conteudo)
        tmp.flush()
        try:
            resultado = scan_pdf(tmp.name, cfg=Config(), usar_ocr=True)
        except Exception as e:
            raise HTTPException(500, f"falha ao analisar PDF: {e}")

    payload = resultado.to_dict()
    payload["arquivo"] = nome  # devolve o nome original, não o tempfile
    return payload
