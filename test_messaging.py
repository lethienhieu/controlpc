import os
import sys
import json

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from tools import messaging_tool
from policy.action_policy import ActionPolicy

def test_contact_lookup():
    print("[TEST] Testing contact lookup...")
    
    # Fuzzy match by name
    res = messaging_tool.find_contact("Nam")
    assert res["success"]
    assert res["contact"]["name"] == "Sample Director"
    
    # Fuzzy match by role
    res = messaging_tool.find_contact("HR")
    assert res["success"]
    assert res["contact"]["name"] == "Sample HR"
    
    # Non-existent contact
    res = messaging_tool.find_contact("Unknown Person")
    assert not res["success"]
    assert "No contact found" in res["error"]
    
    print(" - Contact lookup passed!")

def test_message_draft_creation():
    print("[TEST] Testing message draft creation and persistence...")
    draft_path = messaging_tool.DRAFT_PATH
    
    # Clean up old draft
    if os.path.exists(draft_path):
        os.remove(draft_path)
        
    contact_query = "Nam"
    text = "Hi Nam, I'm sending you a progress report message."
    
    res = messaging_tool.create_draft(contact_query, text)
    assert res["success"]
    assert os.path.exists(draft_path), "Message draft JSON file should exist"
    
    # Verify file content
    with open(draft_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["contact_name"] == "Sample Director"
        assert data["email"] == "nam@example.com"
        assert data["phone"] == "0912345678"
        assert data["text"] == text
        
    print(" - Message draft creation passed!")

def test_gating_and_sending():
    print("[TEST] Testing send messaging with policy gates...")
    draft_path = messaging_tool.DRAFT_PATH
    
    # Clean up old drafts
    if os.path.exists(draft_path):
        os.remove(draft_path)
        
    # 1. Test sending to Hang HR (draft_only)
    # This should fail the direct send, and automatically create a draft instead
    res_hang = messaging_tool.send_message("HR", "Message content for HR")
    assert not res_hang["success"]
    assert "DRAFT_ONLY" in res_hang["error"]
    assert os.path.exists(draft_path), "Draft should have been created for DRAFT_ONLY contact"
    
    # Verify draft contents
    with open(draft_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["contact_name"] == "Sample HR"
        assert data["text"] == "Message content for HR"
        
    # Clean up again
    os.remove(draft_path)
    
    # 2. Test sending to Nam GD (confirm_before_send)
    # The tool level allows send_message (simulates post-approval run)
    msg_path = os.path.join(BASE_DIR, "workspace", "output", "sent_message_Sample_Director.txt")
    if os.path.exists(msg_path):
        os.remove(msg_path)
        
    res_nam = messaging_tool.send_message("Nam", "Message content for Nam")
    assert res_nam["success"]
    assert os.path.exists(msg_path), "Mock sent message text file should exist"
    assert not os.path.exists(draft_path), "Draft path should be cleaned up after successful send"
    
    with open(msg_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Recipient: Sample Director" in content
        assert "Content:\nMessage content for Nam" in content
        
    print(" - Messaging gating and sending passed!")

def test_policy_enforcement():
    print("[TEST] Testing ActionPolicy evaluation for messages...")
    policy = ActionPolicy()
    
    # Evaluating message.send for Nam GD (policy: confirm_before_send)
    res_nam = policy.evaluate_action("message.send", {
        "recipient": "nam@example.com",
        "text": "Hello"
    })
    assert res_nam["decision"] == "requires_confirmation"
    assert res_nam["confirmation_mode"] == "confirm_final"
    
    # Evaluating message.send for Hang HR (policy: draft_only)
    res_hang = policy.evaluate_action("message.send", {
        "recipient": "hang@example.com",
        "text": "Hello"
    })
    assert res_hang["decision"] == "blocked"
    assert "drafts only allowed" in res_hang["preview"]["title"]
    
    print(" - ActionPolicy evaluation passed!")

if __name__ == "__main__":
    try:
        test_contact_lookup()
        test_message_draft_creation()
        test_gating_and_sending()
        test_policy_enforcement()
        print("\n[SUCCESS] All messaging workflow tests passed successfully!")
    except AssertionError as e:
        print(f"\n[FAILURE] Messaging test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error during testing: {e}")
        sys.exit(1)
