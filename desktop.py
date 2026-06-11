import os
import sys
import time
import threading
import webview
import uvicorn

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from backend.app.main import app

def perform_health_check():
    print("========================================================")
    print("               CONTROLPC - HEALTH CHECK                 ")
    print("========================================================")
    
    # 1. Check Python and dependencies
    print("[CHECK] Python packages...")
    packages = ["fastapi", "uvicorn", "pyautogui", "PIL", "mss", "pydantic", "webview"]
    all_ok = True
    for pkg in packages:
        try:
            __import__(pkg)
            print(f"  - {pkg}: OK")
        except ImportError:
            print(f"  - {pkg}: FAILED")
            all_ok = False
            
    # Check pywin32/pywinauto
    try:
        import win32gui
        import pywinauto
        print("  - win32gui/pywinauto (UIA): OK")
    except ImportError:
        print("  - win32gui/pywinauto (UIA): NOT INSTALLED (UIA fallback disabled)")

    # 2. Check Model
    print("[CHECK] Gemma-4 GGUF Model...")
    from agent.llm import LocalLLM
    llm = LocalLLM()
    if llm.model_path and os.path.exists(llm.model_path):
        print(f"  - Model file: OK ({llm.model_path})")
    else:
        print("  - Model file: NOT FOUND (Model path not configured or file missing)")

    # 3. Check Frontend dist
    print("[CHECK] Frontend bundle...")
    dist_file = os.path.join(BASE_DIR, "frontend", "dist", "index.html")
    if os.path.exists(dist_file):
        print(f"  - Frontend bundle: OK ({dist_file})")
    else:
        print("  - Frontend bundle: NOT BUILT (will run dev server if running)")
        
    print("========================================================\n")

def run_backend():
    print("[DESKTOP] Launching FastAPI Backend on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

if __name__ == "__main__":
    # Perform pre-launch health checks
    perform_health_check()

    # Start FastAPI in background
    backend_thread = threading.Thread(target=run_backend, daemon=True)
    backend_thread.start()
    
    time.sleep(1.2) # Allow backend to bind port
    
    # Locate Frontend entry point
    dist_file = os.path.join(BASE_DIR, "frontend", "dist", "index.html")
    if os.path.exists(dist_file):
        print(f"[DESKTOP] Loading offline UI build from: {dist_file}")
        url = dist_file
    else:
        print("[DESKTOP] Offline build not found. Loading from Vite Dev Server at http://localhost:5173")
        url = "http://localhost:5173"
        
    print("[DESKTOP] Launching PyWebView Native Container...")
    window = webview.create_window(
        title="CONTROLPC Local Agent Shell",
        url=url,
        width=1280,
        height=800,
        resizable=True,
        min_size=(1024, 768),
        background_color="#f6f8fb" # Match default page light theme background
    )
    
    webview.start()
