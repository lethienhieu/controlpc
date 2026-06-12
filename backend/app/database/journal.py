"""Human-readable markdown memory (OpenClaw-style), layered on top of the SQLite
state. After each completed task we append a daily journal entry and refresh a
curated MEMORY.md that gets fed back into the agent's prompts — so the agent
"remembers" across sessions and gets more useful the more it's used.

    <brain>/memory/journal/YYYY-MM-DD.md   # one line-group per completed task
    <brain>/memory/MEMORY.md               # curated digest (apps, frequent + recent tasks)
"""
import os
import logging
from datetime import datetime
from typing import List, Dict, Any

from core import paths
from database import memory

logger = logging.getLogger("database.journal")


def _fmt_step(s: Dict[str, Any]) -> str:
    a = s.get("action", "?")
    p = s.get("params", {}) or {}
    key = (p.get("app_name") or p.get("to_email") or p.get("contact_query")
           or p.get("filepath") or p.get("command") or p.get("text") or p.get("message") or "")
    key = str(key).replace("\n", " ")[:40]
    return f"{a}({key})" if key else a


def _today_journal_path() -> str:
    return os.path.join(paths.journal_dir(), datetime.now().strftime("%Y-%m-%d") + ".md")


def append_task(goal: str, steps: List[Dict[str, Any]], result: str = "", ai_mode: str = "gemma4") -> bool:
    """Append a completed task to today's journal, then refresh MEMORY.md."""
    try:
        path = _today_journal_path()
        is_new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            if is_new:
                f.write(f"# CONTROLPC Journal — {datetime.now().strftime('%Y-%m-%d')}\n\n")
            f.write(f"### {datetime.now().strftime('%H:%M:%S')} — {goal}\n")
            if result:
                f.write(f"- **Result**: {result}\n")
            if steps:
                f.write("- **Steps**: " + " → ".join(_fmt_step(s) for s in steps) + "\n")
            f.write(f"- **Engine**: {ai_mode}\n\n")
        rebuild_memory_md()
        return True
    except Exception as e:
        logger.error(f"Failed to append journal: {e}")
        return False


def rebuild_memory_md() -> bool:
    """Regenerate the curated long-term memory digest from SQLite state."""
    try:
        apps = (memory.read_knowledge_base() or {}).get("apps", {})
        plans = memory.get_all_task_plans()

        lines = ["# CONTROLPC — Long-term Memory (MEMORY.md)", "",
                 "_Automatically updated after each completed task._", "",
                 "## Known Applications"]
        if apps:
            for name, p in list(apps.items())[:30]:
                lines.append(f"- **{name}** → `{p}`")
        else:
            lines.append("- (none yet)")

        lines += ["", "## Frequently Used Tasks"]
        freq = sorted(plans, key=lambda x: x["uses"], reverse=True)[:10]
        if freq:
            for p in freq:
                lines.append(f"- \"{p['goal']}\" — run {p['uses']} times")
        else:
            lines.append("- (none yet)")

        lines += ["", "## Recent Activity"]
        recent = sorted(plans, key=lambda x: x["last_used"], reverse=True)[:8]
        if recent:
            for p in recent:
                t = datetime.fromtimestamp(p["last_used"]).strftime("%Y-%m-%d %H:%M") if p["last_used"] else ""
                lines.append(f"- {t} — \"{p['goal']}\"")
        else:
            lines.append("- (none yet)")

        with open(os.path.join(paths.memory_dir(), "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception as e:
        logger.error(f"Failed to rebuild MEMORY.md: {e}")
        return False


def read_memory_md() -> str:
    try:
        p = os.path.join(paths.memory_dir(), "MEMORY.md")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""


def read_today_journal() -> str:
    try:
        p = _today_journal_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""


def read_memory_digest(max_chars: int = 1400) -> str:
    """Short MEMORY.md slice for injecting into prompts."""
    md = read_memory_md()
    return md[:max_chars] if md else ""
