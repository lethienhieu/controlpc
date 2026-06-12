import logging

logger = logging.getLogger("safety")

# Hard ceiling fallback if the real screen size can't be queried (e.g. headless).
_FALLBACK_W, _FALLBACK_H = 3840, 2160


def _screen_size():
    """Best-effort primary screen size; falls back to a 4K ceiling on failure."""
    try:
        import pyautogui
        w, h = pyautogui.size()
        if w and h:
            return int(w), int(h)
    except Exception as e:
        logger.debug(f"Could not query screen size, using fallback: {e}")
    return _FALLBACK_W, _FALLBACK_H


def validate_click_safety(x: int, y: int) -> bool:
    """
    Checks that the targeted coordinates fall within the actual primary screen
    bounds (with a small margin), preventing clicks off-screen.
    """
    if x is None or y is None:
        logger.warning("Safety Block: click coordinates are missing.")
        return False

    width, height = _screen_size()
    margin = 2  # allow exact edges
    if not (-margin <= x <= width + margin):
        logger.warning(f"Safety Block: x={x} out of screen width [0, {width}]")
        return False
    if not (-margin <= y <= height + margin):
        logger.warning(f"Safety Block: y={y} out of screen height [0, {height}]")
        return False
    return True
