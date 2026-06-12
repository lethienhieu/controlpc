# 🖥️ CONTROLPC — Local OS AI Agent

> **Control your Windows PC with natural language — running 100% locally on your GPU.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)](https://react.dev)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

CONTROLPC is a fully local Windows OS-control agent. You type (or send from your
phone) a natural-language command; a ReAct agent — powered by a local GGUF LLM on
your GPU via `llama.cpp` — plans and executes it through reliable, structured
channels (launch-by-path, keyboard shortcuts, Windows UI Automation, allowlisted
CLI). No cloud inference, no Ollama. Secrets live in Windows Credential Manager and
risky actions require your approval.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🤖 **ReAct agent** | Multi-step plan & execute with a local GGUF LLM, **fully on the GPU** |
| 🧩 **Model-agnostic** | Any GGUF chat model (Qwen3, Gemma, …) via bundled `llama.cpp` `llama-server` (CUDA). The chat template is read from the model file. |
| ⌨️ **Structured control** | Prefers `open` (path/registry), keyboard shortcuts, Windows UI Automation (UIA) and allowlisted CLI over fragile coordinate clicks |
| 🔍 **Smart app launch** | Disambiguates app names (opens *Revit*, not *Revit Worksharing Monitor*) and asks when unsure |
| 🧠 **Procedural memory** | Caches successful task plans + a human-readable markdown journal so repeats run instantly |
| 📧 **Email / 💬 messaging** | Draft-first email (SMTP) and messaging with per-contact policies |
| 📡 **Phone control (Telegram)** | Free remote control via a Telegram bot (long-polling, no public IP) with PIN approval |
| 🛡️ **Safety policy** | Per-action risk classification, approval modes, allowlists, tamper-evident audit log |

---

## ✅ Prerequisites

- **Windows 10/11** (UI Automation uses Windows APIs)
- **Python 3.10+** (tested on 3.12 and 3.14)
- **Node.js 18+** and npm
- **NVIDIA GPU** recommended (~8 GB VRAM runs a 9B Q5 model at context 4096). A
  smaller GGUF needs less; a CPU-only `llama.cpp` build also works, just slower.
- **~5–7 GB free disk per model**

---

## 🚀 Install & run

```bash
# 1. Clone
git clone https://github.com/lethienhieu/controlpc.git
cd controlpc
```

**2. Get the inference engine** (kept out of git — it is large binaries).
Download a Windows **CUDA** build of `llama.cpp` from
[github.com/ggml-org/llama.cpp/releases](https://github.com/ggml-org/llama.cpp/releases)
and extract it into `llama\` so that `llama\llama-server.exe` and its DLLs sit there.
(CPU-only builds also work.)

**3. Get a model** (also kept out of git):

```powershell
# Edit scripts\download_models.ps1 and paste a HuggingFace .gguf URL, then:
powershell -ExecutionPolicy Bypass -File .\scripts\download_models.ps1
```

…or simply drop any `.gguf` file into `models\`. Good starting points are an
official **Qwen3-8B** or **Gemma** instruct GGUF. You can switch models later in
the app (**Settings → Model**).

**4. Launch:**

```bash
start.bat
```

`start.bat` (portable — resolves its own path via `%~dp0`) automatically creates the
Python virtual environment, installs dependencies, builds the frontend bundle, and
opens the desktop window.

> If you keep the engine/model elsewhere, point to them with the
> `CONTROLPC_LLAMA_SERVER` / `CONTROLPC_LLAMA_MODEL` environment variables instead
> of using `llama\` / `models\`.

---

## 🧠 How it works (first run)

- All runtime state lives in **`%LOCALAPPDATA%\ControlPC`** (e.g.
  `C:\Users\<you>\AppData\Local\ControlPC`) — created automatically on first run,
  separate from the code so it stays writable even if the app is installed under
  `Program Files`.
  ```
  %LOCALAPPDATA%\ControlPC\
  ├─ brain.json   # manifest + schema version
  ├─ config/      # active config (seeded from the repo's /config on first run)
  ├─ state/       # durable memory to back up: history.db + knowledge_base.json
  ├─ logs/        # rotating logs
  ├─ cache/       # regenerable (screenshots) — safe to delete
  └─ run/         # in-progress email/message drafts
  ```
  Back up `state/` (and `config/`). To reset cleanly, delete the `ControlPC` folder.
  Override the location with `CONTROLPC_BRAIN_DIR`.
- The GPU `llama-server` is started **lazily** on the first inference and pre-warmed
  in the background at startup, then reused and stopped on exit.
- `desktop.py` prints a health check (model found, GPU server found, frontend bundle)
  on launch.

---

## ⚙️ Configuration

Active config files live in `…\ControlPC\config\`; the repo's `config/` holds the
git-tracked defaults that seed them.

**`config/permissions.json`** (real schema):
```json
{
  "file_permissions": { "allowed_read_dirs": ["..."], "allowed_write_dirs": ["..."], "blocked_dirs": ["..."] },
  "app_permissions": { "notepad": { "launch": "allow" } },
  "contact_permissions": { "default": { "policy": "confirm_before_send" } },
  "remote_sender_permissions": { },
  "safety_settings": {
    "coordinate_click_enabled": false,
    "remote_gateway_enabled": false,
    "permission_mode": "ask"
  }
}
```

**`config/email_settings.json`** (real keys — no password on disk):
```json
{ "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_user": "you@example.com", "from_email": "you@example.com", "safety_mode": "mock" }
```
The SMTP password is **never** stored on disk — set it in the app UI (saved to
Windows Credential Manager) or via the `CONTROLPC_SMTP_PASSWORD` env var.
`safety_mode: "mock"` (the default) writes an `.eml` draft instead of sending.

### Environment variables

| Variable | Purpose |
|---|---|
| `CONTROLPC_LLAMA_SERVER` | Path to `llama-server.exe` (overrides `llama\`) |
| `CONTROLPC_LLAMA_MODEL` | Path to the `.gguf` model (overrides `models\`) |
| `CONTROLPC_BRAIN_DIR` | Override the `%LOCALAPPDATA%\ControlPC` data dir |
| `CONTROLPC_SMTP_PASSWORD` | SMTP password fallback (Credential Manager preferred) |
| `CONTROLPC_TELEGRAM_TOKEN` | Telegram bot token fallback (Credential Manager preferred) |
| `CONTROLPC_REMOTE_PIN` | Default remote PIN (change it before enabling remote!) |

### Approval modes (Settings → Approval mode)

- 🛡️ **Ask** (default) — confirm every action.
- ⚖️ **Smart** — only confirm medium/high-risk actions.
- ⚡ **Bypass** — auto-approve everything (hard-blocked actions stay blocked). Use
  only if you fully trust the agent.

---

## 📡 Phone control (Telegram — free)

1. Create a bot with [@BotFather](https://t.me/botfather) → copy the token.
2. In the app: **Settings → 🔐 Security** → paste the token → Save (stored in
   Windows Credential Manager).
3. Get your numeric Telegram ID from [@userinfobot](https://t.me/userinfobot).
4. **Settings → 📱** → enter your Telegram ID + a PIN → **Grant access**.
5. Click **▶ Enable phone control**, then message your bot a command.

The PIN defaults to `1234` — **change it before enabling real remote access.**
High-risk actions require a PIN and an explicitly authorized sender. Free: it uses
Telegram long-polling, so no public IP or server is needed.

---

## 🛡️ Safety model

```
User / remote command
      ▼  IntentClassifier   → chat vs. control
      ▼  ReActPlanner       → JSON-constrained next action (local LLM)
      ▼  ActionPolicy       → risk level + allowlists + approval mode
      ▼  AgentExecutor      → executes (with approval for risky actions)
```

- Coordinate clicking is **disabled by default** (last resort only).
- Remote gateway is **off by default**; the audit log is a SHA-256 hash chain.
- File access is restricted to allowlisted directories.

See [docs/UPGRADE_NOTES.md](docs/UPGRADE_NOTES.md) for the current review backlog.

---

## 🧪 Tests

```bash
backend\venv\Scripts\python test_policy.py
backend\venv\Scripts\python test_tools.py
backend\venv\Scripts\python test_remote.py
backend\venv\Scripts\python test_email.py
backend\venv\Scripts\python test_messaging.py
backend\venv\Scripts\python test_planner.py
```

---

## 🔧 Troubleshooting

- **"Model not found" / "llama-server not found"** — make sure a `.gguf` is in
  `models\` and the CUDA `llama.cpp` build is in `llama\`, or set the
  `CONTROLPC_LLAMA_*` env vars.
- **Port 8000 already in use** — another instance is running; close it or change the
  port in `desktop.py`.
- **`start.bat` can't find Python** — the Microsoft Store `python` alias can shadow a
  real install. Install Python from python.org and ensure `where python` resolves to it.
- **First command is slow** — the model is loading into VRAM (cold start). Subsequent
  commands are fast, and repeated tasks replay from the plan cache.

---

## 🗺️ Roadmap

Zalo OA / WhatsApp Business connectors, a file-search index, vision-based click
fallback, and an installer. See [docs/UPGRADE_NOTES.md](docs/UPGRADE_NOTES.md).

---

## 📄 License

MIT — see [LICENSE](LICENSE).

<div align="center"><strong>Built with ❤️ — CONTROLPC Local OS AI Agent</strong></div>
