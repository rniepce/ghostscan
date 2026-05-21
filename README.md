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

## Deploy no Railway

São **dois serviços** apontando para o mesmo repositório.

### Serviço 1 — backend

- **Root Directory**: `/` (raiz do repo) — necessário para o Python encontrar `ghostscan.py`
- **Builder**: Nixpacks (detecta `requirements.txt` na raiz)
- **Start Command**: já em [Procfile](Procfile) / [railway.json](railway.json):
  `uvicorn main:app --host 0.0.0.0 --port $PORT --app-dir backend`
- **Variáveis de ambiente**:
  - `ALLOWED_ORIGINS=https://<seu-frontend>.up.railway.app` (defina depois que o frontend tiver domínio)
- Gere um domínio público (Settings → Networking → Generate Domain)

### Serviço 2 — frontend

- **Root Directory**: `/frontend`
- **Builder**: Nixpacks (detecta `package.json`)
- **Build Command** e **Start Command**: já em [frontend/railway.json](frontend/railway.json)
- **Variáveis de ambiente**:
  - `VITE_API_URL=https://<seu-backend>.up.railway.app` (URL do serviço 1)
- Gere um domínio público

### Ordem recomendada

1. Suba primeiro o backend, anote a URL pública
2. Crie o frontend service, configure `VITE_API_URL` apontando para o backend
3. Anote a URL do frontend, volte ao backend e configure `ALLOWED_ORIGINS`
4. Redeploy do backend
