import os
import subprocess
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("discovery")

# Utility/helper apps that should lose to the primary application when names
# overlap. The penalty only applies when the keyword is in the candidate but NOT
# in the user's query, so typing "task manager" won't penalise "manager".
AUXILIARY_KEYWORDS = (
    "worksharing", "monitor", "accelerator", "uninstall", "updater", "update",
    "license", "licensing", "genuine", "feedback", "repair", "language pack",
    "content library", "batch print", "etransmit", "viewer", "sample",
    "diagnostic", "diagnostics", "setup", "installer", "configurator", "config",
    "trial", "readme", "documentation", "help", "crash", "report", "recovery",
    "migrate", "migration", "cleanup", "add-in", "addin", "plugin", "utility",
    "utilities", "reset", "activation", "activate", "register", "registration",
)


def score_app_match(query: str, app_key: str, exe_path: str) -> float:
    """Score how well an app entry matches a user query. Higher is better."""
    q = query.lower().strip()
    k = app_key.lower().strip()
    if not q or not k:
        return -1.0

    if q == k:
        return 10000.0

    score = 0.0
    exe_name = os.path.splitext(os.path.basename(exe_path))[0].lower()
    q_compact = q.replace(" ", "")
    exe_compact = exe_name.replace(" ", "")

    # Penalise helper/companion apps (monitor, updater, worksharing, ...).
    for aux in AUXILIARY_KEYWORDS:
        if aux in k and aux not in q:
            score -= 500.0

    # Strong bonus when the executable name matches the query (the canonical app).
    if q_compact == exe_compact or exe_compact == q_compact.replace(".exe", ""):
        score += 800.0
    elif q_compact in exe_compact or exe_compact in q_compact:
        score += 400.0

    q_words = [w for w in q.split() if w]
    if q in k:
        score += 300.0 - len(k) * 0.5
    elif k in q:
        score += 250.0 - len(q) * 0.3
    else:
        matched_words = sum(1 for w in q_words if w in k)
        if matched_words != len(q_words):
            return -1.0
        score += 80.0 * matched_words - len(k) * 0.3

    # Prefer the most specific (fewest extra words) candidate: "revit" should pick
    # "Revit 2024" over "Revit Worksharing Monitor".
    extra_tokens = max(0, len(k.split()) - len(q_words))
    score -= extra_tokens * 40.0

    return score


def find_app_candidates(query, candidates: Dict[str, str], top_n: int = 5):
    """Return the top-N (app_key, exe_path, score) matches with score > 0,
    sorted best-first. Used for confidence/ambiguity decisions."""
    scored = []
    for key, path in candidates.items():
        s = score_app_match(query, key, path)
        if s > 0:
            scored.append((key, path, s))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[:top_n]


def find_best_app_match(query: str, candidates: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """Return the best (app_key, exe_path) match for a query, or None."""
    best_key = None
    best_path = None
    best_score = 0.0

    for key, path in candidates.items():
        score = score_app_match(query, key, path)
        if score > best_score:
            best_score = score
            best_key = key
            best_path = path

    if best_key is None or best_score <= 0:
        return None
    return best_key, best_path

def resolve_lnk_target_powershell(lnk_path: str) -> str:
    """
    Decodes a Windows .lnk shortcut file using a native PowerShell script.
    Extremely robust and does not require third-party libraries.
    """
    try:
        lnk_path_escaped = lnk_path.replace("'", "''")
        cmd = f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path_escaped}'); write-output $s.TargetPath"
        
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=4
        )
        if res.returncode == 0:
            target = res.stdout.strip()
            if target.lower().endswith(".exe") or (os.path.exists(target) and not os.path.isdir(target)):
                return target
    except Exception as e:
        logger.warning(f"Error decoding shortcut {lnk_path}: {e}")
    return ""

def scan_start_menu() -> Dict[str, str]:
    """
    Scans both System-wide and Current User Start Menu paths.
    Returns a dictionary mapping lowercase application names to their absolute .exe paths.
    """
    discovered_apps = {}
    start_menu_paths = []
    
    # 1. Current user's Start Menu
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        start_menu_paths.append(os.path.join(user_profile, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"))
        
    # 2. System-wide Start Menu
    program_data = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
    start_menu_paths.append(os.path.join(program_data, "Microsoft", "Windows", "Start Menu", "Programs"))

    logger.info("Starting Windows Start Menu scanning...")
    
    for base_path in start_menu_paths:
        if not os.path.exists(base_path):
            continue
            
        for root, _, files in os.walk(base_path):
            for file in files:
                if file.lower().endswith(".lnk"):
                    lnk_full_path = os.path.join(root, file)
                    app_name = os.path.splitext(file)[0].lower().strip()
                    
                    exe_target = resolve_lnk_target_powershell(lnk_full_path)
                    if exe_target:
                        discovered_apps[app_name] = exe_target
                        
    logger.info(f"Scan complete. Discovered {len(discovered_apps)} applications from Start Menu.")
    return discovered_apps

def find_file_in_folders(filename: str, search_roots: List[str] = None) -> List[str]:
    """
    Performs a fast recursive search for a specific filename within common directories.
    """
    if search_roots is None:
        user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        search_roots = [
            os.path.join(user_profile, "Desktop"),
            os.path.join(user_profile, "Documents")
        ]
        
    found_files = []
    logger.info(f"Searching for file '{filename}' inside: {search_roots}...")
    
    for root_dir in search_roots:
        if not os.path.exists(root_dir):
            continue
        for root, _, files in os.walk(root_dir):
            for file in files:
                if filename.lower() in file.lower():
                    found_files.append(os.path.join(root, file))
                    if len(found_files) >= 10:  # Cap at 10 results
                        break
            if len(found_files) >= 10:
                break
                
    return found_files
