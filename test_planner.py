import os
import sys
from pydantic import ValidationError

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from agent.planner import IntentClassifier, ReActPlanner, ActionDecision
from agent.llm import LocalLLM

def test_intent_classifier():
    print("[TEST] Testing IntentClassifier in mock mode...")
    llm = LocalLLM()
    classifier = IntentClassifier(llm)
    
    # 1. Test control keywords
    assert classifier.classify("Mở phần mềm Revit", ai_mode="mock") is True
    assert classifier.classify("Click nút submit", ai_mode="mock") is True
    assert classifier.classify("Chào bạn!", ai_mode="mock") is False
    assert classifier.classify("Thời tiết hôm nay thế nào?", ai_mode="mock") is False
    print(" - IntentClassifier mock mode passed!")

def test_react_planner_mock():
    print("[TEST] Testing ReActPlanner in mock mode...")
    llm = LocalLLM()
    planner = ReActPlanner(llm)
    
    # 1. Test app open goal
    dec1 = planner.plan("mở notepad", step=1, max_steps=12, history_logs=[], ai_mode="mock")
    assert dec1["action"] == "open"
    assert dec1["params"]["app_name"] == "notepad"
    
    # 2. Test teaching goal
    dec2 = planner.plan("chạy revit hãy cấu hình C:\\Program Files\\Revit.exe", step=1, max_steps=12, history_logs=[], ai_mode="mock")
    assert dec2["action"] == "learn"
    assert dec2["params"]["key"] == "revit"
    assert dec2["params"]["value"] == "C:\\Program Files\\Revit.exe"
    print(" - ReActPlanner mock mode passed!")

def test_pydantic_validation():
    print("[TEST] Testing ActionDecision Pydantic schema validation...")
    
    # 1. Valid data
    valid_data = {
        "reasoning": "Mở ứng dụng Notepad qua CLI",
        "action": "open",
        "params": {"app_name": "notepad"}
    }
    decision = ActionDecision(**valid_data)
    assert decision.action == "open"
    assert decision.params["app_name"] == "notepad"
    
    # 2. Invalid Action should raise ValidationError
    invalid_data = {
        "reasoning": "Mở ứng dụng Notepad",
        "action": "invalid_action_name",
        "params": {}
    }
    try:
        ActionDecision(**invalid_data)
        assert False, "Should raise ValidationError for invalid action"
    except ValidationError:
        print(" - Validation correctly rejected invalid action: OK")
        
    print(" - Pydantic validation tests passed!")

if __name__ == "__main__":
    try:
        test_intent_classifier()
        test_react_planner_mock()
        test_pydantic_validation()
        print("\n[SUCCESS] Agent Planner tests passed successfully!")
    except AssertionError as e:
        import traceback
        print(f"\n[FAILURE] Planner test assertion failed:")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Error occurred:")
        traceback.print_exc()
        sys.exit(1)
