import os
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError, field_validator
import json

from agent.llm import LocalLLM
from agent.prompts import CLASSIFICATION_PROMPT, REACT_PLANNER_PROMPT
from database import memory, journal
from core import uia_control, os_control
from tools.registry import TOOL_REGISTRY

logger = logging.getLogger("planner")

# Native OS-level actions handled directly by the executor.
OS_ACTIONS = {"open", "hotkey", "press", "click_uia", "click", "type", "learn", "finish"}
# Full set the planner may emit = OS actions plus every registered tool
# (file.*, document.*, email.*, message.*). Previously the schema was locked to
# the 8 OS actions, which made the entire tool registry unreachable.
ALLOWED_ACTIONS = OS_ACTIONS | set(TOOL_REGISTRY.keys())

# JSON schema passed to llama-server so the (small) model is grammar-constrained
# to emit a valid JSON object instead of prose/markdown. The `action` string is
# further validated against ALLOWED_ACTIONS by Pydantic below.
ACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "action": {"type": "string"},
        "params": {"type": "object"},
    },
    "required": ["reasoning", "action", "params"],
}

class ActionDecision(BaseModel):
    reasoning: str = Field(..., description="Reason for choosing this action, prioritizing CLI/hotkey/UIA solutions")
    action: str = Field(..., description="Name of the OS action or registered tool")
    params: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        if v not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Unknown action '{v}'. Must be one of OS actions {sorted(OS_ACTIONS)} "
                f"or a registered tool {sorted(TOOL_REGISTRY.keys())}."
            )
        return v

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
            ans = self.llm.generate(prompt=prompt, max_tokens=8, temperature=0.0).strip().lower()
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
                memory=journal.read_memory_digest(900) or "(none)",
                history=json.dumps(obs_dict)
            )
            
            # Bounded retry: a model can still produce an invalid `action` or odd
            # JSON even when grammar-constrained. Re-generate up to 3x (cooling
            # temperature) before giving up. No silent mock fallback.
            last_err = None
            for attempt in range(3):
                try:
                    content = self.llm.generate(
                        prompt=prompt,
                        max_tokens=160,  # action JSON is small; brief reasoning keeps latency low
                        temperature=0.1 if attempt == 0 else 0.0,
                        json_schema=ACTION_JSON_SCHEMA,
                    ).strip()

                    # Safety net: strip markdown fences if the model added them.
                    if content.startswith("```"):
                        lines = content.split("\n")
                        if lines[0].startswith("```"):
                            content = "\n".join(lines[1:-1]).strip()

                    parsed_data = json.loads(content)
                    validated = ActionDecision(**parsed_data)
                    return validated.model_dump()
                except Exception as e:
                    last_err = e
                    logger.warning(f"Planner attempt {attempt + 1}/3 failed: {e}")

            logger.error(f"Real GGUF planning failed after retries: {last_err}")
            raise last_err

        except Exception as e:
            logger.error(f"Real GGUF planning failed: {e}")
            raise

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
                "reasoning": f"Detected a teaching command from the user: '{app}' maps to the path '{path}'. I am saving this data to the local knowledge base.",
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
                    "reasoning": f"Querying the file/path information for '{app}' in order to open it directly.",
                    "action": "open",
                    "params": {"app_name": app}
                }
            else:
                return {
                    "reasoning": f"Successfully opened '{app}'. Finishing.",
                    "action": "finish",
                    "params": {"message": f"Successfully opened the application '{app}'!"}
                }

        mock_steps_database = {
            "revit 2024": [
                {
                    "reasoning": "The user requested to open Revit 2024. I will look it up in the local knowledge base and launch it using its path.",
                    "action": "open",
                    "params": {"app_name": "revit 2024"}
                },
                {
                    "reasoning": "Revit 2024 was launched successfully. I am finishing the task.",
                    "action": "finish",
                    "params": {"message": "Successfully found and launched Revit 2024!"}
                }
            ],
            "chrome": [
                {
                    "reasoning": "Opening the Google Chrome browser via a system command.",
                    "action": "open",
                    "params": {"app_name": "chrome"}
                },
                {
                    "reasoning": "Chrome has been opened. I am finishing the task.",
                    "action": "finish",
                    "params": {"message": "Google Chrome has been opened."}
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
            "reasoning": "The goal has been completed.",
            "action": "finish",
            "params": {"message": "Task completed."}
        }
