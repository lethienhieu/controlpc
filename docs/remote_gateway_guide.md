# Remote Control Gateway Configuration Guide (Telegram, WhatsApp, Zalo)

This document explains how to enable and secure the remote computer control feature through mobile applications.

---

## 1. Remote Control Safety Principles

To protect the computer from unauthorized access, CONTROLPC enforces the following mandatory safety rules:
1. **Commands Only Enter the Task Queue**: The remote gateway is only allowed to create local tasks in a pending-approval state. It has no permission to directly invoke any CLI, keyboard shortcut, or mouse click.
2. **Allowlist Authentication**: Only accounts listed in `remote_senders` are permitted to interact.
3. **Approval PIN**: For every medium/high-risk action (such as sending email or running system commands), the remote user is required to send the correct authentication PIN.
4. **Rate Limiting**: A maximum of 5 messages/commands sent within 10 seconds to prevent spam.

---

## 2. Telegram Bot Gateway Setup Guide

This is the official remote control channel and the easiest to configure at the current stage.

### Step 2.1: Create a Telegram Bot
1. Open the Telegram app and search for the official bot `@BotFather`.
2. Send the `/newbot` command and follow the instructions to name the bot.
3. Receive the **HTTP API Token** (for example: `123456789:ABCdefGhIJK...`).

### Step 2.2: Configure on CONTROLPC
Set up the credentials in the `remote_gateway/gateway_config.json` file or store them in an environment variable:
* `TELEGRAM_BOT_TOKEN`: The token of the bot you just created.

### Step 2.3: User Authorization (SQLite)
Load the administrator account information into your database or use the settings endpoint.
Example configuration for the `remote_senders` table in SQLite:
* `sender_identity`: Format `telegram:<chat_id_cua_ban>` (for example: `telegram:123456789`).
* `name`: Display name (for example: Owner).
* `enabled`: `1` (enabled).
* `auth_level`: `admin`.
* `can_create_task`: `1`.
* `can_approve_high_risk`: `1`.
* `requires_pin_for_high_risk`: `1`.
* `pin`: A 4-digit PIN used to approve remote tasks (for example: `1234`).

---

## 3. Setting Up Zalo and WhatsApp Gateways

### 3.1. Zalo Gateway (Zalo OA)
* You need to register a business Zalo Official Account (Zalo OA).
* Obtain the `App ID` and `Secret Key` from the Zalo Developer Portal.
* Update the webhook URL to point to the CONTROLPC application's `/api/remote/zalo` endpoint (requires https/ngrok configuration when running locally).

### 3.2. WhatsApp Business Gateway
* Register a WhatsApp Business API account through Meta for Developers.
* Configure a permanent Token and the phone number used to send and receive messages.
* Configure the webhook to point to the corresponding `/api/remote/whatsapp` endpoint.

> [!WARNING]
> Never use unofficial WhatsApp Web automation libraries (web automation clicks) in a production environment, to avoid having the phone number account banned.

---

## 4. Remote Command Operation Workflow
1. The user sends a message to the Bot (for example: *"Open notepad"*).
2. The Bot checks the sender account's permissions. If valid, the system creates a local Task and displays it on the Desktop screen.
3. If the task requires approval: the Bot replies with a notification message: *"⚠️ Action approval required... Please send your PIN to execute."*
4. The user sends the PIN (for example: `1234`).
5. If the PIN matches, the task is executed successfully and the Bot sends a confirmation result back to the phone.
