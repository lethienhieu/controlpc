import logging
from typing import Dict, Any

logger = logging.getLogger("policy.risk")

def classify_action_risk(action: str, params: Dict[str, Any]) -> str:
    """
    Classifies the risk level of an action based on tool name and parameters.
    Returns: 'low', 'medium', 'high', or 'blocked'.
    """
    action_lower = action.lower()
    
    # 1. Blocked Actions: High-risk operations that are forbidden by default
    # e.g., deleting system files, running blocklisted tools, etc.
    if action_lower in ["system.delete_system_dir", "system.modify_registry"]:
        return "blocked"
        
    # Check if file paths target blocked directories
    for path_param in ["path", "file", "filepath", "target_path", "source_path", "dest_path"]:
        if path_param in params and isinstance(params[path_param], str):
            path_val = params[path_param].lower()
            if any(blocked in path_val for blocked in ["c:\\windows", "c:\\program files", "appdata"]):
                # Writing/deleting in system directories is blocked
                if "write" in action_lower or "delete" in action_lower or "copy" in action_lower:
                    return "blocked"

    # 2. High Risk Actions: operations that can send out information or delete files
    if action_lower in ["email.send", "message.send", "file.delete", "cli.run_system_command", "shell.run"]:
        return "high"
    
    # Click coordination and general execution is considered high-risk by default, UIA coordinates can be medium
    if action_lower == "click":
        return "high"
        
    if action_lower in ["email.attach_file", "file.overwrite"]:
        return "high"

    # 3. Medium Risk Actions: write files, rename, hotkeys, UIA clicks, open app outside allowlist
    if action_lower in [
        "file.copy", 
        "file.rename", 
        "file.create_folder", 
        "document.create_docx", 
        "document.create_pdf",
        "click_uia", 
        "type", 
        "press", 
        "hotkey"
    ]:
        return "medium"
        
    # If opening an app
    if action_lower == "open":
        app_name = params.get("app_name", "").lower()
        # Allowlist apps
        if app_name in ["notepad", "explorer", "word", "excel", "calculator"]:
            return "low"
        return "medium"

    # 4. Low Risk Actions: read-only operations
    if action_lower in [
        "file.search", 
        "file.open", 
        "file.preview_metadata", 
        "document.read_text", 
        "document.summarize",
        "email.create_draft", 
        "message.create_draft", 
        "learn", 
        "finish"
    ]:
        return "low"

    # Default fallback
    return "medium"
