import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("policy.permissions")

# Resolve permissions.json path
POLICY_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(POLICY_DIR)))
CONFIG_PATH = os.path.join(WORKSPACE_DIR, "config", "permissions.json")

_cached_permissions: Optional[Dict[str, Any]] = None

def load_permissions() -> Dict[str, Any]:
    """
    Loads permission configuration from config/permissions.json.
    Caches the results for subsequent calls.
    """
    global _cached_permissions
    if _cached_permissions is not None:
        return _cached_permissions
        
    if not os.path.exists(CONFIG_PATH):
        logger.warning(f"Permissions config not found at {CONFIG_PATH}. Using empty defaults.")
        return {}
        
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _cached_permissions = json.load(f)
            logger.info("Permissions config loaded successfully.")
            return _cached_permissions
    except Exception as e:
        logger.error(f"Failed to read permissions configuration: {e}")
        return {}

def reload_permissions() -> None:
    """Flushes cache and reloads configuration."""
    global _cached_permissions
    _cached_permissions = None
    load_permissions()

def is_path_in_dirs(target_path: str, dir_list: List[str]) -> bool:
    """
    Checks if target_path is inside any directory in dir_list.
    Normalizes paths for Windows case-insensitivity.
    """
    if not target_path:
        return False
    try:
        target_norm = os.path.normpath(os.path.abspath(target_path)).lower()
        for d in dir_list:
            d_norm = os.path.normpath(os.path.abspath(d)).lower()
            # Check if it starts with the directory path and is followed by a separator or is exact match
            if target_norm == d_norm or target_norm.startswith(d_norm + os.sep):
                return True
    except Exception as e:
        logger.error(f"Error validating path: {e}")
    return False

def check_file_read_permission(filepath: str) -> bool:
    """Verifies if a file path is permitted to be read."""
    config = load_permissions()
    file_perm = config.get("file_permissions", {})
    
    # 1. Check blocked dirs first
    blocked_dirs = file_perm.get("blocked_dirs", [])
    if is_path_in_dirs(filepath, blocked_dirs):
        logger.warning(f"Read blocked: path '{filepath}' is in blocked directories.")
        return False
        
    # 2. Check allowed read dirs
    allowed_read = file_perm.get("allowed_read_dirs", [])
    if is_path_in_dirs(filepath, allowed_read):
        return True
        
    logger.warning(f"Read denied: path '{filepath}' is not inside allowed read directories.")
    return False

def check_file_write_permission(filepath: str) -> bool:
    """Verifies if a file path is permitted to be written to or created."""
    config = load_permissions()
    file_perm = config.get("file_permissions", {})
    
    # 1. Check blocked dirs first
    blocked_dirs = file_perm.get("blocked_dirs", [])
    if is_path_in_dirs(filepath, blocked_dirs):
        logger.warning(f"Write blocked: path '{filepath}' is in blocked directories.")
        return False
        
    # 2. Check extension
    allowed_extensions = file_perm.get("allowed_extensions", [])
    _, ext = os.path.splitext(filepath)
    if allowed_extensions and ext.lower() not in allowed_extensions:
        logger.warning(f"Write blocked: extension '{ext}' is not allowed.")
        return False
        
    # 3. Check allowed write dirs
    allowed_write = file_perm.get("allowed_write_dirs", [])
    if is_path_in_dirs(filepath, allowed_write):
        return True
        
    logger.warning(f"Write denied: path '{filepath}' is not inside allowed write directories.")
    return False

def get_app_launch_policy(app_name: str) -> str:
    """
    Returns the launch policy for a specific app.
    Options: 'allow', 'confirm', 'block'
    """
    config = load_permissions()
    app_perms = config.get("app_permissions", {})
    
    app_name_lower = app_name.lower().strip()
    # Check if app has direct policy
    if app_name_lower in app_perms:
        return app_perms[app_name_lower].get("launch", "confirm")
        
    # Fallback default
    return "confirm"

def check_cli_command_permission(app_name: str, command: str) -> bool:
    """Checks if a CLI command is in the allowlist for the app."""
    config = load_permissions()
    app_perms = config.get("app_permissions", {})
    
    app_name_lower = app_name.lower().strip()
    if app_name_lower in app_perms:
        allowed_cmds = app_perms[app_name_lower].get("allowed_commands", [])
        # Check if the command starts with any allowed command prefix
        for cmd in allowed_cmds:
            if command.strip().lower().startswith(cmd.lower()):
                return True
    return False

def get_contact_send_policy(email: str) -> str:
    """
    Returns the message/email send policy for a contact.
    Options: 'draft_only', 'confirm_before_send', 'auto_send_allowed', 'blocked'
    """
    config = load_permissions()
    contact_perms = config.get("contact_permissions", {})
    
    email_lower = email.lower().strip()
    if email_lower in contact_perms:
        return contact_perms[email_lower].get("policy", "confirm_before_send")
        
    # Check default policy
    default_policy = contact_perms.get("default", {}).get("policy", "confirm_before_send")
    return default_policy

def get_safety_settings() -> Dict[str, Any]:
    """Returns general safety settings."""
    config = load_permissions()
    return config.get("safety_settings", {})
