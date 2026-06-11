import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("uia_control")

try:
    import win32gui
    import win32process
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    UIA_AVAILABLE = True
except ImportError as e:
    UIA_AVAILABLE = False
    logger.warning(f"Windows UIA/pywin32/pywinauto packages are not fully installed or available: {e}")

def get_active_windows() -> List[Dict[str, Any]]:
    """
    Lists all visible windows with titles and associated process IDs.
    """
    if not UIA_AVAILABLE:
        logger.warning("UIA is not available. Skipping get_active_windows.")
        return []
        
    windows = []
    try:
        def win_enum_callback(hwnd, ctx):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "pid": pid
                        })
            except Exception as ex:
                logger.debug(f"Error checking window {hwnd}: {ex}")
                
        win32gui.EnumWindows(win_enum_callback, None)
    except Exception as e:
        logger.error(f"Failed to enumerate windows: {e}")
    return windows

def click_uia_element(window_title_re: str, auto_id: Optional[str] = None, name: Optional[str] = None, control_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Connects to a running application by window title regex and clicks a matching UIA element.
    At least auto_id or name must be specified.
    """
    if not UIA_AVAILABLE:
        return {"success": False, "error": "pywinauto/pywin32 is not installed or available."}
        
    try:
        logger.info(f"Connecting to app with window matching: '{window_title_re}'")
        app = Application(backend="uia").connect(title_re=window_title_re, timeout=3)
        dlg = app.window(title_re=window_title_re)
        
        search_params = {}
        if auto_id:
            search_params["auto_id"] = auto_id
        if name:
            search_params["title"] = name
        if control_type:
            search_params["control_type"] = control_type
            
        if not search_params:
            return {"success": False, "error": "No search parameters (auto_id, name, control_type) provided."}
            
        logger.info(f"Searching UIA element with params: {search_params}")
        element = dlg.child_window(**search_params)
        element.click_input()  # Click using mouse input simulator for better compatibility
        return {"success": True, "message": f"Successfully clicked element {search_params}"}
    except Exception as e:
        logger.error(f"UIA click failed: {e}")
        return {"success": False, "error": str(e)}

def get_control_tree(window_title_re: str) -> List[Dict[str, Any]]:
    """
    Returns a flat list of basic children controls (id, title, class, type) for debugging and AI navigation.
    """
    if not UIA_AVAILABLE:
        return []
        
    controls = []
    try:
        app = Application(backend="uia").connect(title_re=window_title_re, timeout=2)
        dlg = app.window(title_re=window_title_re)
        
        children = dlg.descendants()
        for child in children:
            try:
                controls.append({
                    "auto_id": child.automation_id(),
                    "name": child.window_text(),
                    "control_type": child.element_info.control_type,
                    "rectangle": str(child.rectangle())
                })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Failed to get control tree: {e}")
    return controls

def focus_window(hwnd) -> bool:
    if not UIA_AVAILABLE:
        return False
    try:
        import win32gui
        import win32con
        import time
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)
        return True
    except Exception as e:
        logger.error(f"Failed to focus window {hwnd}: {e}")
        return False

def focus_window_by_title(window_title_re: str) -> bool:
    if not UIA_AVAILABLE:
        return False
    import re
    import win32gui
    try:
        pattern = re.compile(window_title_re, re.IGNORECASE)
        hwnd_to_focus = None
        
        def enum_win(hwnd, extra):
            nonlocal hwnd_to_focus
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and pattern.search(title):
                    hwnd_to_focus = hwnd
                    return False
            return True
            
        win32gui.EnumWindows(enum_win, None)
        if hwnd_to_focus:
            return focus_window(hwnd_to_focus)
    except Exception as e:
        logger.error(f"Error focusing window by title '{window_title_re}': {e}")
    return False
