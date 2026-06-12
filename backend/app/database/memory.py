import os
import json
import sqlite3
import hashlib
import hmac
import logging
import threading
import time
from typing import Dict, Any, Optional, List

from core import paths

logger = logging.getLogger("memory")
lock = threading.Lock()

# Durable agent memory lives in the brain's state dir (not inside the code pkg).
KB_PATH = os.path.join(paths.state_dir(), "knowledge_base.json")
SQLITE_PATH = os.path.join(paths.state_dir(), "history.db")

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
                executed_status TEXT,
                prev_hash TEXT,
                entry_hash TEXT
            )
        """)
        # Idempotent migration for older DBs missing the hash-chain columns.
        for col in ("prev_hash", "entry_hash"):
            try:
                cursor.execute(f"ALTER TABLE audit_logs ADD COLUMN {col} TEXT")
            except Exception:
                pass
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
        # Procedural memory / skill library: successful goal -> action plan,
        # so repeated tasks replay instantly without re-asking the LLM.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_plans (
                goal_norm TEXT PRIMARY KEY,
                goal_original TEXT,
                steps TEXT,
                uses INTEGER DEFAULT 1,
                last_used REAL
            )
        """)
        # Seed default admin telegram sender if empty. The default PIN can be
        # overridden via the CONTROLPC_REMOTE_PIN env var (change it before
        # enabling the remote gateway in production).
        cursor.execute("SELECT COUNT(*) FROM remote_senders")
        if cursor.fetchone()[0] == 0:
            default_pin = os.environ.get("CONTROLPC_REMOTE_PIN", "1234")
            cursor.execute(
                "INSERT INTO remote_senders (sender_identity, name, enabled, auth_level, can_create_task, can_approve_high_risk, requires_pin_for_high_risk, pin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("telegram:123456789", "Owner", 1, "admin", 1, 1, 1, default_pin)
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

def _canonical_audit(ts: float, action_id, tool, risk_level, decision, confirmation_mode,
                     target_json, params_json, reason, rollback_hint, source_channel, sender_id) -> str:
    """Deterministic string over the IMMUTABLE insert-time fields (executed_status
    is intentionally excluded — it changes over the action lifecycle)."""
    return json.dumps({
        "timestamp": ts, "action_id": action_id, "tool": tool, "risk_level": risk_level,
        "decision": decision, "confirmation_mode": confirmation_mode, "target": target_json,
        "params": params_json, "reason": reason, "rollback_hint": rollback_hint,
        "source_channel": source_channel, "sender_id": sender_id,
    }, sort_keys=True, ensure_ascii=False)

def _entry_hash(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256(((prev_hash or "") + canonical).encode("utf-8")).hexdigest()

def save_audit_log(policy_res: Dict[str, Any], source_channel: str = "local_ui", sender_id: str = "user", executed_status: str = "pending") -> bool:
    conn = None
    try:
        with lock:
            conn = sqlite3.connect(SQLITE_PATH)
            cursor = conn.cursor()
            # Previous link in the tamper-evident chain.
            cursor.execute("SELECT entry_hash FROM audit_logs ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            prev_hash = row[0] if row and row[0] else ""

            ts = time.time()
            target_json = json.dumps(policy_res.get("target", {}))
            params_json = json.dumps(policy_res.get("params", {}))
            canonical = _canonical_audit(
                ts, policy_res.get("action_id"), policy_res.get("tool"), policy_res.get("risk_level"),
                policy_res.get("decision"), policy_res.get("confirmation_mode"), target_json, params_json,
                policy_res.get("reason"), policy_res.get("rollback_hint"), source_channel, sender_id,
            )
            entry_hash = _entry_hash(prev_hash, canonical)

            cursor.execute(
                """INSERT INTO audit_logs
                   (timestamp, action_id, tool, risk_level, decision, confirmation_mode, target, params, reason, rollback_hint, source_channel, sender_id, executed_status, prev_hash, entry_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts, policy_res.get("action_id"), policy_res.get("tool"), policy_res.get("risk_level"),
                    policy_res.get("decision"), policy_res.get("confirmation_mode"), target_json, params_json,
                    policy_res.get("reason"), policy_res.get("rollback_hint"), source_channel, sender_id,
                    executed_status, prev_hash, entry_hash,
                )
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save audit log: {e}")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

def verify_audit_chain() -> Dict[str, Any]:
    """Recompute the hash chain and confirm no row was inserted, altered, or reordered."""
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        return {"valid": False, "error": str(e), "checked": 0}

    prev = ""
    checked = 0
    legacy = 0
    for r in rows:
        # Rows written before the hash-chain feature have no entry_hash; they
        # predate integrity tracking and are skipped (unverifiable legacy).
        if not r["entry_hash"]:
            legacy += 1
            continue
        canonical = _canonical_audit(
            r["timestamp"], r["action_id"], r["tool"], r["risk_level"], r["decision"],
            r["confirmation_mode"], r["target"], r["params"], r["reason"], r["rollback_hint"],
            r["source_channel"], r["sender_id"],
        )
        expected = _entry_hash(prev, canonical)
        if (r["prev_hash"] or "") != prev or r["entry_hash"] != expected:
            return {"valid": False, "checked": checked, "total": len(rows),
                    "legacy_skipped": legacy, "broken_at": r["action_id"]}
        prev = r["entry_hash"]
        checked += 1
    return {"valid": True, "checked": checked, "total": len(rows), "legacy_skipped": legacy}

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

def _normalize_goal(goal: str) -> str:
    """Normalize a goal for cache lookup (lowercase, strip diacritics/space)."""
    try:
        from policy.action_policy import normalize_label
        g = normalize_label(goal or "")
    except Exception:
        g = (goal or "").lower()
    return " ".join(g.split())


def get_task_plan(goal: str) -> Optional[List[Dict[str, Any]]]:
    """Return a previously-learned action plan for this goal, or None."""
    norm = _normalize_goal(goal)
    if not norm:
        return None
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT steps FROM task_plans WHERE goal_norm = ?", (norm,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            steps = json.loads(row[0])
            if isinstance(steps, list) and steps:
                return steps
    except Exception as e:
        logger.error(f"Failed to read task plan: {e}")
    return None


def save_task_plan(goal: str, steps: List[Dict[str, Any]]) -> bool:
    """Persist a successful goal -> action plan (procedural memory). Bumps a
    usage counter so the system learns which tasks recur."""
    norm = _normalize_goal(goal)
    if not norm or not steps:
        return False
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT uses FROM task_plans WHERE goal_norm = ?", (norm,))
        row = cursor.fetchone()
        uses = (row[0] + 1) if row and row[0] else 1
        cursor.execute(
            "INSERT OR REPLACE INTO task_plans (goal_norm, goal_original, steps, uses, last_used) VALUES (?, ?, ?, ?, ?)",
            (norm, goal, json.dumps(steps, ensure_ascii=False), uses, time.time())
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save task plan: {e}")
        return False


def get_all_task_plans() -> List[Dict[str, Any]]:
    """All learned task plans (for the markdown memory digest)."""
    out = []
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT goal_original, goal_norm, uses, last_used FROM task_plans ORDER BY uses DESC, last_used DESC")
        for r in cursor.fetchall():
            out.append({"goal": r["goal_original"] or r["goal_norm"], "uses": r["uses"] or 1, "last_used": r["last_used"] or 0})
        conn.close()
    except Exception as e:
        logger.error(f"Failed to read task plans: {e}")
    return out


def delete_task_plan(goal: str) -> bool:
    """Drop a learned plan (e.g. when it turned out stale on replay)."""
    norm = _normalize_goal(goal)
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_plans WHERE goal_norm = ?", (norm,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to delete task plan: {e}")
        return False


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

def delete_remote_sender(sender_identity: str) -> bool:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.cursor().execute("DELETE FROM remote_senders WHERE sender_identity = ?", (sender_identity,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to delete remote sender: {e}")
        return False


def verify_remote_sender_pin(sender_identity: str, pin: str) -> bool:
    sender = get_remote_sender(sender_identity)
    if sender:
        return hmac.compare_digest(str(sender["pin"]), str(pin))
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

