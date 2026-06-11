import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("integrations.contacts")

INTEGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(INTEGRATIONS_DIR)))
CONTACTS_PATH = os.path.join(WORKSPACE_DIR, "config", "contacts.json")

def load_all_contacts() -> List[Dict[str, Any]]:
    """Loads all contacts from contacts.json."""
    if not os.path.exists(CONTACTS_PATH):
        logger.warning(f"Contacts file not found at {CONTACTS_PATH}. Returning empty list.")
        return []
    try:
        with open(CONTACTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading contacts: {e}")
        return []

def find_contact_by_query(query: str) -> Optional[Dict[str, Any]]:
    """
    Searches for a contact by name, email, or phone (fuzzy match).
    """
    contacts = load_all_contacts()
    q = query.lower().strip()
    
    for c in contacts:
        name = c.get("name", "").lower()
        email = c.get("email", "").lower()
        phone = c.get("phone", "").lower()
        role = c.get("role", "").lower()
        
        if q in name or name in q or q in email or q in phone or q in role:
            return c
            
    return None
