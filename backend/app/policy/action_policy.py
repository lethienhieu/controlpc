import logging
import uuid
from typing import Dict, Any, Tuple

from policy import risk, permissions

logger = logging.getLogger("policy.action_policy")

def normalize_label(s: str) -> str:
    s = s.lower()
    replacements = {
        'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
        'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
        'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
        'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
        'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
        'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        'đ': 'd',
        '_': ' ', '-': ' '
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s

class ActionPolicy:
    def __init__(self):
        # Initialize default policies or configs if needed
        pass

    def evaluate_action(self, tool: str, params: Dict[str, Any], intent: str = "general", reason: str = "") -> Dict[str, Any]:
        """
        Evaluates an action proposal against safety policy rules.
        Returns a dict conforming to the Action Schema:
        {
            "action_id": str,
            "tool": str,
            "intent": str,
            "risk_level": str,     # 'low', 'medium', 'high', 'blocked'
            "decision": str,       # 'allowed', 'blocked', 'requires_confirmation'
            "confirmation_mode": str, # 'none', 'notify', 'confirm_once', 'confirm_final', 'manual_only'
            "target": dict,
            "params": dict,
            "reason": str,
            "preview": {
                "title": str,
                "summary": str
            },
            "rollback_hint": str
        }
        """
        action_id = f"act_{uuid.uuid4().hex[:8]}"
        
        # 1. Classify risk level
        risk_level = risk.classify_action_risk(tool, params)
        
        # Default structures
        target = {}
        preview_title = f"Thực hiện: {tool}"
        preview_summary = f"Chạy công cụ {tool} với các tham số: {params}"
        rollback_hint = "Không thể thu hồi một cách dễ dàng."
        
        decision = "allowed"
        confirmation_mode = "none"
        
        # Resolve target information
        if "path" in params:
            target["file"] = params["path"]
        elif "file" in params:
            target["file"] = params["file"]
        elif "filepath" in params:
            target["file"] = params["filepath"]
            
        if "app_name" in params:
            target["app"] = params["app_name"]
            
        if "recipient" in params:
            target["recipient"] = params["recipient"]
        elif "to" in params:
            target["recipient"] = params["to"]

        # 2. Blocked Risk Level immediately blocks the action
        if risk_level == "blocked":
            return self._build_result(
                action_id, tool, intent, risk_level, "blocked", "manual_only",
                target, params, reason, "Bị chặn bởi hệ thống bảo mật",
                "Hành động này nằm ngoài phạm vi an toàn và bị cấm thực thi.",
                "Hành động không được phép chạy."
            )

        # 3. Check specific tool permissions
        tool_lower = tool.lower()
        
        # File Read check
        if tool_lower in ["file.open", "document.read_text", "document.summarize"]:
            filepath = params.get("path") or params.get("file") or params.get("filepath", "")
            if filepath and not permissions.check_file_read_permission(filepath):
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Truy cập file bị chặn",
                    f"Không có quyền đọc file tại đường dẫn: {filepath}",
                    "Hành động không được phép chạy."
                )
                
        # File Write check
        if tool_lower in ["file.copy", "file.rename", "file.create_folder", "document.create_docx", "document.create_pdf"]:
            destpath = params.get("dest_path") or params.get("path") or params.get("file") or params.get("filepath", "")
            if destpath and not permissions.check_file_write_permission(destpath):
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Tạo/Ghi file bị chặn",
                    f"Không có quyền ghi hoặc định dạng đuôi file không hợp lệ tại: {destpath}",
                    "Hành động không được phép chạy."
                )

        # App launch checks
        if tool_lower == "open":
            app_name = params.get("app_name", "")
            launch_policy = permissions.get_app_launch_policy(app_name)
            
            if launch_policy == "block":
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Khởi chạy ứng dụng bị chặn",
                    f"Ứng dụng '{app_name}' nằm trong danh mục cấm chạy.",
                    "Hành động không được phép chạy."
                )
            elif launch_policy == "confirm":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_once"
                preview_title = f"Mở ứng dụng '{app_name}'"
                preview_summary = f"Yêu cầu khởi chạy ứng dụng '{app_name}' ngoài allowlist chính thức."
                rollback_hint = "Có thể tắt ứng dụng thủ công."
                
        # Click Coordination Safety
        if tool_lower == "click":
            safety = permissions.get_safety_settings()
            click_enabled = safety.get("coordinate_click_enabled", False)
            if not click_enabled:
                # If coordinate click is globally disabled, downgrade or block it
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Click tọa độ bị chặn",
                    "Click chuột theo tọa độ (coordinate click) hiện đang bị tắt trong cấu hình an toàn.",
                    "Vui lòng bật click tọa độ trong cài đặt nếu thực sự cần thiết."
                )
            else:
                decision = "requires_confirmation"
                confirmation_mode = "confirm_final"
                preview_title = "Click chuột theo tọa độ"
                preview_summary = f"Nhấp chuột tại tọa độ X={params.get('x')}, Y={params.get('y')} trên màn hình."
                rollback_hint = "Hành động nhấp chuột không thể thu hồi."

        # Email / Message send checks
        if tool_lower in ["email.send", "message.send"]:
            recipient = target.get("recipient", "default")
            send_policy = permissions.get_contact_send_policy(recipient)
            
            if send_policy == "blocked":
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Gửi tin bị chặn",
                    f"Liên hệ '{recipient}' nằm trong danh sách cấm gửi tự động.",
                    "Hành động không được phép chạy."
                )
            elif send_policy == "draft_only":
                # If contact only allows drafting, block the send tool call
                return self._build_result(
                    action_id, tool, intent, "blocked", "blocked", "manual_only",
                    target, params, reason, "Gửi tin bị chặn (Chỉ cho phép soạn nháp)",
                    f"Liên hệ '{recipient}' chỉ chấp nhận tạo bản nháp (draft). Không được gửi trực tiếp.",
                    "Thay thế bằng hành động tạo bản nháp."
                )
            elif send_policy == "confirm_before_send":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_final"
                preview_title = "Gửi thông tin / Email thật"
                preview_summary = f"Gửi nội dung đến '{recipient}'. Hành động này sẽ gửi dữ liệu ra bên ngoài."
                rollback_hint = "Không thể thu hồi sau khi đã gửi email/tin nhắn."
            elif send_policy == "auto_send_allowed":
                # Allowed to send automatically without confirmation
                decision = "allowed"
                confirmation_mode = "none"

        # Dangerous labels check: Send, Delete, Pay, Submit
        is_dangerous_click = False
        if tool_lower == "click_uia":
            name_val = normalize_label(str(params.get("name") or ""))
            auto_id_val = normalize_label(str(params.get("auto_id") or ""))
            for label in ["send", "delete", "pay", "submit", "gui", "xoa", "thanh toan", "nop"]:
                if label in name_val or label in auto_id_val:
                    is_dangerous_click = True
                    break
                    
        if is_dangerous_click:
            risk_level = "high"
            decision = "requires_confirmation"
            confirmation_mode = "confirm_final"
            preview_title = f"Click nhãn nguy hiểm: {params.get('name') or params.get('auto_id')}"
            preview_summary = f"Cảnh báo: Nhấp vào nút nhạy cảm/nguy hiểm '{params.get('name') or params.get('auto_id')}'."
            rollback_hint = "Hành động nhấp chuột không thể thu hồi."

        # 4. Fallback based on Risk Level if not explicitly resolved
        if decision == "allowed":
            if risk_level == "high":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_final"
            elif risk_level == "medium":
                decision = "requires_confirmation"
                confirmation_mode = "confirm_once"
            elif risk_level == "low":
                decision = "allowed"
                confirmation_mode = "none"

        # Special case: Agent safety settings override
        # If user turned on global safety confirmation, every non-low and non-finish action requires confirmation
        if decision == "allowed" and tool_lower not in ["finish", "learn"]:
            # If default safety is active, upgrade to confirm_once
            decision = "requires_confirmation"
            confirmation_mode = "confirm_once"

        return self._build_result(
            action_id, tool, intent, risk_level, decision, confirmation_mode,
            target, params, reason, preview_title, preview_summary, rollback_hint
        )

    def _build_result(
        self, action_id: str, tool: str, intent: str, risk_level: str,
        decision: str, confirmation_mode: str, target: Dict[str, Any],
        params: Dict[str, Any], reason: str, preview_title: str,
        preview_summary: str, rollback_hint: str
    ) -> Dict[str, Any]:
        return {
            "action_id": action_id,
            "tool": tool,
            "intent": intent,
            "risk_level": risk_level,
            "decision": decision,
            "confirmation_mode": confirmation_mode,
            "target": target,
            "params": params,
            "reason": reason,
            "preview": {
                "title": preview_title,
                "summary": preview_summary
            },
            "rollback_hint": rollback_hint
        }
