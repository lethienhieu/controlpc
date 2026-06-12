import os
import json
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import threading
import time
import logging
from typing import Optional, List, Dict, Any

from agent.executor import AgentExecutor
from core.os_control import capture_screenshot
from core import paths
from database.memory import get_chat_logs

# Setup rotating logs
import logging
from logging.handlers import RotatingFileHandler

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_dir = paths.logs_dir()
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "controlpc.log")

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Rotating File Handler (5MB size, 3 backup files)
file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)
root_logger.addHandler(file_handler)

# Stream Handler (stdout)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.INFO)
root_logger.addHandler(stream_handler)

logger = logging.getLogger("main")

app = FastAPI(title="CONTROLPC Local Agent API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Credentials are not used (no cookies/auth headers). Combining "*" origins
    # with allow_credentials=True is invalid per the CORS spec, so keep it off.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate global Agent Executor
agent = AgentExecutor()

# Background worker to drive the agent ReAct loop
def agent_background_worker():
    global agent
    logger.info("Starting background agent worker thread...")
    while True:
        try:
            if agent.status == "running" and not agent.pending_action:
                logger.info("Agent is running. Triggering next step...")
                agent.next_step()
        except Exception as e:
            logger.error(f"Error in background worker: {e}")
        time.sleep(0.5)

worker_thread = threading.Thread(target=agent_background_worker, daemon=True)
worker_thread.start()

# Auto-start the Telegram remote (mobile) gateway if it's enabled and a token is set.
try:
    from policy.permissions import get_safety_settings as _gss
    from integrations.telegram import gateway as _tg_gateway, get_token as _tg_token
    if _gss().get("remote_gateway_enabled", False) and _tg_token():
        logger.info("Auto-starting Telegram remote gateway...")
        _tg_gateway.start()
except Exception as _e:
    logger.error(f"Remote gateway auto-start skipped: {_e}")

# Pre-warm the GPU model in the background so the FIRST real command doesn't pay
# the cold-start cost (loading the GGUF into VRAM can take tens of seconds). Runs
# off-thread, so the UI/API stay responsive while the model loads.
def _warmup_llm():
    try:
        agent.llm.generate(prompt="ping", max_tokens=1, temperature=0.0)
        logger.info("LLM pre-warm complete (model resident in VRAM).")
    except Exception as _e:
        logger.warning(f"LLM pre-warm skipped: {_e}")

threading.Thread(target=_warmup_llm, daemon=True).start()

# Request schemas
class StartRequest(BaseModel):
    goal: str
    ai_mode: str = "mock"
    safety_confirmation: bool = True

class ChatRequest(BaseModel):
    message: str
    ai_mode: str = "mock"
    safety_confirmation: bool = True

class RejectRequest(BaseModel):
    reason: Optional[str] = "User rejected"

class TelegramRequest(BaseModel):
    sender_id: str
    text: str

# Endpoints
@app.get("/api/status")
def get_status():
    logs = get_chat_logs()
    return {
        "status": agent.status,
        "current_goal": agent.current_goal,
        "current_step": agent.current_step,
        "max_steps": agent.max_steps,
        "logs": logs,
        "pending_action": agent.pending_action,
        "ai_mode": agent.ai_mode,
        "safety_confirmation": agent.safety_confirmation,
        "model_path": agent.llm.model_path
    }

@app.post("/api/start")
def start_agent(req: StartRequest):
    if agent.status in ["running", "waiting_approval"]:
        raise HTTPException(status_code=400, detail="Agent is currently busy.")
    
    agent.start(
        goal=req.goal,
        ai_mode=req.ai_mode,
        safety_confirmation=req.safety_confirmation
    )
    return {"message": "Task has been started", "status": agent.status}

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    if agent.status in ["running", "waiting_approval"]:
        raise HTTPException(status_code=400, detail="Agent is currently busy handling a control task.")
        
    res = agent.handle_chat_input(
        message=req.message,
        ai_mode=req.ai_mode,
        safety_confirmation=req.safety_confirmation
    )
    return res

@app.post("/api/chat/stream")
def chat_stream_endpoint(req: ChatRequest):
    """SSE chat: classifies the message, then either signals a control task
    (frontend switches to polling) or streams the chat reply token-by-token."""
    if agent.status in ["running", "waiting_approval"]:
        raise HTTPException(status_code=400, detail="Agent is currently busy handling a control task.")

    def sse(obj: Dict[str, Any]) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    def event_gen():
        agent.ai_mode = req.ai_mode
        agent.safety_confirmation = req.safety_confirmation
        # 1. Classify
        try:
            is_control = agent.classifier.classify(req.message, ai_mode=req.ai_mode)
        except Exception as e:
            yield sse({"type": "error", "message": f"Classification error: {e}"})
            return
        # 2a. Control command -> start task, tell UI to switch to polling
        if is_control:
            agent.start(goal=req.message, ai_mode=req.ai_mode, safety_confirmation=req.safety_confirmation)
            yield sse({"type": "control", "status": agent.status})
            return
        # 2b. Chat -> stream the reply
        full = ""
        try:
            for delta in agent.stream_chat_reply(req.message, ai_mode=req.ai_mode):
                full += delta
                yield sse({"type": "chunk", "delta": delta})
        except Exception as e:
            yield sse({"type": "error", "message": f"Local model error: {e}"})
            return
        agent.status = "idle"
        yield sse({"type": "done", "message": full})

    return StreamingResponse(event_gen(), media_type="text/event-stream")

@app.post("/api/approve")
def approve_action(background_tasks: BackgroundTasks):
    if agent.status != "waiting_approval" or not agent.pending_action:
        raise HTTPException(status_code=400, detail="There is no action awaiting approval.")
    
    def execute_and_resume():
        agent.execute_pending_action()
        
    background_tasks.add_task(execute_and_resume)
    return {"message": "Executing the approved action..."}

@app.post("/api/reject")
def reject_action(req: RejectRequest):
    if agent.status != "waiting_approval" or not agent.pending_action:
        raise HTTPException(status_code=400, detail="There is no action awaiting approval.")
    
    agent.reject_pending_action(req.reason)
    return {"message": "Action rejected", "status": agent.status}

@app.post("/api/stop")
def stop_agent():
    agent.status = "idle"
    agent.pending_action = None
    agent.add_log("system", "Emergency stop of all activity at the user's request.", "failed")
    return {"message": "Agent emergency-stopped", "status": agent.status}

@app.get("/api/screenshot")
def get_screenshot():
    if agent.status == "waiting_approval" and agent.pending_action:
        tool = agent.pending_action.get("tool") or agent.pending_action.get("action")
        if tool == "click":
            params = agent.pending_action.get("params", {})
            x = params.get("x")
            y = params.get("y")
            if x is not None and y is not None:
                return capture_screenshot(draw_cursor=True, click_marker=(x, y))
    return capture_screenshot()

@app.get("/api/download_status")
def get_download_status():
    exists = os.path.exists(agent.llm.model_path) if agent.llm.model_path else False
    size = os.path.getsize(agent.llm.model_path) if exists else 0
    return {
        "is_downloading": False,
        "exists": exists,
        "file_size": size,
        "model_path": agent.llm.model_path
    }

@app.get("/api/email_draft")
def get_email_draft():
    import json
    draft_path = os.path.join(paths.run_dir(), "email_draft.json")
    if os.path.exists(draft_path):
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                return {"exists": True, "draft": json.load(f)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"exists": False}

@app.get("/api/message_draft")
def get_message_draft():
    import json
    draft_path = os.path.join(paths.run_dir(), "message_draft.json")
    if os.path.exists(draft_path):
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                return {"exists": True, "draft": json.load(f)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"exists": False}

@app.post("/api/remote/telegram")
def telegram_remote_endpoint(req: TelegramRequest):
    from integrations.telegram import process_remote_command
    res = process_remote_command(channel="telegram", sender_id=req.sender_id, text=req.text)
    return res

@app.get("/api/uia/windows")
def get_uia_windows():
    from core.uia_control import get_active_windows
    return {"windows": get_active_windows()}

@app.get("/api/uia/tree")
def get_uia_tree(window_title_re: str):
    from core.uia_control import get_control_tree
    return {"controls": get_control_tree(window_title_re)}

class ImportSettingsRequest(BaseModel):
    settings: Dict[str, Any]

@app.get("/api/settings/export")
def export_settings():
    """
    Exports all JSON configurations and knowledge base settings as a single dictionary.
    """
    config_dir = paths.config_dir()
    db_dir = paths.state_dir()

    settings_data = {}
    
    # Export config files
    for filename in ["contacts.json", "email_settings.json", "messaging_settings.json", "permissions.json"]:
        path = os.path.join(config_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    settings_data[f"config/{filename}"] = json.load(f)
            except Exception as e:
                settings_data[f"config/{filename}"] = f"Error reading: {e}"
                
    # Export knowledge base
    kb_path = os.path.join(db_dir, "knowledge_base.json")
    if os.path.exists(kb_path):
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                settings_data["database/knowledge_base.json"] = json.load(f)
        except Exception as e:
            settings_data["database/knowledge_base.json"] = f"Error reading: {e}"
            
    return settings_data

@app.post("/api/settings/import")
def import_settings(req: ImportSettingsRequest):
    """
    Imports configurations and knowledge base settings from a dictionary.
    """
    config_dir = paths.config_dir()
    db_dir = paths.state_dir()

    imported_keys = []
    
    for key, data in req.settings.items():
        if key.startswith("config/"):
            filename = key.split("/")[-1]
            if filename in ["contacts.json", "email_settings.json", "messaging_settings.json", "permissions.json"]:
                path = os.path.join(config_dir, filename)
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    imported_keys.append(key)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to write {key}: {e}")
                    
        elif key == "database/knowledge_base.json":
            kb_path = os.path.join(db_dir, "knowledge_base.json")
            try:
                with open(kb_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                imported_keys.append(key)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to write {key}: {e}")
                
    # Force reload permissions cache after importing
    from policy.permissions import reload_permissions
    reload_permissions()
    
    return {"message": "Configuration imported successfully!", "imported": imported_keys}

class SetSecretRequest(BaseModel):
    name: str
    value: str

ALLOWED_SECRETS = {"smtp_password", "telegram_token"}

@app.post("/api/settings/set_secret")
def set_secret_endpoint(req: SetSecretRequest):
    """Stores a secret in the OS keyring (Windows Credential Manager)."""
    from core import secrets as app_secrets
    if req.name not in ALLOWED_SECRETS:
        raise HTTPException(status_code=400, detail=f"Invalid secret name. Allowed: {sorted(ALLOWED_SECRETS)}")
    if not app_secrets.backend_available():
        raise HTTPException(status_code=500, detail="No secure secret store (keyring/Credential Manager) is available.")
    ok = app_secrets.set_secret(req.name, req.value)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save the secret.")
    return {"message": f"Saved '{req.name}' securely to Windows Credential Manager.", "name": req.name}

@app.get("/api/settings/secret_status")
def secret_status():
    from core import secrets as app_secrets
    return {
        "keyring_available": app_secrets.backend_available(),
        "secrets": {name: app_secrets.has_secret(name) for name in sorted(ALLOWED_SECRETS)},
    }

@app.get("/api/system/status")
def system_status():
    """Aggregate setup/health for the Settings checklist."""
    from policy.permissions import get_safety_settings
    from core import secrets as app_secrets
    try:
        email_settings = json.load(open(paths.config_file("email_settings.json"), encoding="utf-8"))
    except Exception:
        email_settings = {}
    safety = get_safety_settings()
    return {
        "model_path": agent.llm.model_path,
        "model_found": bool(agent.llm.model_path and os.path.exists(agent.llm.model_path)),
        "server_found": bool(agent.llm.server_exe and os.path.exists(agent.llm.server_exe)),
        "remote_gateway_enabled": safety.get("remote_gateway_enabled", False),
        "coordinate_click_enabled": safety.get("coordinate_click_enabled", False),
        "permission_mode": safety.get("permission_mode", "ask"),
        "email_mode": email_settings.get("safety_mode", "mock"),
        "keyring_available": app_secrets.backend_available(),
        "smtp_password_set": app_secrets.has_secret("smtp_password"),
    }

class EditPendingRequest(BaseModel):
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    text: Optional[str] = None
    contact_query: Optional[str] = None

@app.post("/api/pending/edit")
def edit_pending(req: EditPendingRequest):
    """Edit the content of a pending email/message action before approving it."""
    if agent.status != "waiting_approval" or not agent.pending_action:
        raise HTTPException(status_code=400, detail="There is no action awaiting approval.")
    updates = {k: v for k, v in req.dict().items() if v is not None}
    res = agent.edit_pending_action(updates)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "This action cannot be edited."))
    return res

@app.get("/api/audit/verify")
def audit_verify():
    """Verify the tamper-evident hash chain of the audit log."""
    from database.memory import verify_audit_chain
    return verify_audit_chain()

@app.get("/api/memory")
def get_memory():
    """Human-readable agent memory: curated MEMORY.md + today's journal."""
    from database import journal
    return {"memory_md": journal.read_memory_md(), "journal_today": journal.read_today_journal()}

@app.get("/api/models/list")
def list_models():
    """List selectable GGUF models found in <repo>/models plus the active one."""
    import glob
    from agent.llm import load_model_config
    cur = load_model_config().get("model_path") or agent.llm.model_path or ""
    found = {}
    models_root = os.path.join(paths.REPO_ROOT, "models")
    if os.path.isdir(models_root):
        for p in glob.glob(os.path.join(models_root, "*.gguf")):
            found[os.path.abspath(p)] = os.path.basename(p)
    if cur and os.path.exists(cur):
        found[os.path.abspath(cur)] = os.path.basename(cur)
    cur_abs = os.path.abspath(cur) if cur else ""
    models = [{"name": n, "path": p, "active": (p == cur_abs)} for p, n in sorted(found.items(), key=lambda x: x[1].lower())]
    return {"models": models, "active": cur}

# ── Telegram remote (mobile) gateway ──────────────────────────────────────
class RemoteToggleRequest(BaseModel):
    enable: bool

class RemoteOwnerRequest(BaseModel):
    telegram_id: str
    pin: str = "1234"

def _set_remote_gateway_enabled(enable: bool):
    from policy import permissions
    try:
        with open(permissions.CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("safety_settings", {})["remote_gateway_enabled"] = bool(enable)
    with open(permissions.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    permissions.reload_permissions()

@app.get("/api/remote/status")
def remote_status():
    from integrations.telegram import gateway, get_token
    from policy.permissions import get_safety_settings
    import sqlite3
    from database import memory as mem
    owners = []
    try:
        conn = sqlite3.connect(mem.SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        for r in conn.execute("SELECT sender_identity, name FROM remote_senders WHERE enabled=1"):
            if str(r["sender_identity"]).startswith("telegram:"):
                owners.append({"id": r["sender_identity"], "name": r["name"]})
        conn.close()
    except Exception:
        pass
    return {
        "enabled": get_safety_settings().get("remote_gateway_enabled", False),
        "token_set": bool(get_token()),
        "owners": owners,
        **gateway.status(),
    }

@app.post("/api/remote/toggle")
def remote_toggle(req: RemoteToggleRequest):
    from integrations.telegram import gateway, get_token
    if req.enable:
        if not get_token():
            raise HTTPException(status_code=400, detail="No Telegram token yet. Go to Settings → Security to enter one first.")
        _set_remote_gateway_enabled(True)
        res = gateway.start()
        if not res.get("success"):
            _set_remote_gateway_enabled(False)
            raise HTTPException(status_code=400, detail=res.get("message", "Could not enable the gateway."))
        return res
    _set_remote_gateway_enabled(False)
    return gateway.stop()

@app.post("/api/remote/set_owner")
def remote_set_owner(req: RemoteOwnerRequest):
    tid = req.telegram_id.strip().replace("telegram:", "")
    if not tid.isdigit():
        raise HTTPException(status_code=400, detail="Telegram ID must be a numeric string (get it from @userinfobot).")
    from database import memory as mem
    mem.add_remote_sender(
        sender_identity=f"telegram:{tid}", name="Owner", enabled=True, auth_level="admin",
        can_create_task=True, can_approve_high_risk=True, requires_pin_for_high_risk=True,
        pin=(req.pin or "1234"),
    )
    mem.delete_remote_sender("telegram:123456789")  # drop the placeholder default
    return {"success": True, "message": f"Granted control permission to telegram:{tid}."}

class PermissionModeRequest(BaseModel):
    mode: str  # "ask" | "smart" | "bypass"

@app.post("/api/settings/set_permission_mode")
def set_permission_mode(req: PermissionModeRequest):
    """Persist how strictly the agent asks for approval before acting.
    ask = confirm everything · smart = only risky actions · bypass = no prompts."""
    mode = (req.mode or "").strip().lower()
    if mode not in ("ask", "smart", "bypass"):
        raise HTTPException(status_code=400, detail="Invalid mode (ask/smart/bypass).")
    from policy import permissions
    try:
        with open(permissions.CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("safety_settings", {})["permission_mode"] = mode
    with open(permissions.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    permissions.reload_permissions()
    return {"success": True, "permission_mode": mode}

class SetModelRequest(BaseModel):
    model_path: str
    context: Optional[int] = None

@app.post("/api/settings/set_model")
def set_model_endpoint(req: SetModelRequest):
    """Switch the active GGUF model (any chat model: Gemma, Qwen3, ...).
    The chat template is taken from the GGUF, so no code changes are needed."""
    from agent.llm import load_model_config, save_model_config, LocalLLM
    if req.model_path and not os.path.exists(req.model_path):
        raise HTTPException(status_code=400, detail=f"Model file not found: {req.model_path}")
    cfg = load_model_config()
    cfg["model_path"] = req.model_path
    if req.context:
        cfg["context"] = req.context
    if not save_model_config(cfg):
        raise HTTPException(status_code=500, detail="Failed to save the model configuration.")
    # Restart the GPU server so the new model loads on the next inference call.
    LocalLLM.stop_server()
    new_path = agent.llm.reload_model_config()
    return {"message": "Model changed. The GPU server will load the new model on the next inference call.", "model_path": new_path}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
