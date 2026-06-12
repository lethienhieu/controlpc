import os
import sys
import shutil

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from policy.action_policy import ActionPolicy
from core import os_control

def test_dangerous_labels_policy():
    print("[TEST] Testing dangerous labels click policy...")
    policy = ActionPolicy()
    
    # 1. Normal UIA click: should be medium risk (falls back to requires_confirmation / confirm_once)
    res_normal = policy.evaluate_action("click_uia", {"name": "Cancel"})
    assert res_normal["risk_level"] == "medium"
    assert res_normal["confirmation_mode"] == "confirm_once"
    print(" - Normal UIA click: OK")
    
    # 2. UIA click on "Delete": should be escalated to high risk and requires_confirmation / confirm_final
    res_delete = policy.evaluate_action("click_uia", {"name": "Delete File"})
    assert res_delete["risk_level"] == "high"
    assert res_delete["confirmation_mode"] == "confirm_final"
    print(" - UIA click on 'Delete' label: OK")
    
    # 3. UIA click on "Send"
    res_send = policy.evaluate_action("click_uia", {"name": "Send Email"})
    assert res_send["risk_level"] == "high"
    assert res_send["confirmation_mode"] == "confirm_final"
    print(" - UIA click on 'Send' label: OK")
    
    # 4. UIA click on a "Pay" button (Vietnamese label "Thanh toán")
    res_pay = policy.evaluate_action("click_uia", {"auto_id": "btn_thanh_toan"})
    assert res_pay["risk_level"] == "high"
    assert res_pay["confirmation_mode"] == "confirm_final"
    print(" - UIA click on 'Pay' AutoId: OK")
    
    # 5. UIA click on "Submit"
    res_submit = policy.evaluate_action("click_uia", {"name": "Submit Form"})
    assert res_submit["risk_level"] == "high"
    assert res_submit["confirmation_mode"] == "confirm_final"
    print(" - UIA click on 'Submit' label: OK")

def test_screenshot_click_marker():
    print("[TEST] Testing screenshot with click marker...")
    # Capture screen with a simulated click marker
    marker_coords = (500, 400)
    res = os_control.capture_screenshot(draw_cursor=True, click_marker=marker_coords)
    assert res["success"] is True
    assert os.path.exists(res["filepath"])
    print(f" - Screenshot saved with click marker to: {res['filepath']}")

if __name__ == "__main__":
    try:
        test_dangerous_labels_policy()
        test_screenshot_click_marker()
        print("\n[SUCCESS] Vision Click Fallback policy and marker tests passed successfully!")
    except AssertionError as e:
        import traceback
        print(f"\n[FAILURE] Test assertion failed:")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Error occurred:")
        traceback.print_exc()
        sys.exit(1)
