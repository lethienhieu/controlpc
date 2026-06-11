import os
import sys
import json
import time
import requests
import threading
from contextlib import contextmanager

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from database import memory
from integrations import telegram
from policy import permissions

PERMISSIONS_PATH = os.path.join(BASE_DIR, "config", "permissions.json")

@contextmanager
def remote_gateway_setting(enabled: bool):
    """
    Temporarily toggles remote_gateway_enabled for integration tests and restores
    the previous config afterward. Remote gateway must stay off by default.
    """
    with open(PERMISSIONS_PATH, "r", encoding="utf-8") as f:
        original = json.load(f)

    modified = json.loads(json.dumps(original))
    modified.setdefault("safety_settings", {})["remote_gateway_enabled"] = enabled

    with open(PERMISSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(modified, f, ensure_ascii=False, indent=2)
    permissions.reload_permissions()

    try:
        yield
    finally:
        with open(PERMISSIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(original, f, ensure_ascii=False, indent=2)
        permissions.reload_permissions()

def test_remote_database_auth():
    print("[TEST] Testing remote sender database lookup & validation...")
    
    # 1. Check owner seeded sender
    owner = memory.get_remote_sender("telegram:123456789")
    assert owner is not None
    assert owner["name"] == "Owner"
    assert owner["enabled"] is True
    assert owner["auth_level"] == "admin"
    
    # 2. Check PIN verification
    assert memory.verify_remote_sender_pin("telegram:123456789", "1234") is True
    assert memory.verify_remote_sender_pin("telegram:123456789", "wrong") is False
    
    # 3. Add a temporary sender
    success = memory.add_remote_sender(
        sender_identity="telegram:987654321",
        name="Guest",
        enabled=False,
        auth_level="view_status",
        can_create_task=False,
        can_approve_high_risk=False,
        requires_pin_for_high_risk=True,
        pin="4321"
    )
    assert success is True
    
    guest = memory.get_remote_sender("telegram:987654321")
    assert guest is not None
    assert guest["enabled"] is False
    assert guest["can_create_task"] is False
    
    print(" - Remote DB auth passed!")

def test_telegram_process_commands():
    print("[TEST] Testing remote commands routing & safety confirmation...")
    
    # Reset agent status to idle
    import main
    agent = main.agent
    agent.status = "idle"
    agent.current_goal = ""
    agent.pending_action = None
    
    # 1. Remote gateway is disabled by default and must reject every sender
    res = telegram.process_remote_command("telegram", "999999999", "mở notepad")
    assert not res["success"]
    assert "Remote Gateway" in res["message"] or "điều khiển từ xa" in res["message"]

    with remote_gateway_setting(True):
        # 2. Request from unauthorized sender
        res = telegram.process_remote_command("telegram", "999999999", "mở notepad")
        assert not res["success"]
        assert "không được ủy quyền" in res["message"]
        
        # 3. Request from disabled sender
        res = telegram.process_remote_command("telegram", "987654321", "mở notepad")
        assert not res["success"]
        assert "bị vô hiệu hóa" in res["message"]
        
        # 4. Valid request from Owner should create a local task, not call tools directly.
        # With default safety confirmation, even allowlisted Notepad should pause for approval.
        res = telegram.process_remote_command("telegram", "123456789", "mở notepad")
        assert res["success"] is True
        assert agent.status in ["waiting_approval", "running", "finished"]
        agent.status = "idle"
        agent.pending_action = None
    
    print(" - Command processing and routing passed!")

def test_pin_gated_execution():
    print("[TEST] Testing high-risk PIN authorization flow...")
    
    # Clean old notification files
    noti_file = os.path.join(BASE_DIR, "workspace", "output", "telegram_notifications.txt")
    if os.path.exists(noti_file):
        os.remove(noti_file)
        
    import main
    agent = main.agent
    agent.status = "idle"
    
    with remote_gateway_setting(True):
        # Create a harmless pending action manually to test PIN approval without
        # opening Chrome/browser or any external app during the test.
        agent.status = "waiting_approval"
        agent.source_channel = "telegram"
        agent.sender_id = "123456789"
        agent.pending_action = {
            "action_id": "act_test_pin",
            "tool": "finish",
            "intent": "remote_pin_test",
            "risk_level": "high",
            "decision": "requires_confirmation",
            "confirmation_mode": "confirm_final",
            "target": {},
            "params": {"message": "Remote PIN approval test completed."},
            "reason": "Test PIN approval without launching external apps.",
            "preview": {
                "title": "Test remote approval",
                "summary": "Harmless finish action for PIN flow test."
            },
            "rollback_hint": "No external side effects."
        }
        
        # 1. Send incorrect PIN
        res_bad = telegram.process_remote_command("telegram", "123456789", "9999")
        assert not res_bad["success"]
        assert "PIN không đúng" in res_bad["message"]
        assert agent.status == "waiting_approval"
        
        # 2. Send correct PIN
        res_good = telegram.process_remote_command("telegram", "123456789", "1234")
        assert res_good["success"] is True
        assert "Phê duyệt thành công" in res_good["message"]
        
        # Wait for execution thread to run and task to finish
        time.sleep(1)
        assert agent.status in ["finished", "idle"]
        
    print(" - PIN gating flow passed!")

if __name__ == "__main__":
    import uvicorn
    
    # Start temporary FastAPI thread to test HTTP endpoint
    # Since main imports agent and runs the background thread, we can test integrations directly.
    # To test actual FastAPI routes, we can call main functions directly or use TestClient,
    # but since we verified processed commands directly via `telegram.process_remote_command` 
    # which is the heart of the endpoint, we can also query the FastAPI application.
    
    try:
        test_remote_database_auth()
        test_telegram_process_commands()
        test_pin_gated_execution()
        print("\n[SUCCESS] All remote gateway tests passed successfully!")
    except AssertionError as e:
        import traceback
        print(f"\n[FAILURE] Remote gateway test failed:")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Error during testing:")
        traceback.print_exc()
        sys.exit(1)
