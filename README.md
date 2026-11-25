# Kavach

A defence-only AI system that detects indicators of tampering or forgery in business documents (GST certificates, invoices/bills, bank/UPI statements, payment receipts) from images or PDFs, highlights where anomalies occurred, checks internal consistency, and returns a risk score with plain-English explanations.

## Structure

- `backend/` — FastAPI (Python 3.11+) document analysis API and pluggable analyzer pipeline
- `frontend/` — React + Vite + TypeScript + Tailwind CSS web interface
- `samples/` — Drop test documents (JPG, PNG, PDF) here
- `docker-compose.yml` — Local multi-service orchestration
- `AGENTS.md` — Project engineering and safety rules

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker Compose

```bash
docker compose up --build
```
