# Kavach

A defence-only AI document verification service that detects indicators of tampering in business documents (GST certificates, invoices/bills, bank/UPI statements, payment receipts) from images or PDFs.

> **Responsible Use:** Kavach reports statistical, structural, and consistency **indicators of tampering** for manual review. It never constitutes legal proof of forgery or authenticity.

## Architecture

- **Backend (`backend/`)**: FastAPI (Python 3.11+) running as a **single `uvicorn` process** (`--workers 1`) with an in-process bounded `ThreadPoolExecutor` (`MAX_CONCURRENT_JOBS=2`), SQLite/SQLModel persistence (`DATA_DIR/kavach.db` with WAL mode, swappable via `DB_URL`), and a shared `RapidOCR` ONNXRuntime session.
  - *Why one `uvicorn` process?* Each RapidOCR ONNX session holds ~300 MB in memory and SQLite supports a single writer at a time; running one process with a bounded worker pool avoids model duplication and SQLite lock contention.
- **Pipeline**: Fixed order `ocr -> classify -> rules -> forensics -> scoring -> explain`, with per-analyzer timeouts and fault isolation.
- **Frontend (`frontend/`)**: React + Vite + TypeScript + Tailwind served in production via Nginx with `/api` reverse-proxied to `backend:8000`, security headers, and an access-code gate (`sessionStorage` + `HttpOnly` cookie).

## Quick Start (Local Development)

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
$env:KAVACH_API_KEYS="change-me-local-dev-key"
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Deployment

### Docker Compose (Production-like Local Run)

```bash
cp .env.example .env
# Edit .env and set a strong KAVACH_API_KEYS value
docker compose up --build -d
```

- Frontend: `http://localhost:8080`
- Backend health: `http://localhost:8000/health`

### Render (`render.yaml`)

1. Connect this repository in Render as a Blueprint (`render.yaml`).
2. Set secret `KAVACH_API_KEYS` and `CORS_ORIGINS` on `kavach-backend`.
3. Persistent disk `kavach-data` is mounted at `/data` for SQLite and temporary uploads.

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `KAVACH_ENV` | `development` | Environment name (`development` / `production`) |
| `DATA_DIR` | system temp `/kavach_data` | Directory for SQLite DB and temporary uploads |
| `DB_URL` | `sqlite:///{DATA_DIR}/kavach.db` | SQLModel database URL (swap to Postgres if needed) |
| `FILE_TTL_MINUTES` | `60` | Retention window before files & job rows are purged |
| `DELETE_AFTER_VIEW` | `false` | Redact extracted fields after completed result is viewed |
| `KAVACH_API_KEYS` | *(empty)* | Comma-separated access keys (hashed in memory) |
| `KAVACH_RATE_LIMIT` | `30/minute` | Per-key/IP rate limit on `POST /api/analyze` |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed CORS origins (comma-separated) |
| `TRUSTED_PROXIES` | `127.0.0.1,::1` | Proxy IPs trusted for `X-Forwarded-For` |
| `MAX_CONCURRENT_JOBS` | `2` | Worker pool concurrency |
| `MAX_QUEUE_LENGTH` | `16` | Max queued + active jobs before returning `503` |
| `MAX_PIXELS` | `25000000` | Maximum image pixel count (`width * height`) |
| `MAX_PDF_PAGES` | `10` | Maximum PDF page count |
| `KAVACH_ANALYZER_TIMEOUT_SECONDS` | `45.0` | Per-analyzer timeout |
| `SENTRY_DSN` | *(empty)* | Optional Sentry DSN (`send_default_pii=False` + scrubber) |

## Operations

- **Backup**: Copy `/data/kavach.db` (or run `sqlite3 /data/kavach.db ".backup /backup/kavach.db"`).
- **Restore**: Stop the backend, replace `/data/kavach.db` with the backup, and restart.
- **Rotate Access Keys**: Add the new key to `KAVACH_API_KEYS` (`old,new`), restart, update clients, then remove the old key and restart again.
- **Upgrade**: Pull the target release tag/branch, rebuild containers (`docker compose up --build -d`), and verify `/health` and `/ready`.

## Deploying with Vercel (Frontend) + Render/Docker (Backend) + Supabase (Postgres)

Because the backend bundles RapidOCR, ONNX Runtime, OpenCV, PyMuPDF, and scikit-image (exceeding Vercel's 250 MB serverless limit and requiring background worker threads), deploy the frontend on **Vercel** and the backend container on **Render** (or Railway / Fly.io):

1. **Supabase (Database)**:
   - Copy your Supabase Postgres connection string (Transaction Pooler port `6543` or Direct `5432`, with `?sslmode=require`).
   - Set `DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require` on the backend service (`db.py` automatically normalizes `postgres://`/`postgresql://` to `postgresql+psycopg://` and disables prepared statements for PgBouncer).
2. **Backend (Render via `render.yaml`)**:
   - Deploy `kavach-backend` from `backend/Dockerfile` with `KAVACH_API_KEYS`, `DB_URL` (Supabase), and `CORS_ORIGINS=https://<your-app>.vercel.app`.
3. **Frontend (Vercel)**:
   - Import the repo in Vercel with **Root Directory** set to `frontend` (`frontend/vercel.json` configures Vite + SPA rewrites; see `frontend/.env.example`).
   - Set `VITE_API_BASE=https://<your-backend-host>` (e.g. your Render URL, no trailing slash) and redeploy. Local `npm run dev` keeps Vite's `/api` proxy when `VITE_API_BASE` is unset.

## Known Limitations

- Low-resolution `480x640` images can cause OCR character drops; unconfirmed GSTIN reads emit a `warn` rather than a hard checksum failure.
- Single-occurrence amounts with no cross-check (e.g. a receipt total) cannot be mathematically verified by consistency rules alone.
- RapidOCR CPU inference can take several seconds per high-resolution page; timed-out analyzers cap `confidence <= 0.3` and warn that checks were incomplete.
