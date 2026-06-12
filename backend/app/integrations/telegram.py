import os
import json
import time
import hmac
import logging
import threading
import requests
from typing import Dict, Any, Optional

from database import memory
from core import paths

logger = logging.getLogger("integrations.telegram")

# WORKSPACE_DIR (repo root) used for user-visible mock-notification output.
INTEGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(INTEGRATIONS_DIR)))
SETTINGS_PATH = paths.config_file("messaging_settings.json")

def load_telegram_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_PATH):
        return {"safety_mode": "mock", "telegram_enabled": True}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading messaging settings: {e}")
        return {"safety_mode": "mock"}

def get_token() -> str:
    """Telegram bot token from the OS keyring (Credential Manager) or env."""
    from core import secrets as app_secrets
    return app_secrets.get_secret("telegram_token")


def tg_api(token: str, method: str, payload: Optional[dict] = None, params: Optional[dict] = None, timeout: int = 30):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if payload is not None:
        return requests.post(url, json=payload, timeout=timeout)
    return requests.get(url, params=params or {}, timeout=timeout)


def tg_send(token: str, chat_id, text: str) -> None:
    try:
        tg_api(token, "sendMessage", payload={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.warning(f"tg_send failed: {e}")


def send_telegram_notification(chat_id: str, text: str) -> Dict[str, Any]:
    """Send a notification to the remote user. Live via Bot API when a token is
    configured (Credential Manager / env); otherwise falls back to a mock file."""
    token = get_token()
    if token:
        try:
            res = tg_api(token, "sendMessage", payload={"chat_id": chat_id, "text": text}, timeout=10)
            if res.status_code == 200:
                return {"success": True, "mode": "live"}
            return {"success": False, "error": res.text}
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return {"success": False, "error": str(e)}
    # No token -> mock file (free, offline demo)
    noti_path = os.path.join(WORKSPACE_DIR, "workspace", "output", "telegram_notifications.txt")
    try:
        os.makedirs(os.path.dirname(noti_path), exist_ok=True)
        with open(noti_path, "a", encoding="utf-8") as f:
            f.write(f"[CHAT_ID: {chat_id}] {text}\n")
        return {"success": True, "mode": "mock"}
    except Exception as e:
        return {"success": False, "error": str(e)}

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

# "mock" is a dev-only canned decision tree; the live engine label is "gemma4"
# (any non-"mock" value routes to the real llama-server LLM). The local UI sets
# agent.ai_mode the first time it's used, but a remote command can arrive before
# that — fall back to the real engine so phone commands never run in mock mode.
REAL_AI_MODE = "gemma4"


def _effective_ai_mode(agent) -> str:
    return agent.ai_mode if agent.ai_mode and agent.ai_mode != "mock" else REAL_AI_MODE


def process_remote_command(channel: str, sender_id: str, text: str) -> Dict[str, Any]:
    """
    Validates the remote sender and routes their command to the Agent Executor.
    Matches schema, safety checks, and handles PIN confirmations for high risk tasks.
    """
    # Rate limit check
    sender_identity = f"{channel}:{sender_id}"
    if is_rate_limited(sender_identity):
        logger.warning(f"Rate limit exceeded for sender: {sender_identity}")
        return {"success": False, "message": "You are sending commands too quickly. Please wait a few seconds."}

    # Safety config check: remote_gateway_enabled must be True
    from policy.permissions import get_safety_settings
    safety_settings = get_safety_settings()
    if not safety_settings.get("remote_gateway_enabled", False):
        logger.warning(f"Remote gateway is disabled. Rejected command from {sender_identity}")
        return {"success": False, "message": "The Remote Gateway is disabled in the safety configuration."}

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
                pin=p.get("pin") or os.environ.get("CONTROLPC_REMOTE_PIN", "1234")
            )
            sender = memory.get_remote_sender(sender_identity)
            
    if not sender:
        logger.warning(f"Unauthorized access attempt from remote identity: {sender_identity}")
        return {"success": False, "message": "You are not authorized to control this system."}

    if not sender["enabled"]:
        return {"success": False, "message": "Your account is currently disabled."}
        
    # Import agent executor dynamically to avoid circular import issues
    import main
    agent = main.agent
    
    cmd_stripped = text.strip()
    
    # 2. Check if agent is waiting for PIN approval
    if agent.status == "waiting_approval" and agent.pending_action:
        # Verify if this sender is the one running the task, or has admin authorization
        if agent.sender_id == sender_id or sender["auth_level"] == "admin":
            # Check if this input matches the PIN (constant-time comparison).
            if hmac.compare_digest(str(cmd_stripped), str(sender["pin"])):
                # High-risk actions require a sender explicitly allowed to approve them.
                if (agent.pending_action.get("risk_level") == "high"
                        and not sender.get("can_approve_high_risk")):
                    return {
                        "success": False,
                        "message": "You are not authorized to approve high-risk actions from this device.",
                        "action": "denied",
                    }
                # Log approval in sqlite
                logger.info(f"Remote action approved by {sender['name']} via PIN.")
                agent.add_log("system", f"Remote approval from {sender['name']} via PIN succeeded.", "info")
                
                # Execute pending action asynchronously to respond back to TG quickly
                import threading
                threading.Thread(target=agent.execute_pending_action, daemon=True).start()
                
                return {
                    "success": True,
                    "message": "Approval successful! The action is now being executed.",
                    "action": "approved"
                }
            else:
                # If it looks like a PIN attempt (digits) or user sent bad input
                if cmd_stripped.isdigit():
                    return {
                        "success": False,
                        "message": "Incorrect PIN. Please try again.",
                        "action": "bad_pin"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"The system is waiting for a PIN to approve the action: {agent.pending_action['preview']['title']}. Please enter the PIN.",
                        "action": "waiting_pin"
                    }
                    
    # 3. Handle idle agent starting a new task
    if agent.status == "idle":
        if not sender["can_create_task"]:
            return {"success": False, "message": "Your account does not have permission to create new tasks."}
            
        # Update agent context with remote source
        agent.source_channel = channel
        agent.sender_id = sender_id
        
        # Start task
        agent.start(goal=text, ai_mode=_effective_ai_mode(agent), safety_confirmation=agent.safety_confirmation, source_channel=channel, sender_id=sender_id)
        
        # Check if it immediate entered waiting approval
        if agent.status == "waiting_approval":
            return {
                "success": True,
                "message": f"The task has been created. The next action requires authentication. Please enter the PIN to approve: {agent.pending_action['preview']['title']}",
                "action": "waiting_pin"
            }
            
        return {
            "success": True,
            "message": f"Remote command received and execution has started: '{text}'",
            "action": "task_started"
        }
        
    # 4. Handle agent currently running a task
    if agent.status in ["running", "waiting_approval"]:
        return {
            "success": False,
            "message": f"The system is busy performing a task: '{agent.current_goal}'. Status: {agent.status}.",
            "action": "system_busy"
        }
        
    return {"success": False, "message": "Invalid system state.", "action": "none"}


class _RemoteGateway:
    """Integrated Telegram long-polling gateway — runs in a background thread
    inside the backend (no separate process), free (no public IP needed).
    getUpdates(long-poll) -> process_remote_command -> reply via sendMessage."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._offset = 0
        self.bot_username = ""
        self.last_error = ""

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> Dict[str, Any]:
        if self.is_running():
            return {"success": True, "message": "Gateway is already running.", "bot_username": self.bot_username}
        token = get_token()
        if not token:
            return {"success": False, "message": "No Telegram token configured. Go to Settings → Security to enter one."}
        try:
            me = tg_api(token, "getMe", params={}, timeout=10).json()
            if not me.get("ok"):
                return {"success": False, "message": f"Invalid token: {me.get('description', me)}"}
            self.bot_username = me["result"].get("username", "")
        except Exception as e:
            return {"success": False, "message": f"Could not connect to Telegram: {e}"}
        # Drain pending updates so old messages aren't replayed when enabling.
        try:
            r = tg_api(token, "getUpdates", params={"offset": -1, "timeout": 0}, timeout=10).json()
            res = r.get("result", [])
            if res:
                self._offset = res[-1]["update_id"] + 1
        except Exception:
            pass
        self._stop.clear()
        self.last_error = ""
        self._thread = threading.Thread(target=self._loop, args=(token,), daemon=True)
        self._thread.start()
        logger.info(f"Telegram remote gateway started (@{self.bot_username}).")
        return {"success": True, "message": f"Enabled. Message the bot @{self.bot_username} to send commands.", "bot_username": self.bot_username}

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        self._thread = None
        logger.info("Telegram remote gateway stopped.")
        return {"success": True, "message": "Gateway disabled."}

    def status(self) -> Dict[str, Any]:
        return {"running": self.is_running(), "bot_username": self.bot_username, "last_error": self.last_error}

    def _loop(self, token: str):
        while not self._stop.is_set():
            try:
                r = tg_api(token, "getUpdates", params={"offset": self._offset, "timeout": 25}, timeout=35)
                if r.status_code != 200:
                    self.last_error = f"getUpdates HTTP {r.status_code}"
                    time.sleep(3)
                    continue
                for u in r.json().get("result", []):
                    self._offset = u["update_id"] + 1
                    msg = u.get("message") or {}
                    chat_id = (msg.get("chat") or {}).get("id")
                    text = msg.get("text")
                    if chat_id is None or not text:
                        continue
                    try:
                        result = process_remote_command("telegram", str(chat_id), text)
                        reply = result.get("message", "Received.")
                    except Exception as e:
                        logger.error(f"Remote command error: {e}")
                        reply = f"Error processing command: {e}"
                    tg_send(token, chat_id, reply)
            except requests.exceptions.RequestException as e:
                self.last_error = str(e)
                time.sleep(3)
            except Exception as e:
                self.last_error = str(e)
                time.sleep(3)


# Module-level singleton
gateway = _RemoteGateway()
