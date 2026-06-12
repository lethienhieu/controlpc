import os
import json
import logging
import re
from typing import List, Dict, Any, Optional

from policy import permissions
from integrations import smtp_imap
from core import paths

logger = logging.getLogger("tools.email_tool")

# Contacts = active brain config; draft = transient brain run dir.
CONTACTS_PATH = paths.config_file("contacts.json")
DRAFT_PATH = os.path.join(paths.run_dir(), "email_draft.json")

def validate_recipient(email: str) -> Dict[str, Any]:
    """
    Validates email format and checks if recipient is in contacts allowlist.
    """
    email_clean = email.strip().lower()
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    
    if not re.match(email_regex, email_clean):
        return {"success": False, "error": f"Invalid email format: '{email}'"}
        
    # Check contacts list
    contacts = []
    if os.path.exists(CONTACTS_PATH):
        try:
            with open(CONTACTS_PATH, "r", encoding="utf-8") as f:
                contacts = json.load(f)
        except Exception as e:
            logger.error(f"Error loading contacts: {e}")
            
    contact_info = None
    for c in contacts:
        if c.get("email", "").lower().strip() == email_clean:
            contact_info = c
            break
            
    return {
        "success": True,
        "email": email_clean,
        "is_known_contact": contact_info is not None,
        "contact_info": contact_info
    }

def create_draft(to_email: str, subject: str, body: str, attachments: List[str] = None) -> Dict[str, Any]:
    """
    Creates a temporary draft email saved on disk at workspace/temp/current_draft.json.
    Allows the frontend to preview and edit the email draft.
    """
    # 1. Validate recipient
    val_res = validate_recipient(to_email)
    if not val_res["success"]:
        return val_res
        
    to_email = val_res["email"]
    
    # 2. Check attachments permissions
    safe_attachments = []
    if attachments:
        for path in attachments:
            if not permissions.check_file_read_permission(path):
                return {"success": False, "error": f"Read permission denied for attachment: {path}"}
            if os.path.exists(path):
                safe_attachments.append(os.path.normpath(os.path.abspath(path)))
                
    draft = {
        "to": to_email,
        "subject": subject,
        "body": body,
        "attachments": safe_attachments
    }
    
    # Write draft to temp directory for frontend preview/edit
    try:
        os.makedirs(os.path.dirname(DRAFT_PATH), exist_ok=True)
        with open(DRAFT_PATH, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Email draft created and saved to {DRAFT_PATH}")
        return {
            "success": True,
            "message": f"Successfully created an email draft addressed to: {to_email}",
            "draft": draft
        }
    except Exception as e:
        logger.error(f"Failed to save draft: {e}")
        return {"success": False, "error": str(e)}

def attach_file_to_draft(filepath: str) -> Dict[str, Any]:
    """
    Appends a new file attachment to the active draft.
    """
    if not os.path.exists(DRAFT_PATH):
        return {"success": False, "error": "No active email draft found. Create a draft first."}
        
    if not permissions.check_file_read_permission(filepath):
        return {"success": False, "error": f"Read permission denied for path: {filepath}"}
        
    if not os.path.exists(filepath):
        return {"success": False, "error": f"File not found: {filepath}"}
        
    try:
        with open(DRAFT_PATH, "r", encoding="utf-8") as f:
            draft = json.load(f)
            
        filepath_norm = os.path.normpath(os.path.abspath(filepath))
        if filepath_norm not in draft.get("attachments", []):
            if "attachments" not in draft:
                draft["attachments"] = []
            draft["attachments"].append(filepath_norm)
            
            with open(DRAFT_PATH, "w", encoding="utf-8") as f:
                json.dump(draft, f, ensure_ascii=False, indent=2)
                
        return {"success": True, "message": f"Attached file: {os.path.basename(filepath_norm)}", "draft": draft}
    except Exception as e:
        logger.error(f"Failed to attach file to draft: {e}")
        return {"success": False, "error": str(e)}

def send_email(to_email: str, subject: str, body: str, attachments: List[str] = None) -> Dict[str, Any]:
    """
    Sends the email (either mock or live) based on config settings.
    """
    # Recipients verification
    val_res = validate_recipient(to_email)
    if not val_res["success"]:
        return val_res
        
    # Attachments verification
    if attachments:
        for path in attachments:
            if not permissions.check_file_read_permission(path):
                return {"success": False, "error": f"Read permission denied for attachment: {path}"}
                
    # Send through integration
    res = smtp_imap.send_email_smtp(to_email, subject, body, attachments)
    
    # If successful, delete the current draft file
    if res.get("success") and os.path.exists(DRAFT_PATH):
        try:
            os.remove(DRAFT_PATH)
        except:
            pass
            
    return res

def list_recent() -> Dict[str, Any]:
    """
    Lists recent emails sent by the system (retrieved from database history).
    """
    try:
        from database import memory
        audit_logs = memory.get_audit_logs()
        emails = []
        for log in audit_logs:
            if log.get("tool") == "email.send" and log.get("executed_status") == "completed":
                emails.append({
                    "timestamp": log["timestamp"],
                    "to": log["target"].get("recipient", ""),
                    "subject": log["params"].get("subject", ""),
                    "body": log["params"].get("body", "")
                })
        return {"success": True, "emails": emails[:5]}
    except Exception as e:
        return {"success": False, "error": str(e)}
