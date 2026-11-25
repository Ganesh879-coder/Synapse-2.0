# Kavach Frontend

React + Vite + TypeScript + Tailwind CSS web UI for Kavach.

## Commands

```bash
cd frontend
npm install
npm run build
```

## Mock Mode vs. Real Backend

- **Mock mode** (no backend required, loads fixtures from `public/mock/`):

```bash
# PowerShell
$env:VITE_MOCK="1"; npm run dev

# bash
VITE_MOCK=1 npm run dev
```

- **Real backend mode** (proxies `/api/*` to `http://localhost:8000` by default; override with `VITE_API_BASE`):

```bash
npm run dev
```
