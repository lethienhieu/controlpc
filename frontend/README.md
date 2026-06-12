# CONTROLPC — Frontend

React 19 + Vite UI (dark glassmorphism chat interface) for the CONTROLPC local OS
agent. It is served inside a PyWebView desktop shell by `desktop.py`.

## Development

- `npm install` — install dependencies
- `npm run dev` — Vite dev server at http://localhost:5173 (`desktop.py` falls back
  to this automatically if no production build exists)
- `npm run build` — production bundle into `dist/` (the repo-root `start.bat` runs
  this for you)

The backend API runs separately at http://localhost:8000 — see the repo-root
[README](../README.md).
