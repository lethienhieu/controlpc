# 🖥️ CONTROLPC — Local OS AI Agent

> **Điều khiển máy tính bằng ngôn ngữ tự nhiên, hoàn toàn chạy cục bộ.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18%2B-61DAFB?logo=react)](https://react.dev)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## ✨ Tính năng chính

| Tính năng | Mô tả |
|---|---|
| 🤖 **AI Agent (ReAct)** | Lập kế hoạch & thực thi đa bước với Gemma-4 |
| 🖱️ **UIA Control** | Điều khiển UI Windows qua UIAutomation |
| 🖱️ **Click Fallback** | Tìm & click element bằng màn hình nếu UIA fail |
| 📧 **Email** | Đọc, gửi email qua SMTP/IMAP |
| 💬 **Messaging** | Gửi tin nhắn Telegram |
| 📡 **Remote Gateway** | Điều khiển từ xa qua Telegram Bot + PIN |
| 🛡️ **Action Policy** | Phân loại rủi ro & duyệt từng hành động nguy hiểm |
| 🔍 **App Discovery** | Tự động tìm và mở ứng dụng trên hệ thống |
| 📝 **Memory** | Lưu lịch sử hội thoại có ngữ cảnh |

---

## 🚀 Cài đặt & Khởi chạy

### Yêu cầu
- **Python** 3.10+
- **Node.js** 18+ & npm
- **Windows** 10/11 (UIAutomation phụ thuộc Win API)

### Chạy ứng dụng

```bash
# 1. Clone repo
git clone https://github.com/lethienhieu/controlpc.git
cd controlpc

# 2. Double-click start.bat  (hoặc chạy lệnh)
start.bat
```

`start.bat` sẽ tự động:
- Kiểm tra và tạo Python virtual environment
- Cài đặt tất cả dependencies
- Build frontend production bundle
- Khởi động ứng dụng Desktop

---

## 📁 Cấu trúc dự án

```
controlpc/
├── backend/
│   ├── app/
│   │   ├── agent/          # ReAct Planner, IntentClassifier, Executor
│   │   ├── core/           # OS Control, UIA, Safety, Discovery
│   │   ├── database/       # Memory, Knowledge Base
│   │   ├── integrations/   # Telegram, SMTP/IMAP, Contacts
│   │   ├── policy/         # ActionPolicy, Risk Classifier, Permissions
│   │   └── tools/          # File, Email, Messaging, Document tools
│   ├── requirements.txt
│   └── run_backend.py
├── frontend/
│   └── src/
│       ├── App.jsx         # Main chat UI
│       └── App.css         # Styling
├── config/
│   ├── permissions.json    # Cấu hình quyền & chính sách an toàn
│   ├── contacts.json       # Danh bạ
│   └── email_settings.json
├── remote_gateway/
│   └── telegram_bot.py     # Remote control via Telegram
├── docs/
│   ├── configuration_guide.md
│   └── remote_gateway_guide.md
├── desktop.py              # Native Desktop window (webview)
├── start.bat               # One-click launcher
└── test_*.py               # Automated test suite (7 test modules)
```

---

## ⚙️ Cấu hình

### Permissions (`config/permissions.json`)
```json
{
  "allow_file_delete": false,
  "allow_network_access": true,
  "remote_gateway_enabled": false,
  "max_risk_level": "medium"
}
```

### Email (`config/email_settings.json`)
```json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "email": "your@email.com",
  "password": "your-app-password"
}
```

> 📖 Xem hướng dẫn đầy đủ tại [docs/configuration_guide.md](docs/configuration_guide.md)

---

## 🛡️ Kiến trúc an toàn

```
User Input
    │
    ▼
IntentClassifier  ──►  Phân loại: chat / task / remote
    │
    ▼
ReActPlanner  ──►  Lập kế hoạch đa bước (Gemma-4)
    │
    ▼
ActionPolicy  ──►  Đánh giá rủi ro (low/medium/high/critical)
    │
    ▼
AgentExecutor ──►  Thực thi (với approval nếu rủi ro cao)
```

- **Hành động nguy hiểm** (xóa file, gửi email) yêu cầu xác nhận của người dùng
- **Remote Gateway** mặc định TẮT, cần PIN để kích hoạt từng lệnh
- **Sandbox workspace** — không truy cập ngoài thư mục cho phép

---

## 🧪 Chạy Tests

```bash
cd controlpc
pip install pytest

# Chạy toàn bộ test suite
python -m pytest test_smoke.py test_policy.py test_tools.py test_uia.py -v

# Test từng module
python -m pytest test_planner.py -v      # Agent Planner
python -m pytest test_remote.py -v       # Remote Gateway  
python -m pytest test_click_fallback.py  # Click Fallback
```

---

## 📡 Remote Gateway (Telegram)

Cho phép điều khiển máy tính từ xa qua Telegram Bot:

1. Tạo bot tại [@BotFather](https://t.me/botfather) → lấy token
2. Cập nhật `config/permissions.json`:
   ```json
   { "remote_gateway_enabled": true, "telegram_bot_token": "..." }
   ```
3. Mỗi lệnh từ xa cần xác nhận bằng **PIN 6 số**

> 📖 Xem hướng dẫn tại [docs/remote_gateway_guide.md](docs/remote_gateway_guide.md)

---

## 🤝 Đóng góp

Pull requests luôn được chào đón! Vui lòng:
1. Fork repo
2. Tạo branch: `git checkout -b feature/ten-tinh-nang`
3. Commit: `git commit -m 'feat: mô tả thay đổi'`
4. Push: `git push origin feature/ten-tinh-nang`
5. Mở Pull Request

---

## 📄 License

MIT License — xem file [LICENSE](LICENSE) để biết thêm.

---

<div align="center">
  <strong>Xây dựng với ❤️ — CONTROLPC Local OS AI Agent</strong>
</div>
