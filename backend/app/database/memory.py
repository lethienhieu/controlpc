import os
import json
import sqlite3
import logging
import threading
import time
from typing import Dict, Any, Optional, List

logger = logging.getLogger("memory")
lock = threading.Lock()

DB_DIR = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(DB_DIR, "knowledge_base.json")
SQLITE_PATH = os.path.join(DB_DIR, "history.db")

# Ensure SQLite DB is initialized
def init_db():
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                step INTEGER,
                type TEXT,
                message TEXT,
                status TEXT,
                action_data TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                action_id TEXT UNIQUE,
                tool TEXT,
                risk_level TEXT,
                decision TEXT,
                confirmation_mode TEXT,
                target TEXT,
                params TEXT,
                reason TEXT,
                rollback_hint TEXT,
                source_channel TEXT,
                sender_id TEXT,
                executed_status TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS remote_senders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_identity TEXT UNIQUE,
                name TEXT,
                enabled INTEGER,
                auth_level TEXT,
                can_create_task INTEGER,
                can_approve_high_risk INTEGER,
                requires_pin_for_high_risk INTEGER,
                pin TEXT
            )
        """)
        # Seed default admin telegram sender if empty
        cursor.execute("SELECT COUNT(*) FROM remote_senders")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO remote_senders (sender_identity, name, enabled, auth_level, can_create_task, can_approve_high_risk, requires_pin_for_high_risk, pin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("telegram:123456789", "Owner", 1, "admin", 1, 1, 1, "1234")
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to initialize SQLite: {e}")

init_db()

def read_knowledge_base() -> Dict[str, Any]:
    with lock:
        if not os.path.exists(KB_PATH):
            return {"apps": {}, "custom_triggers": {}}
        try:
            with open(KB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading knowledge base: {e}")
            return {"apps": {}, "custom_triggers": {}}

def write_knowledge_base(data: Dict[str, Any]) -> bool:
    with lock:
        try:
            with open(KB_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error writing knowledge base: {e}")
            return False

def get_app_path(app_name: str) -> Optional[str]:
    from core.discovery import find_best_app_match

    data = read_knowledge_base()
    app_name_lower = app_name.lower().strip()
    apps = data.get("apps", {})

    if app_name_lower in apps:
        return apps[app_name_lower]

    match = find_best_app_match(app_name_lower, apps)
    return match[1] if match else None

def save_app_path(app_name: str, path: str) -> bool:
    data = read_knowledge_base()
    if "apps" not in data:
        data["apps"] = {}
    data["apps"][app_name.lower().strip()] = path.strip()
    return write_knowledge_base(data)

def save_chat_log(step: int, step_type: str, message: str, status: str = "info", action_data: Optional[Dict] = None) -> bool:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        action_data_str = json.dumps(action_data) if action_data else None
        cursor.execute(
            "INSERT INTO chat_logs (timestamp, step, type, message, status, action_data) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), step, step_type, message, status, action_data_str)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save chat log: {e}")
        return False

def get_chat_logs() -> List[Dict[str, Any]]:
    logs = []
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chat_logs ORDER BY id ASC")
        rows = cursor.fetchall()
        for r in rows:
            action_data = None
            if r["action_data"]:
                try:
                    action_data = json.loads(r["action_data"])
                except:
                    pass
            logs.append({
                "timestamp": r["timestamp"],
                "step": r["step"],
                "type": r["type"],
                "message": r["message"],
                "status": r["status"],
                "action_data": action_data
            })
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch chat logs: {e}")
    return logs

def save_audit_log(policy_res: Dict[str, Any], source_channel: str = "local_ui", sender_id: str = "user", executed_status: str = "pending") -> bool:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO audit_logs 
               (timestamp, action_id, tool, risk_level, decision, confirmation_mode, target, params, reason, rollback_hint, source_channel, sender_id, executed_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(),
                policy_res.get("action_id"),
                policy_res.get("tool"),
                policy_res.get("risk_level"),
                policy_res.get("decision"),
                policy_res.get("confirmation_mode"),
                json.dumps(policy_res.get("target", {})),
                json.dumps(policy_res.get("params", {})),
                policy_res.get("reason"),
                policy_res.get("rollback_hint"),
                source_channel,
                sender_id,
                executed_status
            )
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save audit log: {e}")
        return False

def update_audit_log_status(action_id: str, executed_status: str) -> bool:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE audit_logs SET executed_status = ? WHERE action_id = ?",
            (executed_status, action_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to update audit log status: {e}")
        return False

def get_audit_logs() -> List[Dict[str, Any]]:
    logs = []
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC")
        rows = cursor.fetchall()
        for r in rows:
            logs.append({
                "timestamp": r["timestamp"],
                "action_id": r["action_id"],
                "tool": r["tool"],
                "risk_level": r["risk_level"],
                "decision": r["decision"],
                "confirmation_mode": r["confirmation_mode"],
                "target": json.loads(r["target"]) if r["target"] else {},
                "params": json.loads(r["params"]) if r["params"] else {},
                "reason": r["reason"],
                "rollback_hint": r["rollback_hint"],
                "source_channel": r["source_channel"],
                "sender_id": r["sender_id"],
                "executed_status": r["executed_status"]
            })
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch audit logs: {e}")
    return logs

def get_remote_sender(sender_identity: str) -> Optional[Dict[str, Any]]:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM remote_senders WHERE sender_identity = ?", (sender_identity,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "sender_identity": row["sender_identity"],
                "name": row["name"],
                "enabled": bool(row["enabled"]),
                "auth_level": row["auth_level"],
                "can_create_task": bool(row["can_create_task"]),
                "can_approve_high_risk": bool(row["can_approve_high_risk"]),
                "requires_pin_for_high_risk": bool(row["requires_pin_for_high_risk"]),
                "pin": row["pin"]
            }
    except Exception as e:
        logger.error(f"Failed to get remote sender: {e}")
    return None

def verify_remote_sender_pin(sender_identity: str, pin: str) -> bool:
    sender = get_remote_sender(sender_identity)
    if sender:
        return sender["pin"] == pin
    return False

def add_remote_sender(sender_identity: str, name: str, enabled: bool, auth_level: str, can_create_task: bool, can_approve_high_risk: bool, requires_pin_for_high_risk: bool, pin: str) -> bool:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO remote_senders 
               (sender_identity, name, enabled, auth_level, can_create_task, can_approve_high_risk, requires_pin_for_high_risk, pin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (sender_identity, name, int(enabled), auth_level, int(can_create_task), int(can_approve_high_risk), int(requires_pin_for_high_risk), pin)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to add remote sender: {e}")
        return False

