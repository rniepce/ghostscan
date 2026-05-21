# GhostScan — Web app

Detector determinístico de injeção fantasma em PDFs, com interface web.

## Estrutura

- `ghostscan.py` — detector (CLI + biblioteca)
- `backend/` — API FastAPI que expõe `scan_pdf()` via HTTP
- `frontend/` — Vite + React + TypeScript + Tailwind

## Rodando local (dois terminais)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Abra <http://localhost:5173> e arraste um PDF.

## Verificação rápida via curl

```bash
curl -F "file=@algum.pdf" http://localhost:8000/api/scan | jq .
```
