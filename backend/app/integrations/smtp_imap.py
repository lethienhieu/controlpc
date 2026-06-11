import os
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Any

logger = logging.getLogger("integrations.smtp_imap")

# Resolve workspace folders
INTEGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(INTEGRATIONS_DIR)))
SETTINGS_PATH = os.path.join(WORKSPACE_DIR, "config", "email_settings.json")

def load_email_settings() -> Dict[str, Any]:
    """Loads email settings from config."""
    if not os.path.exists(SETTINGS_PATH):
        return {"safety_mode": "mock", "smtp_host": "smtp.example.com", "smtp_port": 587}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading email settings: {e}")
        return {"safety_mode": "mock"}

def send_email_smtp(to_email: str, subject: str, body: str, attachments: List[str] = None) -> Dict[str, Any]:
    """
    Composes and sends an email via SMTP.
    If safety_mode is 'mock', it outputs the email as an EML draft file on disk.
    """
    settings = load_email_settings()
    safety_mode = settings.get("safety_mode", "mock").lower()
    from_email = settings.get("from_email", "controlpc@example.com")
    
    # 1. Compose email MIME structure
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    
    msg.attach(MIMEText(body, "plain", "utf-8"))
    
    # Process attachments
    attached_files = []
    if attachments:
        for filepath in attachments:
            if not os.path.exists(filepath):
                logger.warning(f"Attachment file not found: {filepath}")
                continue
            try:
                filename = os.path.basename(filepath)
                with open(filepath, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename= {filename}",
                    )
                    msg.attach(part)
                    attached_files.append(filename)
            except Exception as e:
                logger.error(f"Failed to attach file {filepath}: {e}")
                
    # 2. Execute send based on safety_mode
    if safety_mode == "mock":
        # Write to EML file in workspace/output for validation
        eml_filename = f"draft_email_{to_email.replace('@', '_at_')}.eml"
        eml_path = os.path.join(WORKSPACE_DIR, "workspace", "output", eml_filename)
        
        try:
            with open(eml_path, "w", encoding="utf-8") as f:
                f.write(msg.as_string())
            logger.info(f"[MOCK SMTP] Saved email to EML draft at: {eml_path}")
            return {
                "success": True,
                "mode": "mock",
                "message": f"Đã lưu email nháp (giả lập SMTP) thành công vào: {eml_filename}",
                "eml_path": eml_path,
                "attachments": attached_files
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to save mock email: {e}"}
            
    else:
        # Live SMTP sending (Requires valid SMTP server configurations)
        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port", 587)
        smtp_user = settings.get("smtp_user")
        
        # Read SMTP password from environment variables (No hardcoded passwords!)
        smtp_password = os.environ.get("CONTROLPC_SMTP_PASSWORD")
        if not smtp_password:
            return {"success": False, "error": "SMTP password not configured in environment variable 'CONTROLPC_SMTP_PASSWORD'."}
            
        try:
            logger.info(f"Connecting to SMTP server {smtp_host}:{smtp_port}...")
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_email, msg.as_string())
            server.quit()
            
            logger.info(f"Successfully sent email to {to_email}")
            return {
                "success": True,
                "mode": "live",
                "message": f"Đã gửi email thật thành công đến {to_email}",
                "attachments": attached_files
            }
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            return {"success": False, "error": str(e)}
