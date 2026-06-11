import os
import sys
import json
import time
import requests

# Resolve workspace folders
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(BOT_DIR)
IN_PATH = os.path.join(WORKSPACE_DIR, "workspace", "temp", "telegram_in.json")
OUT_PATH = os.path.join(WORKSPACE_DIR, "workspace", "output", "telegram_out.json")

def process_simulated_messages():
    if not os.path.exists(IN_PATH):
        return
        
    try:
        with open(IN_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return
            
        if not data or not data.get("new_message"):
            return
            
        sender_id = data.get("sender_id", "123456789")
        text = data.get("text", "")
        
        print(f"[MOCK TG BOT] Received simulated message from {sender_id}: {text}")
        
        # Call FastAPI backend
        res = requests.post("http://127.0.0.1:8000/api/remote/telegram", json={
            "sender_id": str(sender_id),
            "text": text
        })
        
        if res.status_code == 200:
            response_data = res.json()
        else:
            response_data = {"success": False, "message": f"HTTP Error {res.status_code}: {res.text}"}
            
        print(f"[MOCK TG BOT] Backend reply: {response_data}")
        
        # Write back to simulated output file
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "status": "success",
                "backend_response": response_data
            }, f, ensure_ascii=False, indent=2)
            
        # Clear the incoming file to mark it as processed
        with open(IN_PATH, "w", encoding="utf-8") as f:
            json.dump({"new_message": False}, f)
            
    except Exception as e:
        print(f"[MOCK TG BOT] Error processing simulated message: {e}")

def run_real_polling(token):
    print(f"[TG BOT] Starting real polling loop with token: {token[:8]}...")
    offset = 0
    url = f"https://api.telegram.org/bot{token}"
    
    while True:
        try:
            res = requests.get(f"{url}/getUpdates", params={"offset": offset, "timeout": 5}, timeout=10)
            if res.status_code != 200:
                print(f"[TG BOT] getUpdates failed: {res.text}")
                time.sleep(3)
                continue
                
            updates = res.json().get("result", [])
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text")
                
                if chat_id and text:
                    print(f"[TG BOT] Msg from {chat_id}: {text}")
                    # Dispatch to FastAPI
                    api_res = requests.post("http://127.0.0.1:8000/api/remote/telegram", json={
                        "sender_id": str(chat_id),
                        "text": text
                    })
                    
                    if api_res.status_code == 200:
                        reply = api_res.json().get("message", "Tác vụ đã được ghi nhận.")
                    else:
                        reply = f"Lỗi liên kết Backend: {api_res.text}"
                        
                    # Reply back via TG
                    requests.post(f"{url}/sendMessage", json={"chat_id": chat_id, "text": reply})
                    
        except Exception as e:
            print(f"[TG BOT] Error in polling loop: {e}")
            time.sleep(3)
            
def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    # Check if config says mock
    settings_path = os.path.join(WORKSPACE_DIR, "config", "messaging_settings.json")
    safety_mode = "mock"
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                safety_mode = json.load(f).get("safety_mode", "mock").lower()
        except:
            pass
            
    if safety_mode == "mock" or not token:
        print("[TG BOT] Running in MOCK/SIMULATED mode. Polling workspace/temp/telegram_in.json...")
        while True:
            process_simulated_messages()
            time.sleep(1)
    else:
        run_real_polling(token)

if __name__ == "__main__":
    main()
