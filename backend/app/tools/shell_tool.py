import subprocess
import logging
from typing import Dict, Any

from policy import permissions

logger = logging.getLogger("tools.shell_tool")


def run_command(command: str, shell: str = "powershell") -> Dict[str, Any]:
    """Run an ALLOWLISTED shell command (query/inspect/launch ops) — the
    structured alternative to blind coordinate clicking.

    The command must match the allowlist for the chosen shell in
    config/permissions.json (``app_permissions.<shell>.allowed_commands``).
    Arbitrary shell is refused. Pattern: OpenClaw/UFO-style structured
    primitives instead of pixel clicks (see .claude/patterns.md)."""
    if not command or not command.strip():
        return {"success": False, "error": "Empty command."}

    shell = (shell or "powershell").lower().strip()
    if shell not in ("powershell", "cmd"):
        return {"success": False, "error": f"Unsupported shell: {shell}"}

    if not permissions.check_cli_command_permission(shell, command):
        return {
            "success": False,
            "error": (f"Command is not in the allowlist for '{shell}': '{command}'. "
                      f"Add it to config/permissions.json → app_permissions.{shell}.allowed_commands if it is truly needed."),
        }

    try:
        if shell == "powershell":
            args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            args = ["cmd", "/c", command]
        logger.info(f"Running allowlisted {shell} command: {command}")
        res = subprocess.run(args, capture_output=True, text=True, timeout=30)
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        if len(out) > 4000:
            out = out[:4000] + "\n...(truncated)"
        ok = res.returncode == 0
        return {
            "success": ok,
            "output": out,
            "error": err if not ok else "",
            "returncode": res.returncode,
            "message": f"Executed ({shell}): {command}",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out (30s timeout)."}
    except Exception as e:
        logger.error(f"Shell command failed: {e}")
        return {"success": False, "error": str(e)}
