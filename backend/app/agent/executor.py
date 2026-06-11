import os
import time
import json
import logging
import re
from typing import List, Dict, Any, Optional

from agent.llm import LocalLLM
from agent.prompts import CHAT_REPLY_PROMPT
from agent.planner import IntentClassifier, ReActPlanner
from core import os_control, uia_control, discovery, safety
from database import memory
from policy.action_policy import ActionPolicy
from tools.registry import TOOL_REGISTRY, execute_tool_call

logger = logging.getLogger("executor")

class AgentExecutor:
    def __init__(self):
        import threading
        self.lock = threading.RLock()
        self.current_goal: str = ""
        self.status: str = "idle"  # idle, running, waiting_approval, finished, paused, error
        self.current_step: int = 0
        self.max_steps: int = 12
        self.pending_action: Optional[Dict[str, Any]] = None
        self.ai_mode: str = "mock"  # mock, gemma4
        self.safety_confirmation: bool = True
        self.source_channel: str = "local_ui"
        self.sender_id: str = "user"
        
        self.llm = LocalLLM()
        self.policy = ActionPolicy()
        self.classifier = IntentClassifier(self.llm)
        self.planner = ReActPlanner(self.llm)
        self._discovery_cache: Dict[str, str] = {}  # Cache Start Menu scan results

        # Preloaded mock databases to support quick testing
        self.mock_steps_database = {
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

    def start(self, goal: str, ai_mode: str = "mock", safety_confirmation: bool = True, source_channel: str = "local_ui", sender_id: str = "user"):
        self.current_goal = goal
        self.status = "running"
        self.current_step = 0
        self.pending_action = None
        self.ai_mode = ai_mode
        self.safety_confirmation = safety_confirmation
        self.source_channel = source_channel
        self.sender_id = sender_id
        
        # Clear previous SQLite logs for the new session
        try:
            import sqlite3
            conn = sqlite3.connect(memory.SQLITE_PATH)
            conn.cursor().execute("DELETE FROM chat_logs")
            conn.commit()
            conn.close()
        except:
            pass

        self.add_log("system", f"Khởi động tác vụ mới: '{goal}' (AI Mode: {ai_mode.upper()})", "info")
        return self.next_step()

    def add_log(self, step_type: str, message: str, status: str = "info", action_data: Optional[Dict] = None):
        memory.save_chat_log(self.current_step, step_type, message, status, action_data)
        logger.info(f"[{step_type.upper()}] {message}")

    def handle_chat_input(self, message: str, ai_mode: str = "mock", safety_confirmation: bool = True) -> Dict[str, Any]:
        """
        Processes general chat or system control inputs.
        """
        self.ai_mode = ai_mode
        self.safety_confirmation = safety_confirmation

        is_control_cmd = False
        
        # 1. Classification
        try:
            is_control_cmd = self.classifier.classify(message, ai_mode=ai_mode)
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise e

        # 2. Routing
        if is_control_cmd:
            self.start(goal=message, ai_mode=ai_mode, safety_confirmation=safety_confirmation)
            return {"type": "control", "status": self.status, "message": "Bắt đầu lập trình thực thi điều khiển..."}
        else:
            reply = ""
            if ai_mode == "mock":
                reply = "Xin chào! Tôi là CONTROLPC, trợ lý ảo cục bộ điều khiển máy tính. Tôi có thể khởi chạy ứng dụng trực tiếp, gửi chuỗi phím tắt, tương tác qua Windows UI Automation (UIA) hoặc học thêm các đường dẫn phím tắt mới. Hãy thử ra lệnh cho tôi!"
            else:
                try:
                    prompt = CHAT_REPLY_PROMPT.format(message=message)
                    reply = self.llm.generate(
                        prompt=f"<start_of_turn>user\n{prompt}\n<end_of_turn>\n<start_of_turn>model\n",
                        max_tokens=150,
                        temperature=0.7
                    )
                except Exception as e:
                    reply = f"Lỗi kết nối mô hình local: {e}"
                    
            self.status = "idle"
            self.add_log("assistant_chat", reply, "completed")
            return {"type": "chat", "status": self.status, "message": reply}

    def next_step(self) -> Dict[str, Any]:
        with self.lock:
            if self.status != "running":
                return {"status": self.status, "message": "Agent không hoạt động."}
            
            self.current_step += 1
            if self.current_step > self.max_steps:
                self.status = "error"
                self.add_log("system", "Vượt quá giới hạn số bước ReAct.", "failed")
                return {"status": self.status, "message": "Vượt quá số bước giới hạn."}

            self.add_log("system", f"Đang phân tích bước {self.current_step}...", "info")
            
            # Plan decision (skip screenshot to save time; only capture when needed for click actions)
            decision = self.plan_action()
            if not decision:
                self.status = "error"
                self.add_log("system", "Không nhận được quyết định hợp lệ từ AI.", "failed")
                return {"status": self.status}
                
            reasoning = decision.get("reasoning", "Đang xử lý...")
            action = decision.get("action")
            params = decision.get("params", {})
            
            self.add_log("reasoning", reasoning, "completed")
            
            # Evaluate safety policy
            policy_res = self.policy.evaluate_action(
                tool=action,
                params=params,
                intent=self.current_goal,
                reason=reasoning
            )
            
            risk_level = policy_res["risk_level"]
            decision_policy = policy_res["decision"]
            
            # Save Audit Log in pending/executing state
            memory.save_audit_log(
                policy_res, 
                source_channel=self.source_channel, 
                sender_id=self.sender_id, 
                executed_status="pending" if decision_policy == "requires_confirmation" else "executing"
            )
            
            action_desc = f"{action.upper()} (Mức rủi ro: {risk_level.upper()}) - Parameters: {params}"
            
            if decision_policy == "blocked":
                self.status = "error"
                self.add_log("error", f"Hành động bị CHẶN bởi hệ thống bảo mật: {policy_res['preview']['title']}. Lý do: {policy_res['preview']['summary']}", "failed")
                memory.update_audit_log_status(policy_res["action_id"], "blocked")
                return {"status": self.status, "message": "Hành động bị chặn bởi chính sách bảo mật."}
                
            self.pending_action = policy_res
            
            # Check Safety / User Approval
            if decision_policy == "requires_confirmation":
                self.status = "waiting_approval"
                self.add_log("action", f"Đang chờ phê duyệt: {action_desc}", "pending", self.pending_action)
                if self.source_channel == "telegram":
                    try:
                        from integrations.telegram import send_telegram_notification
                        send_telegram_notification(
                            self.sender_id,
                            f"⚠️ Yêu cầu phê duyệt hành động:\n"
                            f"Mục tiêu: {self.pending_action['preview']['title']}\n"
                            f"Mô tả: {self.pending_action['preview']['summary']}\n"
                            f"Vui lòng gửi mã PIN của bạn để phê duyệt thực thi."
                        )
                    except Exception as ex:
                        logger.error(f"Failed to send remote notification: {ex}")
                return {
                    "status": self.status,
                    "pending_action": self.pending_action
                }
            else:
                return self.execute_pending_action()

    def plan_action(self) -> Optional[Dict[str, Any]]:
        history_logs = memory.get_chat_logs()
        return self.planner.plan(
            goal=self.current_goal,
            step=self.current_step,
            max_steps=self.max_steps,
            history_logs=history_logs,
            ai_mode=self.ai_mode
        )

    def execute_pending_action(self) -> Dict[str, Any]:
        with self.lock:
            if not self.pending_action:
                return {"status": self.status, "message": "Không có hành động chờ."}
            
            self.status = "running"
            action = self.pending_action.get("tool") or self.pending_action.get("action")
            params = self.pending_action["params"]
            action_id = self.pending_action.get("action_id")
            
            self.add_log("action", f"Đang thực thi: {action.upper()} - {params}", "info")
            if action_id:
                memory.update_audit_log_status(action_id, "executing")
            
            success = False
            err_msg = ""
            
            try:
                if action in TOOL_REGISTRY:
                    res = execute_tool_call(action, params)
                    success = res.get("success", False)
                    err_msg = res.get("error", "")
                    if success:
                        if "message" in res:
                            self.add_log("system", f"Kết quả: {res['message']}", "info")
                        elif "content" in res:
                            self.add_log("system", f"Kết quả: Đọc thành công tệp ({res.get('length')} ký tự)", "info")
                        elif "summary" in res:
                            self.add_log("system", f"Kết quả tóm tắt: {res['summary']}", "info")
                        elif "results" in res:
                            self.add_log("system", f"Tìm kiếm hoàn tất, tìm thấy {len(res['results'])} tệp tin.", "info")
                elif action == "click":
                    # Validate coordinates safety
                    x, y = params.get("x"), params.get("y")
                    if safety.validate_click_safety(x, y):
                        res = os_control.click_mouse(x, y, params.get("click_type", "click"))
                        success = res["success"]
                        err_msg = res.get("error", "")
                    else:
                        success = False
                        err_msg = "Coordinates blocked by safety settings."
                elif action == "click_uia":
                    res = uia_control.click_uia_element(
                        window_title_re=params.get("window_title_re", ""),
                        auto_id=params.get("auto_id"),
                        name=params.get("name"),
                        control_type=params.get("control_type")
                    )
                    success = res["success"]
                    err_msg = res.get("error", "")
                elif action == "type":
                    window_title = params.get("window_title_re")
                    if window_title:
                        from core.uia_control import focus_window_by_title
                        focus_window_by_title(window_title)
                    res = os_control.type_text(params.get("text", ""), params.get("press_enter", False))
                    success = res["success"]
                    err_msg = res.get("error", "")
                elif action == "press":
                    window_title = params.get("window_title_re")
                    if window_title:
                        from core.uia_control import focus_window_by_title
                        focus_window_by_title(window_title)
                    res = os_control.press_key(params.get("key", ""))
                    success = res["success"]
                    err_msg = res.get("error", "")
                elif action == "hotkey":
                    window_title = params.get("window_title_re")
                    if window_title:
                        from core.uia_control import focus_window_by_title
                        focus_window_by_title(window_title)
                    res = os_control.press_hotkey(*params.get("keys", []))
                    success = res["success"]
                    err_msg = res.get("error", "")
                elif action == "open":
                    app_name = params.get("app_name", "")
                    # 1. Search knowledge base
                    exe_path = memory.get_app_path(app_name)
                    
                    # 2. If not found, use cached scan or run new Start Menu scan
                    if not exe_path:
                        # Check cache first to avoid repeated slow scans
                        cache_key = app_name.lower().strip()
                        if cache_key in self._discovery_cache:
                            exe_path = self._discovery_cache[cache_key]
                            self.add_log("system", f"Tìm thấy trong cache: '{app_name}' -> '{exe_path}'", "info")
                        else:
                            self.add_log("system", f"Đường dẫn '{app_name}' chưa có. Đang quét Start Menu...", "info")
                            scanned = discovery.scan_start_menu()
                            match = discovery.find_best_app_match(app_name, scanned)
                            if match:
                                matched_key, exe_path = match
                                self._discovery_cache[cache_key] = exe_path
                                self.add_log(
                                    "system",
                                    f"Phát hiện app: '{matched_key}' -> '{exe_path}'. Lưu theo tên '{app_name}'.",
                                    "info",
                                )
                                memory.save_app_path(app_name, exe_path)
    
                    # 3. Launch file/app directly
                    if exe_path:
                        res = os_control.open_app_or_file(exe_path)
                        success = res["success"]
                        err_msg = res.get("error", "")
                    else:
                        # Fallback to Win+R
                        self.add_log("system", f"Không tìm thấy đường dẫn tuyệt đối cho '{app_name}'. Dùng Win+R làm dự phòng.", "info")
                        os_control.press_hotkey("win", "r")
                        time.sleep(0.5)
                        os_control.type_text(app_name, press_enter=True)
                        success = True
                        
                elif action == "learn":
                    key = params.get("key", "")
                    val = params.get("value", "")
                    success = memory.save_app_path(key, val)
                    if success:
                        self.add_log("success", f"Đã học xong: '{key}' -> '{val}'", "completed")
                    else:
                        err_msg = "Lỗi khi cập nhật cơ sở dữ liệu."
                elif action == "finish":
                    self.status = "finished"
                    self.add_log("success", f"Tác vụ hoàn thành: {params.get('message')}", "completed")
                    self.pending_action = None
                    if self.source_channel == "telegram":
                        try:
                            from integrations.telegram import send_telegram_notification
                            send_telegram_notification(
                                self.sender_id,
                                f"✅ Tác vụ hoàn thành xuất sắc!\nKết quả: {params.get('message')}"
                            )
                        except Exception as ex:
                            logger.error(f"Failed to send finish notification: {ex}")
                    return {"status": self.status, "message": "Tác vụ hoàn thành"}
                else:
                    err_msg = f"Hành động không xác định: {action}"
            except Exception as e:
                err_msg = str(e)
                
            # Update logs status
            if success:
                self.add_log("system", "Thực thi hành động thành công.", "info")
                if action_id:
                    memory.update_audit_log_status(action_id, "completed")
                self.pending_action = None
                time.sleep(0.3)  # Giảm từ 1.0s → 0.3s: đủ để OS phản hồi, không gây delay cảm nhận
                return self.next_step()
            else:
                self.status = "error"
                self.add_log("error", f"Lỗi thực thi hành động: {err_msg}", "failed")
                if action_id:
                    memory.update_audit_log_status(action_id, "failed")
                self.pending_action = None
                if self.source_channel == "telegram":
                    try:
                        from integrations.telegram import send_telegram_notification
                        send_telegram_notification(
                            self.sender_id,
                            f"❌ Tác vụ thất bại tại bước {self.current_step}.\nLỗi: {err_msg}"
                        )
                    except Exception as ex:
                        logger.error(f"Failed to send failure notification: {ex}")
                return {"status": self.status, "error": err_msg}

    def reject_pending_action(self, reason: str = "User rejected") -> Dict[str, Any]:
        self.status = "paused"
        self.add_log("system", f"Hành động bị từ chối: {reason}", "info")
        if self.pending_action and "action_id" in self.pending_action:
            memory.update_audit_log_status(self.pending_action["action_id"], "rejected")
        self.pending_action = None
        return {"status": self.status, "message": "Đã tạm dừng tác vụ."}
