# CONTROLPC Configuration Guide (Email, Folders, Contacts)

This document explains how to set up security settings, folder permissions, the contact list, and the Email connection for the CONTROLPC system.

All JSON configuration files are placed in the root `config/` folder.

---

## 1. Folder & Application Access Configuration (`config/permissions.json`)

The `config/permissions.json` file controls the level of automation and the data areas the Agent is allowed to operate on.

### 1.1. Folder Permissions (File Permissions)
* `allowed_read_dirs`: List of folders the Agent is allowed to read data from (e.g., Documents, Downloads).
* `allowed_write_dirs`: List of folders the Agent is allowed to create, write, or modify files in.
* `blocked_dirs`: Strictly forbidden folders (e.g., `C:\Windows`, `C:\Program Files`, AppData). The Agent is blocked immediately if it attempts to read/write in these areas.
* `allowed_extensions`: List of file formats allowed for writing (e.g., `.docx`, `.xlsx`, `.pdf`, `.txt`, `.png`, `.jpg`).
* `max_attachment_mb`: Maximum size limit for attachments sent via email.

### 1.2. Application Launch Permissions (App Permissions)
Each application is assigned a run policy (`launch`):
* `allow`: Allow it to run directly.
* `confirm`: Require user confirmation.
* `block`: Forbid it from running.
* `allowed_commands`: List of shell/CLI commands allowed to be executed (applies only to CLI tools such as `cmd` or `powershell`).

### 1.3. Safety Settings (Safety Settings)
* `coordinate_click_enabled`: `true` or `false` to enable/disable the absolute mouse-coordinate click feature.
* `remote_gateway_enabled`: Enable/disable receiving remote commands.
* `default_action_policy`: The default approval policy for normal tasks (`confirm_once`, `confirm_final`, or `none`).

---

## 2. Email and Connection Configuration (`config/email_settings.json`)

Set up the sending account and configure the SMTP/IMAP ports:

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
> Do not store raw passwords in the JSON configuration file. The mailbox connection password must be stored via the secure environment variable `EMAIL_PASSWORD` or Windows Credential Manager.

---

## 3. Contacts & Contact Permission Configuration (`config/contacts.json`)

Each contact is assigned a trust level to avoid automatically sending sensitive emails/messages:

* **Policy level (`policy`):**
  1. `draft_only`: Compose drafts only; never actually send.
  2. `confirm_before_send`: Enforce a final confirmation prompt (requires confirm-final) in the main interface before sending.
  3. `auto_send_allowed`: Allow automatic sending without prompting (should only be assigned to personal or test mailboxes).
  4. `blocked`: Forbid sending information.

Example `config/contacts.json` file:
```json
{
  "contacts": [
    {
      "name": "Sample Director",
      "email": "nam@example.com",
      "phone": "+84901234567",
      "policy": "confirm_before_send"
    },
    {
      "name": "Sample HR",
      "email": "hang@example.com",
      "phone": "+84988888888",
      "policy": "draft_only"
    }
  ]
}
```
