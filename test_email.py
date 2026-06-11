import os
import sys

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from tools import email_tool
from policy.action_policy import ActionPolicy

def test_recipient_validation():
    print("[TEST] Testing recipient validation...")
    
    # Valid & known contact
    res_nam = email_tool.validate_recipient("nam@example.com")
    assert res_nam["success"]
    assert res_nam["is_known_contact"]
    assert res_nam["contact_info"]["name"] == "Nam GĐ"
    
    # Valid & unknown contact
    res_unk = email_tool.validate_recipient("stranger@example.com")
    assert res_unk["success"]
    assert not res_unk["is_known_contact"]
    
    # Invalid email syntax
    res_inv = email_tool.validate_recipient("invalid-email-string")
    assert not res_inv["success"]
    assert "Định dạng email không hợp lệ" in res_inv["error"]
    
    print(" - Recipient validation passed!")

def test_draft_creation_and_removal():
    print("[TEST] Testing draft creation and file persistence...")
    draft_path = "workspace/temp/current_draft.json"
    
    # Cleanup old draft if any
    if os.path.exists(draft_path):
        os.remove(draft_path)
        
    to = "nam@example.com"
    subject = "Báo cáo tiến độ CONTROLPC"
    body = "Xin chào anh Nam,\nTôi đã hoàn thành xong Phase 3 của CONTROLPC."
    
    res = email_tool.create_draft(to, subject, body)
    assert res["success"]
    assert os.path.exists(draft_path), "Draft JSON file should exist"
    
    # Read and verify content
    with open(draft_path, "r", encoding="utf-8") as f:
        import json
        data = json.load(f)
        assert data["to"] == to
        assert data["subject"] == subject
        assert data["body"] == body
        
    print(" - Email draft creation passed!")

def test_email_sending_mock():
    print("[TEST] Testing email sending with mock SMTP EML generation...")
    to = "nam@example.com"
    subject = "Báo cáo gửi thử"
    body = "Đã tích hợp SMTP mock."
    
    # Clean output eml first
    eml_path = "workspace/output/draft_email_nam_at_example.com.eml"
    if os.path.exists(eml_path):
        os.remove(eml_path)
        
    res = email_tool.send_email(to, subject, body)
    assert res["success"]
    assert res["mode"] == "mock"
    assert os.path.exists(eml_path), "EML draft should be saved on mock sending"
    
    # Verify the draft JSON file was removed after successful send
    draft_path = "workspace/temp/current_draft.json"
    assert not os.path.exists(draft_path), "Draft file should be cleaned up after successful send"
    
    print(" - Email send mock passed!")

def test_policy_enforcement():
    print("[TEST] Testing ActionPolicy rules for email sending...")
    policy = ActionPolicy()
    
    # Gửi email đến Nam GĐ: Nam GĐ có policy là 'confirm_before_send' -> requires_confirmation
    res = policy.evaluate_action("email.send", {
        "recipient": "nam@example.com",
        "subject": "Báo cáo",
        "body": "Nội dung"
    })
    assert res["decision"] == "requires_confirmation"
    assert res["confirmation_mode"] == "confirm_final"
    assert "email" in res["target"].values() or "nam@example.com" in res["target"].values()
    
    # Gửi email đến Hằng HR: Hằng HR có policy là 'draft_only' -> blocked/prevented
    res_hang = policy.evaluate_action("email.send", {
        "recipient": "hang@example.com",
        "subject": "Báo cáo",
        "body": "Nội dung"
    })
    assert res_hang["decision"] == "blocked"
    assert "Chỉ cho phép soạn nháp" in res_hang["preview"]["title"]
    
    print(" - ActionPolicy checks for email passed!")

if __name__ == "__main__":
    try:
        test_recipient_validation()
        test_draft_creation_and_removal()
        test_email_sending_mock()
        test_policy_enforcement()
        print("\n[SUCCESS] All email workflow tests passed successfully!")
    except AssertionError as e:
        print(f"\n[FAILURE] Email test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error during testing: {e}")
        sys.exit(1)
