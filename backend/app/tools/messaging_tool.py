import os
import json
import logging
from typing import Dict, Any, Optional

from integrations import contacts
from policy import permissions
from core import paths

logger = logging.getLogger("tools.messaging_tool")

# WORKSPACE_DIR (repo root) still used for user-visible output; draft is transient.
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(TOOLS_DIR)))
DRAFT_PATH = os.path.join(paths.run_dir(), "message_draft.json")

def find_contact(query: str) -> Dict[str, Any]:
    """
    Finds a contact based on a search query.
    """
    c = contacts.find_contact_by_query(query)
    if c:
        return {"success": True, "contact": c, "message": f"Found contact: {c['name']} ({c['email']})"}
    return {"success": False, "error": f"No contact found matching the keyword: '{query}'"}

def create_draft(contact_query: str, text: str) -> Dict[str, Any]:
    """
    Creates a draft message. Saves it to workspace/temp/current_message_draft.json.
    """
    c_res = find_contact(contact_query)
    if not c_res["success"]:
        return c_res
        
    c = c_res["contact"]
    draft = {
        "contact_name": c["name"],
        "email": c.get("email", ""),
        "phone": c.get("phone", ""),
        "text": text
    }
    
    try:
        os.makedirs(os.path.dirname(DRAFT_PATH), exist_ok=True)
        with open(DRAFT_PATH, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Message draft created for {c['name']}")
        return {
            "success": True,
            "message": f"Drafted a message for: {c['name']}",
            "draft": draft
        }
    except Exception as e:
        logger.error(f"Failed to save message draft: {e}")
        return {"success": False, "error": str(e)}

def send_message(contact_query: str, text: str) -> Dict[str, Any]:
    """
    Sends a message (mock or live) based on contact permissions.
    """
    c_res = find_contact(contact_query)
    if not c_res["success"]:
        return c_res
        
    c = c_res["contact"]
    email = c.get("email", "default")
    
    # Check permission policy
    policy = permissions.get_contact_send_policy(email)
    
    if policy == "blocked":
        return {"success": False, "error": f"Sending messages is blocked for contact: {c['name']}"}

    if policy == "draft_only":
        # Force downgrade to draft creation
        create_draft(contact_query, text)
        return {
            "success": False,
            "error": f"Contact '{c['name']}' has a DRAFT_ONLY policy. The system has automatically switched to saving a draft."
        }
        
    # Send mock message
    try:
        msg_filename = f"sent_message_{c['name'].replace(' ', '_')}.txt"
        msg_path = os.path.join(WORKSPACE_DIR, "workspace", "output", msg_filename)
        
        output_text = (
            f"=== MESSAGE SENT ===\n"
            f"Recipient: {c['name']}\n"
            f"Phone number: {c.get('phone', '')}\n"
            f"Email: {c.get('email', '')}\n"
            f"Content:\n{text}\n"
        )
        
        with open(msg_path, "w", encoding="utf-8") as f:
            f.write(output_text)
            
        # Clean current draft file on successful send
        if os.path.exists(DRAFT_PATH):
            try:
                os.remove(DRAFT_PATH)
            except:
                pass
                
        logger.info(f"[MOCK MESSAGE] Sent message to {c['name']}")
        return {
            "success": True,
            "message": f"Message sent (mock) successfully to: {c['name']}",
            "path": msg_path
        }
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return {"success": False, "error": str(e)}

def open_thread(contact_query: str) -> Dict[str, Any]:
    """
    Simulates opening the chat thread in desktop application.
    """
    c_res = find_contact(contact_query)
    if not c_res["success"]:
        return c_res
        
    c = c_res["contact"]
    logger.info(f"Opening thread for {c['name']}")
    return {
        "success": True,
        "message": f"Opened the chat window with: {c['name']}"
    }
