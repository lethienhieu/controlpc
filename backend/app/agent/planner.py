import os
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError
from typing import Literal
import json

from agent.llm import LocalLLM
from agent.prompts import CLASSIFICATION_PROMPT, REACT_PLANNER_PROMPT
from database import memory
from core import uia_control, os_control

logger = logging.getLogger("planner")

class ActionDecision(BaseModel):
    reasoning: str = Field(..., description="Lý do chọn hành động này, ưu tiên giải pháp CLI/phím tắt/UIA")
    action: Literal["open", "hotkey", "press", "click_uia", "click", "type", "learn", "finish"]
    params: Dict[str, Any] = Field(default_factory=dict)

class IntentClassifier:
    def __init__(self, llm: LocalLLM):
        self.llm = llm

    def classify(self, message: str, ai_mode: str = "mock") -> bool:
        """
        Classifies user query.
        Returns True if 'os_control', False if 'chat'.
        """
        if ai_mode == "mock":
            msg_lower = message.lower()
            keywords = ["mở", "click", "gõ", "dạy", "chạy", "phím tắt", "hotkey", "bấm", "nhập", "tìm", "gửi email", "gửi tin nhắn", "soạn nháp"]
            return any(kw in msg_lower for kw in keywords)
            
        try:
            prompt = CLASSIFICATION_PROMPT.format(message=message)
            ans = self.llm.generate(
                prompt=f"<start_of_turn>user\n{prompt}\n<end_of_turn>\n<start_of_turn>model\n",
                max_tokens=8,
                temperature=0.0
            ).strip().lower()
            return "os_control" in ans
        except Exception as e:
            logger.error(f"Real LLM classification failed: {e}")
            raise e

class ReActPlanner:
    def __init__(self, llm: LocalLLM):
        self.llm = llm

    def plan(self, goal: str, step: int, max_steps: int, history_logs: List[Dict[str, Any]], ai_mode: str = "mock") -> Dict[str, Any]:
        """
        Generates the next step using LLM or mock decision.
        Returns the structured JSON decision.
        """
        if ai_mode == "mock":
            return self._get_mock_decision(goal, step, history_logs)
            
        # Real ReAct planning with Gemma-4
        try:
            # 1. Gather active windows
            active_windows = uia_control.get_active_windows()
            
            # 2. Gather control tree for the focused window if any
            focused_controls = []
            if active_windows:
                first_title = active_windows[0].get("title", "")
                if first_title:
                    focused_controls = uia_control.get_control_tree(first_title)[:10]
            
            # 3. Gather recent files from permitted directories
            from policy.permissions import load_permissions
            config = load_permissions()
            allowed_read = config.get("file_permissions", {}).get("allowed_read_dirs", [])
            recent_files = []
            for d in allowed_read[:2]:  # Max 2 dirs to keep observation small
                if os.path.exists(d):
                    try:
                        files = [os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
                        recent_files.extend(files[:3])
                    except:
                        pass
                        
            # Trim history: only last 3 action logs, truncate long messages
            action_history = []
            for l in history_logs[-5:]:
                if l['type'] in ('action', 'system', 'reasoning'):
                    msg = l['message'][:120]  # Cap at 120 chars to reduce tokens
                    action_history.append(msg)
            action_history = action_history[-3:]  # Only last 3
            
            obs_dict = {
                "active_windows": [{"title": w["title"][:60]} for w in active_windows[:3]],
                "focused_controls": focused_controls[:5],
                "recent_files": recent_files[:3],
                "action_history": action_history
            }
            
            prompt = REACT_PLANNER_PROMPT.format(
                goal=goal,
                step=step,
                max_steps=max_steps,
                history=json.dumps(obs_dict)
            )
            
            content = self.llm.generate(
                prompt=f"<start_of_turn>user\n{prompt}\n<end_of_turn>\n<start_of_turn>model\n",
                max_tokens=256,
                temperature=0.1
            ).strip()
            
            # Clean markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```json") or lines[0].startswith("```"):
                    content = "\n".join(lines[1:-1]).strip()
            
            # Parse & validate using Pydantic
            parsed_data = json.loads(content)
            validated = ActionDecision(**parsed_data)
            return validated.model_dump()
            
        except Exception as e:
            logger.error(f"Real GGUF planning failed: {e}")
            raise e

    def _get_mock_decision(self, goal: str, step: int, history_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        goal_lower = goal.lower()
        import re
        
        if "hãy" in goal_lower or "chạy file" in goal_lower or "đường dẫn" in goal_lower:
            app = "revit 2024"
            path = "C:\\Program Files\\Autodesk\\Revit 2024\\Revit.exe"
            
            path_match = re.search(r'[a-zA-Z]:\\[^"]+', goal)
            if path_match:
                path = path_match.group(0).strip()
                
            app_match = re.search(r'(?:mở|app|chạy)\s+([a-zA-Z0-9\s\-]+?)\s+(?:hãy|chạy|đường dẫn)', goal)
            if app_match:
                app = app_match.group(1).strip().lower()
                
            return {
                "reasoning": f"Nhận diện lệnh dạy của người dùng: '{app}' ứng với đường dẫn '{path}'. Tôi lưu dữ liệu vào cơ sở tri thức cục bộ.",
                "action": "learn",
                "params": {
                    "key": app,
                    "value": path,
                    "type": "apps"
                }
            }
            
        if "mở" in goal_lower:
            app = "notepad"
            match = re.search(r'mở\s+([a-zA-Z0-9\s\-]+)', goal_lower)
            if match:
                app = match.group(1).strip()
                
            if step == 1:
                return {
                    "reasoning": f"Truy vấn thông tin tệp tin/đường dẫn của '{app}' để mở trực tiếp.",
                    "action": "open",
                    "params": {"app_name": app}
                }
            else:
                return {
                    "reasoning": f"Đã thực hiện mở thành công '{app}'. Kết thúc.",
                    "action": "finish",
                    "params": {"message": f"Mở phần mềm '{app}' thành công!"}
                }

        mock_steps_database = {
            "revit 2024": [
                {
                    "reasoning": "Người dùng yêu cầu mở Revit 2024. Tôi sẽ tra cứu cơ sở tri thức cục bộ và khởi chạy bằng đường dẫn.",
                    "action": "open",
                    "params": {"app_name": "revit 2024"}
                },
                {
                    "reasoning": "Revit 2024 đã được khởi động thành công. Tôi kết thúc tác vụ.",
                    "action": "finish",
                    "params": {"message": "Đã tìm thấy và khởi chạy Revit 2024 thành công!"}
                }
            ],
            "chrome": [
                {
                    "reasoning": "Mở trình duyệt Google Chrome thông qua lệnh hệ thống.",
                    "action": "open",
                    "params": {"app_name": "chrome"}
                },
                {
                    "reasoning": "Chrome đã được mở. Tôi kết thúc tác vụ.",
                    "action": "finish",
                    "params": {"message": "Đã mở Google Chrome."}
                }
            ]
        }
        
        selected_key = "chrome"
        for k in mock_steps_database.keys():
            if k in goal_lower:
                selected_key = k
                break
                
        steps = mock_steps_database[selected_key]
        step_idx = step - 1
        if step_idx < len(steps):
            return steps[step_idx]
            
        return {
            "reasoning": "Mục tiêu đã hoàn thành.",
            "action": "finish",
            "params": {"message": "Tác vụ hoàn tất."}
        }
