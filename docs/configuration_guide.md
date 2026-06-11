# Hướng dẫn cấu hình CONTROLPC (Email, Thư mục, Danh bạ)

Tài liệu này hướng dẫn cách thiết lập các cài đặt bảo mật, phân quyền thư mục, danh bạ liên hệ và kết nối Email cho hệ thống CONTROLPC.

Mọi tệp cấu hình JSON được đặt trong thư mục gốc `config/`.

---

## 1. Cấu hình quyền truy cập Thư mục & Ứng dụng (`config/permissions.json`)

Tệp `config/permissions.json` kiểm soát mức độ tự động hóa và vùng dữ liệu được phép thao tác của Agent.

### 1.1. Phân quyền Thư mục (File Permissions)
* `allowed_read_dirs`: Danh sách các thư mục Agent được phép đọc dữ liệu (ví dụ: Documents, Downloads).
* `allowed_write_dirs`: Danh sách các thư mục Agent được phép tạo, ghi hoặc sửa đổi tệp tin.
* `blocked_dirs`: Thư mục cấm tuyệt đối (ví dụ: `C:\Windows`, `C:\Program Files`, AppData). Agent sẽ bị chặn ngay lập tức nếu cố đọc/ghi tại các vùng này.
* `allowed_extensions`: Danh sách định dạng tệp tin được phép ghi (ví dụ: `.docx`, `.xlsx`, `.pdf`, `.txt`, `.png`, `.jpg`).
* `max_attachment_mb`: Giới hạn kích thước tối đa của tệp đính kèm khi gửi qua email.

### 1.2. Quyền khởi chạy Ứng dụng (App Permissions)
Mỗi ứng dụng được định nghĩa chính sách chạy (`launch`):
* `allow`: Cho phép chạy trực tiếp.
* `confirm`: Yêu cầu xác nhận của người dùng.
* `block`: Cấm chạy.
* `allowed_commands`: Danh sách các lệnh shell/CLI được phép thực thi (chỉ áp dụng đối với các công cụ CLI như `cmd` hoặc `powershell`).

### 1.3. Cài đặt An toàn (Safety Settings)
* `coordinate_click_enabled`: `true` hoặc `false` để bật/tắt tính năng click theo tọa độ chuột tuyệt đối.
* `remote_gateway_enabled`: Bật/tắt việc nhận lệnh từ xa.
* `default_action_policy`: Chính sách duyệt mặc định đối với các tác vụ thông thường (`confirm_once`, `confirm_final` hoặc `none`).

---

## 2. Cấu hình Email và Kết nối (`config/email_settings.json`)

Thiết lập tài khoản gửi thư và cấu hình cổng SMTP/IMAP:

```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "imap_server": "imap.gmail.com",
  "imap_port": 993,
  "sender_email": "your-email@gmail.com",
  "username": "your-email@gmail.com",
  "use_tls": true
}
```

> [!IMPORTANT]
> Không lưu mật khẩu thô trong tệp cấu hình JSON. Mật khẩu kết nối hòm thư phải được lưu thông qua biến môi trường bảo mật `EMAIL_PASSWORD` hoặc Windows Credential Manager.

---

## 3. Cấu hình Danh bạ & Phân quyền liên hệ (`config/contacts.json`)

Mỗi liên hệ được phân mức độ tin cậy để tránh tự động gửi email/tin nhắn nhạy cảm:

* **Mức độ chính sách (`policy`):**
  1. `draft_only`: Chỉ soạn bản nháp (draft), tuyệt đối không gửi thật.
  2. `confirm_before_send`: Enforce hỏi xác nhận cuối (requires confirm-final) tại giao diện chính trước khi gửi.
  3. `auto_send_allowed`: Cho phép gửi tự động không cần hỏi (chỉ nên gán cho hòm thư cá nhân hoặc kiểm thử).
  4. `blocked`: Cấm gửi thông tin.

Ví dụ tệp `config/contacts.json`:
```json
{
  "contacts": [
    {
      "name": "Nam GĐ",
      "email": "nam@example.com",
      "phone": "+84901234567",
      "policy": "confirm_before_send"
    },
    {
      "name": "Hằng HR",
      "email": "hang@example.com",
      "phone": "+84988888888",
      "policy": "draft_only"
    }
  ]
}
```
