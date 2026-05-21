# Backend GhostScan

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Endpoints:

- `GET  /api/health` — healthcheck
- `POST /api/scan` — multipart com campo `file` (PDF). Retorna `ScanResult` em JSON.

Teste:

```bash
curl -F "file=@../algum.pdf" http://localhost:8000/api/scan | jq .
```
