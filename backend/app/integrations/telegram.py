import os
import json
import logging
import requests
from typing import Dict, Any, Optional

from database import memory

logger = logging.getLogger("integrations.telegram")

# Resolve folders
INTEGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(INTEGRATIONS_DIR)))
SETTINGS_PATH = os.path.join(WORKSPACE_DIR, "config", "messaging_settings.json")

def load_telegram_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_PATH):
        return {"safety_mode": "mock", "telegram_enabled": True}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading messaging settings: {e}")
        return {"safety_mode": "mock"}

def send_telegram_notification(chat_id: str, text: str) -> Dict[str, Any]:
    """
    Sends a notification back to the remote user via Telegram.
    If safety_mode is 'mock', it appends to workspace/output/telegram_notifications.txt.
    """
    settings = load_telegram_settings()
    safety_mode = settings.get("safety_mode", "mock").lower()
    
    if safety_mode == "mock":
        noti_path = os.path.join(WORKSPACE_DIR, "workspace", "output", "telegram_notifications.txt")
        try:
            with open(noti_path, "a", encoding="utf-8") as f:
                f.write(f"[CHAT_ID: {chat_id}] {text}\n")
            logger.info(f"[MOCK TG NOTIFICATION] Sent to {chat_id}: {text}")
            return {"success": True, "mode": "mock"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        # Live Telegram sending
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return {"success": False, "error": "TELEGRAM_BOT_TOKEN environment variable not set."}
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                logger.info(f"Successfully sent Telegram notification to {chat_id}")
                return {"success": True, "mode": "live"}
            else:
                return {"success": False, "error": res.text}
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return {"success": False, "error": str(e)}

import time

# Simple in-memory rate limiter: sender_identity -> list of timestamps
_rate_limits = {}

def is_rate_limited(sender_identity: str) -> bool:
    now = time.time()
    timestamps = _rate_limits.get(sender_identity, [])
    # Keep only timestamps from the last 10 seconds
    timestamps = [t for t in timestamps if now - t < 10]
    _rate_limits[sender_identity] = timestamps
    
    if len(timestamps) >= 5:  # limit to 5 commands per 10 seconds
        return True
    timestamps.append(now)
    return False

def process_remote_command(channel: str, sender_id: str, text: str) -> Dict[str, Any]:
    """
    Validates the remote sender and routes their command to the Agent Executor.
    Matches schema, safety checks, and handles PIN confirmations for high risk tasks.
    """
    # Rate limit check
    sender_identity = f"{channel}:{sender_id}"
    if is_rate_limited(sender_identity):
        logger.warning(f"Rate limit exceeded for sender: {sender_identity}")
        return {"success": False, "message": "Bạn đang gửi lệnh quá nhanh. Vui lòng đợi vài giây."}

    # Safety config check: remote_gateway_enabled must be True
    from policy.permissions import get_safety_settings
    safety_settings = get_safety_settings()
    if not safety_settings.get("remote_gateway_enabled", False):
        logger.warning(f"Remote gateway is disabled. Rejected command from {sender_identity}")
        return {"success": False, "message": "Cổng điều khiển từ xa (Remote Gateway) đang bị tắt trong cấu hình an toàn."}

    # 1. Authorize sender
    sender = memory.get_remote_sender(sender_identity)
    
    if not sender:
        # Check permissions.json configuration fallback
        from policy import permissions
        perms = permissions.load_permissions().get("remote_sender_permissions", {})
        if sender_identity in perms:
            p = perms[sender_identity]
            memory.add_remote_sender(
                sender_identity=sender_identity,
                name=p.get("name", "Remote User"),
                enabled=p.get("enabled", True),
                auth_level=p.get("auth_level", "create_task"),
                can_create_task=p.get("can_create_task", True),
                can_approve_high_risk=p.get("can_approve_high_risk", False),
                requires_pin_for_high_risk=p.get("requires_pin_for_high_risk", True),
                pin="1234"  # Default pin
            )
            sender = memory.get_remote_sender(sender_identity)
            
    if not sender:
        logger.warning(f"Unauthorized access attempt from remote identity: {sender_identity}")
        return {"success": False, "message": "Bạn không được ủy quyền để điều khiển hệ thống này."}
        
    if not sender["enabled"]:
        return {"success": False, "message": "Tài khoản của bạn hiện đang bị vô hiệu hóa."}
        
    # Import agent executor dynamically to avoid circular import issues
    import main
    agent = main.agent
    
    cmd_stripped = text.strip()
    
    # 2. Check if agent is waiting for PIN approval
    if agent.status == "waiting_approval" and agent.pending_action:
        # Verify if this sender is the one running the task, or has admin authorization
        if agent.sender_id == sender_id or sender["auth_level"] == "admin":
            # Check if this input matches the PIN
            if cmd_stripped == sender["pin"]:
                # Log approval in sqlite
                logger.info(f"Remote action approved by {sender['name']} via PIN.")
                agent.add_log("system", f"Phê duyệt từ xa từ {sender['name']} bằng mã PIN thành công.", "info")
                
                # Execute pending action asynchronously to respond back to TG quickly
                import threading
                threading.Thread(target=agent.execute_pending_action, daemon=True).start()
                
                return {
                    "success": True,
                    "message": "Phê duyệt thành công! Hành động đang được thực thi.",
                    "action": "approved"
                }
            else:
                # If it looks like a PIN attempt (digits) or user sent bad input
                if cmd_stripped.isdigit():
                    return {
                        "success": False,
                        "message": "Mã PIN không đúng. Vui lòng thử lại.",
                        "action": "bad_pin"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Hệ thống đang chờ mã PIN để phê duyệt hành động: {agent.pending_action['preview']['title']}. Vui lòng nhập mã PIN.",
                        "action": "waiting_pin"
                    }
                    
    # 3. Handle idle agent starting a new task
    if agent.status == "idle":
        if not sender["can_create_task"]:
            return {"success": False, "message": "Tài khoản của bạn không có quyền tạo tác vụ mới."}
            
        # Update agent context with remote source
        agent.source_channel = channel
        agent.sender_id = sender_id
        
        # Start task
        agent.start(goal=text, ai_mode=agent.ai_mode, safety_confirmation=agent.safety_confirmation, source_channel=channel, sender_id=sender_id)
        
        # Check if it immediate entered waiting approval
        if agent.status == "waiting_approval":
            return {
                "success": True,
                "message": f"Tác vụ đã được tạo. Hành động tiếp theo đòi hỏi xác thực. Vui lòng nhập mã PIN để phê duyệt: {agent.pending_action['preview']['title']}",
                "action": "waiting_pin"
            }
            
        return {
            "success": True,
            "message": f"Đã nhận lệnh từ xa và bắt đầu thực thi: '{text}'",
            "action": "task_started"
        }
        
    # 4. Handle agent currently running a task
    if agent.status in ["running", "waiting_approval"]:
        return {
            "success": False,
            "message": f"Hệ thống đang bận thực hiện tác vụ: '{agent.current_goal}'. Trạng thái: {agent.status}.",
            "action": "system_busy"
        }
        
    return {"success": False, "message": "Trạng thái hệ thống không hợp lệ.", "action": "none"}
