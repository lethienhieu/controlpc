import os
import sys

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from policy.risk import classify_action_risk
from policy.permissions import load_permissions, check_file_read_permission, check_file_write_permission
from policy.action_policy import ActionPolicy

def test_risk_classification():
    print("[TEST] Running risk classification tests...")
    
    assert classify_action_risk("system.delete_system_dir", {}) == "blocked"
    assert classify_action_risk("email.send", {"recipient": "test@example.com"}) == "high"
    assert classify_action_risk("click", {"x": 100, "y": 200}) == "high"
    assert classify_action_risk("click_uia", {"name": "Button"}) == "medium"
    assert classify_action_risk("file.search", {"path": "C:\\Users\\admin\\Documents"}) == "low"
    assert classify_action_risk("open", {"app_name": "notepad"}) == "low"
    assert classify_action_risk("open", {"app_name": "cmd"}) == "medium"
    
    print("[TEST] Risk classification tests passed!")

def test_file_permissions():
    print("[TEST] Running file permission tests...")
    
    # Blocked directory checks
    assert not check_file_read_permission("C:\\Windows\\System32\\cmd.exe")
    assert not check_file_write_permission("C:\\Windows\\System32\\config.db")
    
    # Allowed read checks
    assert check_file_read_permission("C:\\Users\\admin\\Documents\\report.docx")
    assert check_file_read_permission("C:\\1 CODE\\CONTROLPC\\workspace\\output\\test.txt")
    
    # Allowed write checks
    assert check_file_write_permission("C:\\Users\\admin\\Documents\\output.docx")
    assert not check_file_write_permission("C:\\Users\\admin\\Documents\\output.exe")  # blocked extension .exe
    
    print("[TEST] File permission tests passed!")

def test_action_policy_evaluation():
    print("[TEST] Running ActionPolicy evaluation tests...")
    policy = ActionPolicy()
    
    # 1. Blocked Action
    res_blocked = policy.evaluate_action("system.delete_system_dir", {})
    assert res_blocked["decision"] == "blocked"
    assert res_blocked["risk_level"] == "blocked"
    print(" - Blocked action assertion: OK")
    
    # 2. Blocked write to System Directory
    res_sys_write = policy.evaluate_action("file.copy", {"path": "C:\\Windows\\test.txt"})
    assert res_sys_write["decision"] == "blocked"
    print(" - Blocked system path write assertion: OK")
    
    # 3. High Risk / Confirmation (Email Send)
    res_email = policy.evaluate_action("email.send", {"recipient": "nam@example.com"})
    assert res_email["decision"] == "requires_confirmation"
    assert res_email["confirmation_mode"] == "confirm_final"
    print(" - Email send confirmation assertion: OK")
    
    # 4. Blocked Coordinate Click (if coordinate_click_enabled is false)
    res_click = policy.evaluate_action("click", {"x": 500, "y": 600})
    assert res_click["decision"] == "blocked"  # coordinate_click_enabled is false in permissions.json
    print(" - Coordinate click block assertion: OK")
    
    # 5. Low Risk / Allowed Read-Only Action
    # Let's check with file.search under allowed dir
    res_search = policy.evaluate_action("file.search", {"path": "C:\\Users\\admin\\Documents"})
    # Since search is low risk, if no global override is forced it would be allowed,
    # but wait: in ActionPolicy:
    # "If decision is allowed and tool is not finish/learn, safety override upgrades it to requires_confirmation (confirm_once)"
    # Let's verify:
    assert res_search["decision"] == "requires_confirmation"
    assert res_search["confirmation_mode"] == "confirm_once"
    print(" - File search low-risk confirmation assertion: OK")
    
    print("[TEST] ActionPolicy evaluation tests passed!")

if __name__ == "__main__":
    try:
        test_risk_classification()
        test_file_permissions()
        test_action_policy_evaluation()
        print("\n[SUCCESS] All policy tests passed successfully!")
    except AssertionError as e:
        print(f"\n[FAILURE] Policy test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error during testing: {e}")
        sys.exit(1)
