import logging

logger = logging.getLogger("safety")

# Define screen boundaries to prevent cursor clicks outside safe zones (e.g. system trays)
SAFE_ZONE_X = (0, 3840)
SAFE_ZONE_Y = (0, 2160)

def validate_click_safety(x: int, y: int) -> bool:
    """
    Checks if the targeted coordinates fall within defined safe zones.
    """
    if not (SAFE_ZONE_X[0] <= x <= SAFE_ZONE_X[1]):
        logger.warning(f"Safety Block: x coordinate {x} is out of safe range {SAFE_ZONE_X}")
        return False
    if not (SAFE_ZONE_Y[0] <= y <= SAFE_ZONE_Y[1]):
        logger.warning(f"Safety Block: y coordinate {y} is out of safe range {SAFE_ZONE_Y}")
        return False
    return True
