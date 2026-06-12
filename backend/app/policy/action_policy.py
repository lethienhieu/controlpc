import logging
import uuid
from typing import Dict, Any, Tuple

from policy import risk, permissions

logger = logging.getLogger("policy.action_policy")

def normalize_label(s: str) -> str:
    s = s.lower()
    replacements = {
        'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
        'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
        'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
        'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
        'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
        'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        'đ': 'd',
        '_': ' ', '-': ' '
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s

class ActionPolicy:
    def __init__(self):
        # Initialize default policies or configs if needed
        pass

    def evaluate_action(self, tool: str, params: Dict[str, Any], intent: str = "general", reason: str = "", safety_confirmation: bool = True) -> Dict[str, Any]:
        """
        Evaluates an action proposal against safety policy rules.
        Returns a dict conforming to the Action Schema:
        {
            "action_id": str,
            "tool": str,
            "intent": str,
            "risk_level": str,     # 'low', 'medium', 'high', 'blocked'
            "decision": str,       # 'allowed', 'blocked', 'requires_confirmation'
            "confirmation_mode": str, # 'none', 'notify', 'confirm_once', 'confirm_final', 'manual_only'
            "target": dict,
            "params": dict,
            "reason": str,
            "preview": {
                "title": str,
                "summary": str
            },
            "rollback_hint": str
        }
        """
        action_id = f"act_{uuid.uuid4().hex[:8]}"
        
        # 1. Classify risk level
        risk_level = risk.classify_action_risk(tool, params)
        
        # Default structures
        target = {}
        preview_title = f"Execute: {tool}"
        preview_summary = f"Run the {tool} tool with parameters: {params}"
        rollback_hint = "This cannot be easily undone."
        
        decision = "allowed"
        confirmation_mode = "none"
        
        # Resolve target information
        if "path" in params:
            target["file"] = params["path"]
        elif "file" in params:
            target["file"] = params["file"]
        elif "filepath" in params:
            target["file"] = params["filepath"]
            
        if "app_name" in params:
            target["app"] = params["app_name"]
            
        if "recipient" in params:
            target["recipient"] = params["recipient"]
        elif "to" in params:
            target["recipient"] = params["to"]

        # 2. Blocked Risk Level immediately blocks the action
        if risk_level == "blocked":
            return self._build_result(
                action_id, tool, intent, risk_level, "blocked", "manual_only",
                target, params, reason, "Blocked by the security system",
                "This action falls outside the safety scope and is prohibited from execution.",
                "This action is not permitted to run."
            )

        # 3. Check specific tool permissions
        tool_lower = tool.lower()
        
        # File Read check
        if tool_lower in ["file.open", "document.read_text", "document.summarize"]:
            filepath = params.get("path") or params.get("file") or params.get("filepath", "")
            if filepath and not permissions.check_file_read_permission(filepath):
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "File access blocked",
                    f"No permission to read the file at path: {filepath}",
                    "This action is not permitted to run."
                )
                
        # File Write check
        if tool_lower in ["file.copy", "file.rename", "file.create_folder", "document.create_docx", "document.create_pdf"]:
            destpath = params.get("dest_path") or params.get("path") or params.get("file") or params.get("filepath", "")
            if destpath and not permissions.check_file_write_permission(destpath):
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "File create/write blocked",
                    f"No write permission, or invalid file extension at: {destpath}",
                    "This action is not permitted to run."
                )

        # App launch checks
        if tool_lower == "open":
            app_name = params.get("app_name", "")
            launch_policy = permissions.get_app_launch_policy(app_name)
            
            if launch_policy == "block":
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Application launch blocked",
                    f"The application '{app_name}' is in the blocked-launch list.",
                    "This action is not permitted to run."
                )
            elif launch_policy == "confirm":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_once"
                preview_title = f"Open application '{app_name}'"
                preview_summary = f"Request to launch the application '{app_name}' outside the official allowlist."
                rollback_hint = "The application can be closed manually."
                
        # Shell command: must be allowlisted, always high-risk confirmation.
        if tool_lower == "shell.run":
            shell_kind = params.get("shell", "powershell")
            command = params.get("command", "")
            if not permissions.check_cli_command_permission(shell_kind, command):
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Shell command blocked",
                    f"The command '{command}' is not in the allowlist for '{shell_kind}'.",
                    "Add the command to config/permissions.json if it is truly needed."
                )
            decision = "requires_confirmation"
            confirmation_mode = "confirm_final"
            preview_title = f"Run {shell_kind} command"
            preview_summary = f"Execute (allowlisted): {command}"
            rollback_hint = "Shell commands may not be reversible."

        # Click Coordination Safety
        if tool_lower == "click":
            safety = permissions.get_safety_settings()
            click_enabled = safety.get("coordinate_click_enabled", False)
            if not click_enabled:
                # If coordinate click is globally disabled, downgrade or block it
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Coordinate click blocked",
                    "Coordinate-based mouse clicks are currently disabled in the safety configuration.",
                    "Please enable coordinate clicking in settings if it is truly necessary."
                )
            else:
                decision = "requires_confirmation"
                confirmation_mode = "confirm_final"
                preview_title = "Coordinate-based mouse click"
                preview_summary = f"Click the mouse at coordinates X={params.get('x')}, Y={params.get('y')} on the screen."
                rollback_hint = "A mouse click action cannot be undone."

        # Email / Message send checks
        if tool_lower in ["email.send", "message.send"]:
            recipient = target.get("recipient", "default")
            send_policy = permissions.get_contact_send_policy(recipient)
            
            if send_policy == "blocked":
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Message send blocked",
                    f"The contact '{recipient}' is in the list barred from automatic sending.",
                    "This action is not permitted to run."
                )
            elif send_policy == "draft_only":
                # If contact only allows drafting, block the send tool call
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Message send blocked (drafts only allowed)",
                    f"The contact '{recipient}' only accepts draft creation. Direct sending is not allowed.",
                    "Replace with a draft-creation action instead."
                )
            elif send_policy == "confirm_before_send":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_final"
                preview_title = "Send real message / email"
                preview_summary = f"Send content to '{recipient}'. This action will send data externally."
                rollback_hint = "Cannot be undone once the email/message has been sent."
            elif send_policy == "auto_send_allowed":
                # Allowed to send automatically without confirmation
                decision = "allowed"
                confirmation_mode = "none"

        # Dangerous labels check: Send, Delete, Pay, Submit
        is_dangerous_click = False
        if tool_lower == "click_uia":
            name_val = normalize_label(str(params.get("name") or ""))
            auto_id_val = normalize_label(str(params.get("auto_id") or ""))
            for label in ["send", "delete", "pay", "submit", "gui", "xoa", "thanh toan", "nop"]:
                if label in name_val or label in auto_id_val:
                    is_dangerous_click = True
                    break
                    
        if is_dangerous_click:
            risk_level = "high"
            decision = "requires_confirmation"
            confirmation_mode = "confirm_final"
            preview_title = f"Click dangerous label: {params.get('name') or params.get('auto_id')}"
            preview_summary = f"Warning: clicking the sensitive/dangerous button '{params.get('name') or params.get('auto_id')}'."
            rollback_hint = "A mouse click action cannot be undone."

        # 4. Fallback based on Risk Level if not explicitly resolved
        if decision == "allowed":
            if risk_level == "high":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_final"
            elif risk_level == "medium":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_once"
            elif risk_level == "low":
                decision = "allowed"
                confirmation_mode = "none"

        # Permission mode (persisted in safety_settings) decides how aggressively we
        # ask the user to approve actions. Hard "blocked" results already returned
        # early above, so the safety rails are never weakened by any mode here.
        #   "ask"    -> confirm every still-allowed action (safest; default)
        #   "smart"  -> only the risk-based confirmations (medium/high) stand
        #   "bypass" -> auto-approve everything that isn't hard-blocked (no prompts)
        try:
            mode = permissions.get_safety_settings().get("permission_mode")
        except Exception:
            mode = None
        if not mode:
            # Back-compat with the old boolean toggle when no mode is persisted.
            mode = "ask" if safety_confirmation else "smart"

        if mode == "bypass":
            if decision == "requires_confirmation":
                decision = "allowed"
                confirmation_mode = "none"
        elif mode == "ask":
            if decision == "allowed" and tool_lower not in ["finish", "learn"]:
                decision = "requires_confirmation"
                confirmation_mode = "confirm_once"
        # mode == "smart": leave the risk-based decision untouched.

        return self._build_result(
            action_id, tool, intent, risk_level, decision, confirmation_mode,
            target, params, reason, preview_title, preview_summary, rollback_hint
        )

    def _build_result(
        self, action_id: str, tool: str, intent: str, risk_level: str,
        decision: str, confirmation_mode: str, target: Dict[str, Any],
        params: Dict[str, Any], reason: str, preview_title: str,
        preview_summary: str, rollback_hint: str
    ) -> Dict[str, Any]:
        return {
            "action_id": action_id,
            "tool": tool,
            "intent": intent,
            "risk_level": risk_level,
            "decision": decision,
            "confirmation_mode": confirmation_mode,
            "target": target,
            "params": params,
            "reason": reason,
            "preview": {
                "title": preview_title,
                "summary": preview_summary
            },
            "rollback_hint": rollback_hint
        }
