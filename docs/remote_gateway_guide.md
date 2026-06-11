# Hướng dẫn cấu hình Cổng điều khiển từ xa (Telegram, WhatsApp, Zalo)

Tài liệu này hướng dẫn cách kích hoạt và bảo mật tính năng điều khiển máy tính từ xa thông qua ứng dụng điện thoại.

---

## 1. Nguyên tắc An toàn Điều khiển từ xa

Để bảo vệ máy tính khỏi các truy cập trái phép, CONTROLPC áp dụng các luật an toàn bắt buộc:
1. **Chỉ nhận lệnh vào Task Queue**: Cổng remote chỉ được phép tạo task local ở trạng thái chờ duyệt. Không có quyền gọi trực tiếp bất kỳ CLI, phím tắt hay click chuột nào.
2. **Xác thực Allowlist**: Chỉ các tài khoản nằm trong danh sách `remote_senders` mới được phép tương tác.
3. **Mã PIN phê duyệt**: Với mọi hành động rủi ro trung bình/cao (như gửi mail, chạy lệnh hệ thống), người dùng từ xa bắt buộc phải gửi đúng mã PIN xác thực.
4. **Giới hạn tần suất (Rate Limiting)**: Tối đa 5 tin nhắn/lệnh gửi trong 10 giây để chống spam.

---

## 2. Hướng dẫn thiết lập Telegram Bot Gateway

Đây là kênh điều khiển từ xa chính thức và dễ cấu hình nhất trong giai đoạn hiện tại.

### Bước 2.1: Tạo Bot Telegram
1. Mở ứng dụng Telegram, tìm kiếm bot chính thức `@BotFather`.
2. Gửi lệnh `/newbot` và làm theo hướng dẫn để đặt tên bot.
3. Nhận mã **HTTP API Token** (ví dụ: `123456789:ABCdefGhIJK...`).

### Bước 2.2: Cấu hình trên CONTROLPC
Thiết lập mã thông tin trong tệp `remote_gateway/gateway_config.json` hoặc lưu vào biến môi trường:
* `TELEGRAM_BOT_TOKEN`: Token của bot vừa tạo.

### Bước 2.3: Phân quyền Người dùng (SQLite)
Nạp thông tin tài khoản quản trị vào cơ sở dữ liệu của bạn hoặc sử dụng endpoint cài đặt.
Ví dụ cấu hình cho bảng `remote_senders` trong SQLite:
* `sender_identity`: Định dạng `telegram:<chat_id_cua_ban>` (ví dụ: `telegram:123456789`).
* `name`: Tên hiển thị (ví dụ: Owner).
* `enabled`: `1` (kích hoạt).
* `auth_level`: `admin`.
* `can_create_task`: `1`.
* `can_approve_high_risk`: `1`.
* `requires_pin_for_high_risk`: `1`.
* `pin`: Mã PIN 4 chữ số dùng để phê duyệt tác vụ từ xa (ví dụ: `1234`).

---

## 3. Thiết lập Zalo và WhatsApp Gateways

### 3.1. Zalo Gateway (Zalo OA)
* Cần đăng ký một tài khoản Zalo Official Account (Zalo OA) doanh nghiệp.
* Nhận `App ID` và `Secret Key` từ Zalo Developer Portal.
* Cập nhật webhook URL trỏ về cổng `/api/remote/zalo` của ứng dụng CONTROLPC (yêu cầu cấu hình https/ngrok khi chạy local).

### 3.2. WhatsApp Business Gateway
* Đăng ký tài khoản WhatsApp Business API thông qua Meta for Developers.
* Cấu hình Token vĩnh viễn và số điện thoại gửi nhận tin nhắn.
* Cấu hình webhook trỏ về `/api/remote/whatsapp` tương ứng.

> [!WARNING]
> Tuyệt đối không sử dụng thư viện tự động hóa WhatsApp Web (web automation clicks) không chính thống ở môi trường thực tế để tránh bị khóa tài khoản số điện thoại.

---

## 4. Quy trình vận hành Lệnh từ xa
1. Người dùng gửi tin nhắn đến Bot (ví dụ: *"Mở notepad"*).
2. Bot kiểm tra quyền của tài khoản người gửi. Nếu hợp lệ, hệ thống tạo một Task local và hiển thị trên màn hình Desktop.
3. Nếu task cần phê duyệt: Bot gửi lại tin nhắn thông báo: *"⚠️ Yêu cầu phê duyệt hành động... Vui lòng gửi mã PIN của bạn để thực thi."*
4. Người dùng gửi mã PIN (ví dụ: `1234`).
5. Nếu mã PIN khớp, task được thực thi thành công và Bot gửi kết quả xác nhận về điện thoại.
