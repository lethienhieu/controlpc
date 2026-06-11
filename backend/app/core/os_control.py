import os
import time
import base64
import logging
from io import BytesIO
from PIL import Image, ImageDraw
import pyautogui
import mss

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("os_control")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3  # Slight pause for stability

# Cache path for screen captures
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)
SCREENSHOT_PATH = os.path.join(TEMP_DIR, "screenshot.png")

def capture_screenshot(draw_cursor=True, click_marker=None):
    """
    Captures the primary monitor and saves it to a temp path.
    Returns Base64 representation, width, height, and file path.
    """
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            if draw_cursor or click_marker:
                try:
                    draw = ImageDraw.Draw(img)
                    if draw_cursor:
                        cursor_x, cursor_y = pyautogui.position()
                        # Draw virtual orange cursor dot for UI preview
                        draw.ellipse([cursor_x - 6, cursor_y - 6, cursor_x + 6, cursor_y + 6], fill="orange", outline="white", width=2)
                    
                    if click_marker:
                        cx, cy = click_marker
                        # Draw a red target marker: outer circle, inner dot, and crosshairs
                        draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], outline="red", width=3)
                        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill="red")
                        # Draw crosshair lines
                        draw.line([cx - 25, cy, cx - 10, cy], fill="red", width=2)
                        draw.line([cx + 10, cy, cx + 25, cy], fill="red", width=2)
                        draw.line([cx, cy - 25, cx, cy - 10], fill="red", width=2)
                        draw.line([cx, cy + 10, cx, cy + 25], fill="red", width=2)
                        
                        # Add label text: Coordinates
                        draw.rectangle([cx + 18, cy - 10, cx + 140, cy + 10], fill="red")
                        draw.text((cx + 22, cy - 8), f"CLICK: ({cx}, {cy})", fill="white")
                except Exception as e:
                    logger.warning(f"Could not draw cursor or click marker: {e}")

            img.save(SCREENSHOT_PATH, format="PNG")
            
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            return {
                "success": True,
                "base64": f"data:image/png;base64,{img_str}",
                "width": img.size[0],
                "height": img.size[1],
                "filepath": SCREENSHOT_PATH
            }
    except Exception as e:
        logger.error(f"Screenshot capture failed: {e}")
        # Return fallback dark canvas if running in headless or error state
        mock_img = Image.new("RGB", (1920, 1080), color=(20, 20, 25))
        buffered = BytesIO()
        mock_img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return {
            "success": False,
            "base64": f"data:image/png;base64,{img_str}",
            "width": 1920,
            "height": 1080,
            "error": str(e)
        }

def move_mouse(x, y):
    """Moves mouse to (x, y) coordinates."""
    try:
        logger.info(f"Moving mouse to ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.4)
        return {"success": True, "position": (x, y)}
    except Exception as e:
        logger.error(f"Mouse move failed: {e}")
        return {"success": False, "error": str(e)}

def click_mouse(x=None, y=None, click_type="click"):
    """
    Clicks at specified (x, y) or current location.
    click_type can be 'click', 'double_click', or 'right_click'.
    """
    try:
        if x is not None and y is not None:
            pyautogui.moveTo(x, y, duration=0.3)
            
        logger.info(f"Executing click: {click_type} at ({x or 'current'}, {y or 'current'})")
        
        if click_type == "click":
            pyautogui.click()
        elif click_type == "double_click":
            pyautogui.doubleClick()
        elif click_type == "right_click":
            pyautogui.rightClick()
        else:
            pyautogui.click()
            
        return {"success": True}
    except Exception as e:
        logger.error(f"Mouse click failed: {e}")
        return {"success": False, "error": str(e)}

def type_text(text, press_enter=False):
    """Writes text and optionally presses Enter."""
    try:
        logger.info(f"Typing text: '{text}' (Enter={press_enter})")
        pyautogui.write(text, interval=0.03)
        if press_enter:
            pyautogui.press("enter")
        return {"success": True}
    except Exception as e:
        logger.error(f"Text typing failed: {e}")
        return {"success": False, "error": str(e)}

def press_key(key):
    """Presses a single keyboard key."""
    try:
        logger.info(f"Pressing key: '{key}'")
        pyautogui.press(key)
        return {"success": True}
    except Exception as e:
        logger.error(f"Key press failed: {e}")
        return {"success": False, "error": str(e)}

def press_hotkey(*keys):
    """Presses keyboard shortcuts (e.g. ['ctrl', 'c'])."""
    try:
        logger.info(f"Pressing hotkeys: {keys}")
        pyautogui.hotkey(*keys)
        return {"success": True}
    except Exception as e:
        logger.error(f"Hotkey press failed: {e}")
        return {"success": False, "error": str(e)}

def open_app_or_file(target_path):
    """
    Launches a file or app directly via absolute path using os.startfile.
    This mimics a native double-click action in Windows, supporting default application mappings.
    """
    try:
        target_path = os.path.normpath(target_path)
        if not os.path.exists(target_path):
            return {"success": False, "error": f"Path not found: {target_path}"}
            
        logger.info(f"Launching target path directly: '{target_path}'")
        os.startfile(target_path)
        return {"success": True, "method": "direct_startfile", "path": target_path}
    except Exception as e:
        logger.error(f"Direct startfile launch failed: {e}")
        return {"success": False, "error": str(e)}
