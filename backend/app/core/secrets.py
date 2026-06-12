"""Secret storage for CONTROLPC.

Primary backend: the OS keyring (Windows Credential Manager via keyring's
WinVaultKeyring) — secrets are stored encrypted by Windows, not in plaintext
config files. Falls back to environment variables for headless/CI use.

Public names (logical secret keys):
  - "smtp_password"   (env fallback: CONTROLPC_SMTP_PASSWORD)
  - "telegram_token"  (env fallback: CONTROLPC_TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN)
"""
import os
import logging

logger = logging.getLogger("core.secrets")

SERVICE = "CONTROLPC"

# Extra env var aliases kept for backward compatibility with the old setup.
_ENV_ALIASES = {
    "smtp_password": ["CONTROLPC_SMTP_PASSWORD"],
    "telegram_token": ["CONTROLPC_TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN"],
}

try:
    import keyring
    _KEYRING_OK = True
except Exception as e:  # pragma: no cover
    _KEYRING_OK = False
    logger.warning(f"keyring unavailable, falling back to env vars only: {e}")


def backend_available() -> bool:
    """True if a real OS keyring backend is usable."""
    if not _KEYRING_OK:
        return False
    try:
        kr = keyring.get_keyring().__class__.__name__
        return "Fail" not in kr  # keyring.backends.fail.Keyring means no real store
    except Exception:
        return False


def _env_value(name: str) -> str:
    for env_name in _ENV_ALIASES.get(name, [f"CONTROLPC_{name.upper()}"]):
        v = os.environ.get(env_name)
        if v:
            return v
    return ""


def get_secret(name: str) -> str:
    """Return the secret value: keyring first, then env var. "" if absent."""
    if _KEYRING_OK:
        try:
            v = keyring.get_password(SERVICE, name)
            if v:
                return v
        except Exception as e:
            logger.warning(f"keyring read failed for '{name}': {e}")
    return _env_value(name)


def set_secret(name: str, value: str) -> bool:
    """Persist a secret into the OS keyring. Returns False if no real backend."""
    if not backend_available():
        logger.error("No OS keyring backend available to store secret.")
        return False
    try:
        keyring.set_password(SERVICE, name, value)
        return True
    except Exception as e:
        logger.error(f"keyring write failed for '{name}': {e}")
        return False


def delete_secret(name: str) -> bool:
    if not _KEYRING_OK:
        return False
    try:
        keyring.delete_password(SERVICE, name)
        return True
    except Exception:
        return False


def has_secret(name: str) -> bool:
    return bool(get_secret(name))
