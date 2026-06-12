"""Central filesystem layout for CONTROLPC — the single source of truth for
where the agent keeps its "brain" (state/memory), config, logs, cache and
transient run files.

Design (mirrors OpenClaw's single dotfolder-state-dir convention):

    <repo>/.controlpc/            # THE AGENT BRAIN (gitignored; override CONTROLPC_BRAIN_DIR)
        brain.json               # manifest: {schema_version, created, layout}
        config/                  # active, user-editable config (copied from shipped /config on first run)
        state/                   # durable memory: history.db (chat/audit/remote/skill-library) + knowledge_base.json
        logs/                    # rotating logs
        cache/screenshots/       # regenerable scratch (safe to delete)
        run/                     # transient in-flight drafts (deleted after send)

User files stay OUTSIDE the brain in <repo>/workspace/ (input/output/templates).
Large model weights (models/) and the CUDA runtime (llama/) stay where they are.
Secrets stay in Windows Credential Manager (never on disk).

Everything is resolved at runtime here so no other module hardcodes paths, and
the whole brain can be relocated (e.g. to %LOCALAPPDATA%\\ControlPC for a
packaged build) by setting CONTROLPC_BRAIN_DIR.
"""
import os
import json
import time
import shutil
import logging

logger = logging.getLogger("core.paths")

# backend/app/core/paths.py -> repo root is 4 levels up
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHIPPED_CONFIG_DIR = os.path.join(REPO_ROOT, "config")          # git-tracked defaults/templates
WORKSPACE_DIR = os.path.join(REPO_ROOT, "workspace")            # user files (NOT the brain)

# Config files that have a shipped default and an active (brain) copy.
_SHIPPED_CONFIG_FILES = ("permissions.json", "email_settings.json",
                         "messaging_settings.json", "contacts.json")


def brain_dir() -> str:
    """The agent brain lives in the OS-standard per-user local data dir
    (Windows: %LOCALAPPDATA%\\ControlPC), so it is always user-writable even when
    the app is installed in a read-only location (e.g. Program Files), and is kept
    out of the code tree. Override entirely with the CONTROLPC_BRAIN_DIR env var."""
    env = os.environ.get("CONTROLPC_BRAIN_DIR")
    if env:
        return env
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        home = os.path.expanduser("~")
        if os.name == "nt":
            base = os.path.join(home, "AppData", "Local")
        else:
            base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "ControlPC")


def config_dir() -> str:
    return os.path.join(brain_dir(), "config")


def state_dir() -> str:
    return os.path.join(brain_dir(), "state")


def logs_dir() -> str:
    return os.path.join(brain_dir(), "logs")


def cache_dir() -> str:
    return os.path.join(brain_dir(), "cache")


def screenshots_dir() -> str:
    return os.path.join(cache_dir(), "screenshots")


def run_dir() -> str:
    return os.path.join(brain_dir(), "run")


def memory_dir() -> str:
    return os.path.join(brain_dir(), "memory")


def journal_dir() -> str:
    return os.path.join(memory_dir(), "journal")


def config_file(name: str) -> str:
    """Return the active config path inside the brain, lazily seeding it from the
    shipped default in <repo>/config on first access."""
    active = os.path.join(config_dir(), name)
    if not os.path.exists(active):
        shipped = os.path.join(SHIPPED_CONFIG_DIR, name)
        if os.path.exists(shipped):
            try:
                os.makedirs(config_dir(), exist_ok=True)
                shutil.copy2(shipped, active)
            except Exception as e:
                logger.warning(f"Could not seed config '{name}': {e}")
    return active


def _safe_copy(src: str, dst: str):
    try:
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            logger.info(f"Migrated into brain: {src} -> {dst}")
    except Exception as e:
        logger.warning(f"Migration copy failed {src} -> {dst}: {e}")


def _migrate_legacy():
    """One-time, idempotent move of pre-brain scattered data into the brain.
    Copies (not deletes) to preserve data + the audit hash chain integrity."""
    # 0. Previous in-repo brain (old default <repo>/.controlpc) -> new brain.
    #    Runs first so the freshest data wins (_safe_copy never overwrites).
    legacy_brain = os.path.join(REPO_ROOT, ".controlpc")
    if os.path.isdir(legacy_brain) and os.path.abspath(legacy_brain) != os.path.abspath(brain_dir()):
        for sub in ("state", "config", "logs", "run"):
            src_sub = os.path.join(legacy_brain, sub)
            if os.path.isdir(src_sub):
                try:
                    for f in os.listdir(src_sub):
                        _safe_copy(os.path.join(src_sub, f), os.path.join(brain_dir(), sub, f))
                except Exception:
                    pass

    db_old = os.path.join(REPO_ROOT, "backend", "app", "database")
    _safe_copy(os.path.join(db_old, "history.db"), os.path.join(state_dir(), "history.db"))
    _safe_copy(os.path.join(db_old, "knowledge_base.json"), os.path.join(state_dir(), "knowledge_base.json"))
    _safe_copy(os.path.join(SHIPPED_CONFIG_DIR, "model_settings.json"), os.path.join(config_dir(), "model_settings.json"))
    _safe_copy(os.path.join(WORKSPACE_DIR, "temp", "current_draft.json"), os.path.join(run_dir(), "email_draft.json"))
    _safe_copy(os.path.join(WORKSPACE_DIR, "temp", "current_message_draft.json"), os.path.join(run_dir(), "message_draft.json"))

    # Rotating logs
    old_logs = os.path.join(REPO_ROOT, "backend", "logs")
    if os.path.isdir(old_logs):
        try:
            for f in os.listdir(old_logs):
                if f.startswith("controlpc.log"):
                    _safe_copy(os.path.join(old_logs, f), os.path.join(logs_dir(), f))
        except Exception:
            pass

    # Active config copies (defaults shipped in <repo>/config)
    for name in _SHIPPED_CONFIG_FILES:
        _safe_copy(os.path.join(SHIPPED_CONFIG_DIR, name), os.path.join(config_dir(), name))

    # Knowledge base working copy: prefer migrated, else seed.
    kb = os.path.join(state_dir(), "knowledge_base.json")
    if not os.path.exists(kb):
        _safe_copy(os.path.join(SHIPPED_CONFIG_DIR, "knowledge_base.seed.json"), kb)


_INITIALIZED = False


def ensure_brain() -> str:
    """Create the brain directory tree (idempotent) and run first-run migration."""
    global _INITIALIZED
    if _INITIALIZED:
        return brain_dir()
    brain_dirs = (brain_dir(), config_dir(), state_dir(), logs_dir(), cache_dir(),
                  screenshots_dir(), run_dir(), memory_dir(), journal_dir())
    # User-facing workspace dirs (outside the brain) — auto-created too so a fresh
    # install can write reports/outputs without any manual folder setup.
    workspace_dirs = (
        WORKSPACE_DIR,
        os.path.join(WORKSPACE_DIR, "input"),
        os.path.join(WORKSPACE_DIR, "output"),
        os.path.join(WORKSPACE_DIR, "templates"),
    )
    for d in brain_dirs + workspace_dirs:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            logger.error(f"Could not create dir {d}: {e}")

    manifest = os.path.join(brain_dir(), "brain.json")
    if not os.path.exists(manifest):
        _migrate_legacy()
        try:
            with open(manifest, "w", encoding="utf-8") as f:
                json.dump({
                    "app": "CONTROLPC",
                    "schema_version": 1,
                    "created": time.time(),
                    "layout": ["config", "state", "logs", "cache", "run"],
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Could not write brain.json: {e}")

    _INITIALIZED = True
    return brain_dir()


# Initialise on import so any module that imports paths gets a ready brain.
ensure_brain()
