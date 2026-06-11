import os
import json
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import time
import logging
from typing import Optional, List, Dict, Any

from agent.executor import AgentExecutor
from core.os_control import capture_screenshot
from database.memory import get_chat_logs

# Setup rotating logs
import logging
from logging.handlers import RotatingFileHandler

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_dir = os.path.join(ROOT_DIR, "backend", "logs")
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
    allow_credentials=True,
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
    return {"message": "Tác vụ đã được bắt đầu", "status": agent.status}

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    if agent.status in ["running", "waiting_approval"]:
        raise HTTPException(status_code=400, detail="Agent đang bận xử lý tác vụ điều khiển.")
        
    res = agent.handle_chat_input(
        message=req.message,
        ai_mode=req.ai_mode,
        safety_confirmation=req.safety_confirmation
    )
    return res

@app.post("/api/approve")
def approve_action(background_tasks: BackgroundTasks):
    if agent.status != "waiting_approval" or not agent.pending_action:
        raise HTTPException(status_code=400, detail="Không có hành động nào đang chờ duyệt.")
    
    def execute_and_resume():
        agent.execute_pending_action()
        
    background_tasks.add_task(execute_and_resume)
    return {"message": "Đang thực thi hành động đã phê duyệt..."}

@app.post("/api/reject")
def reject_action(req: RejectRequest):
    if agent.status != "waiting_approval" or not agent.pending_action:
        raise HTTPException(status_code=400, detail="Không có hành động nào đang chờ duyệt.")
    
    agent.reject_pending_action(req.reason)
    return {"message": "Đã từ chối hành động", "status": agent.status}

@app.post("/api/stop")
def stop_agent():
    agent.status = "idle"
    agent.pending_action = None
    agent.add_log("system", "Dừng khẩn cấp mọi hoạt động theo yêu cầu của người dùng.", "failed")
    return {"message": "Đã dừng khẩn cấp Agent", "status": agent.status}

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
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    draft_path = os.path.join(ROOT_DIR, "workspace", "temp", "current_draft.json")
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
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    draft_path = os.path.join(ROOT_DIR, "workspace", "temp", "current_message_draft.json")
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
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_dir = os.path.join(ROOT_DIR, "config")
    db_dir = os.path.join(ROOT_DIR, "backend", "app", "database")
    
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
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_dir = os.path.join(ROOT_DIR, "config")
    db_dir = os.path.join(ROOT_DIR, "backend", "app", "database")
    
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
    
    return {"message": "Cấu hình đã được nhập thành công!", "imported": imported_keys}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
