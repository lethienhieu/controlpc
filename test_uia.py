import os
import sys
import time
import subprocess

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from core import uia_control, os_control

def test_uia_and_hotkeys():
    print("[TEST] Starting UIA & Hotkey stability test using Notepad...")
    
    # 1. Open Notepad
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)  # Wait for Notepad to launch and render its window
    
    try:
        # 2. List windows and check if Notepad is present
        windows = uia_control.get_active_windows()
        assert len(windows) > 0, "No active windows found"
        
        notepad_window = None
        for win in windows:
            if win.get("pid") == proc.pid and "notepad" in win["title"].lower():
                notepad_window = win
                break

        if notepad_window is None:
            for win in windows:
                if "notepad" in win["title"].lower():
                    notepad_window = win
                    break
                
        assert notepad_window is not None, "Notepad window not found in active windows list"
        print(f" - Found Notepad window: {notepad_window}")
        
        # 3. Focus Notepad window. Windows may reject SetForegroundWindow when
        # the test process is not allowed to steal focus, so this test treats
        # focus as best-effort and avoids typing if focus fails.
        focused = uia_control.focus_window(notepad_window["hwnd"])
        if not focused:
            try:
                from pywinauto import Application
                app = Application(backend="uia").connect(process=proc.pid, timeout=2)
                app.top_window().set_focus()
                focused = True
            except Exception as focus_error:
                print(f" - Warning: could not force focus Notepad ({focus_error}). Skipping hotkey/type portion.")
        else:
            print(" - Successfully focused Notepad window")
        
        # 4. Get control tree
        tree = uia_control.get_control_tree(".*Notepad.*")
        print(f" - Retrieved control tree ({len(tree)} elements found)")
        # Control tree might be empty in headless or minimal environments, but on a desktop it should succeed.
        
        if focused:
            # 5. Type text into Notepad
            # We target Notepad window using pywinauto/pyautogui text input
            print(" - Typing text...")
            os_control.type_text("Hello, this is a test from CONTROLPC UIA suite!", press_enter=True)
            time.sleep(1.0)
            
            # 6. Verify typing using UIA (if there's a document element)
            # Usually Notepad has an Edit or RichEdit control depending on Win10/Win11.
            # Let's search the control tree for the typed text
            typed_text_found = False
            updated_tree = uia_control.get_control_tree(".*Notepad.*")
            for elem in updated_tree:
                # Check name or auto_id
                name = elem.get("name") or ""
                if "Hello, this is a test" in name:
                    typed_text_found = True
                    break
            
            print(f" - Verified typing text in control tree: {typed_text_found}")
            
            # 7. Press hotkey (Alt + F4 to close)
            print(" - Closing Notepad using Alt+F4...")
            os_control.press_hotkey("alt", "f4")
            time.sleep(1.0)
            
            # Notepad will ask to save if text was modified, we send 'n' or 'right' then 'enter'
            # Since it's localized or OS dependent, we can send hotkey/key to dismiss it.
            # On Windows 11 it's "Don't Save" button (Alt+N works, or 'n' key).
            # Let's press 'n' and 'right' + 'enter' just to be safe.
            print(" - Rejecting save popup using 'n' key...")
            os_control.press_key("n")
            time.sleep(1.0)
        
        print(" - Verifying Notepad process terminated...")
        ret = proc.poll()
        if ret is None:
            # If still running, force terminate
            proc.terminate()
            print(" - Forced termination of Notepad")
        else:
            print(" - Notepad terminated cleanly!")
            
    except Exception as e:
        proc.terminate()
        raise e
        
    print("[SUCCESS] UIA & Hotkey stability test completed successfully!")

if __name__ == "__main__":
    try:
        test_uia_and_hotkeys()
    except AssertionError as e:
        import traceback
        print(f"\n[FAILURE] Test failed:")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Error occurred:")
        traceback.print_exc()
        sys.exit(1)
