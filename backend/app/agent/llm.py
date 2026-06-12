import os
import json
import time
import socket
import logging
import threading
import subprocess
import atexit
from typing import Optional, List

import requests

from core import paths

logger = logging.getLogger("llm")

# Default GGUF model name (fallback). gemma-4-E4B (Q4_K_M ~4.97GB) fits entirely
# in 8GB VRAM. The active model can be overridden via env / model_settings.json,
# so any chat GGUF (e.g. Qwen3) works — the chat template comes from the GGUF.
MODEL_FILENAME = "gemma-4-E4B-it-Q4_K_M.gguf"


def _repo_root() -> str:
    # backend/app/agent/llm.py -> repo root is 4 levels up
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


_MODEL_CONFIG_PATH = os.path.join(paths.config_dir(), "model_settings.json")


def load_model_config() -> dict:
    """Optional runtime model selection: {"model_path": "...", "context": 8192}."""
    try:
        if os.path.exists(_MODEL_CONFIG_PATH):
            with open(_MODEL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read model_settings.json: {e}")
    return {}


def save_model_config(cfg: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_MODEL_CONFIG_PATH), exist_ok=True)
        with open(_MODEL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Could not write model_settings.json: {e}")
        return False


# Extra known locations that already ship a CUDA llama.cpp build + the model.
# These let CONTROLPC reuse an existing GPU setup without copying ~6GB of
# binaries/weights into this repo. Override with env vars when needed.
_FALLBACK_ROOTS = [
    r"E:\THBIM-CODE\2025\WH x AI",
]


class LocalLLM:
    """
    GPU-backed local LLM served by a bundled llama.cpp ``llama-server.exe``
    subprocess running gemma-4-E4B with full GPU offload (``-ngl 99``).

    This replaces the previous in-process ``llama-cpp-python`` (CPU only)
    backend. The native CUDA server runs every layer on the GPU (RTX 5060 /
    Blackwell) for ~10-20x faster inference, and avoids the Python 3.14 +
    CUDA-toolkit build problems that block GPU ``llama-cpp-python`` wheels.

    The public surface is kept identical to the old class so callers
    (executor / planner / classifier / main.py) need no changes:
      * ``model_path``  - resolved path to the GGUF file (or "" if missing)
      * ``generate(prompt, max_tokens, temperature, stop)`` -> str
      * ``load_model()`` -> bool

    The subprocess is shared across all LocalLLM instances (class-level) and is
    started lazily on first ``generate``/``load_model`` call, then reused.
    """

    _proc: Optional[subprocess.Popen] = None
    _base_url: str = ""
    # Reentrant: _ensure_server() holds this lock and may itself call
    # stop_server() (on health timeout); stop_server() now also takes the lock,
    # so it must be re-entrant to avoid a same-thread deadlock. It also serialises
    # an external stop_server() (e.g. set_model / warmup) against a concurrent
    # _ensure_server(), preventing the _base_url/_proc data race.
    _lock = threading.RLock()
    _atexit_registered = False

    def __init__(self):
        self.server_exe = self._find_server_exe()
        self.model_path = self._find_model_file()

    # ── Path resolution ───────────────────────────────────────────────────
    def _search_roots(self) -> List[str]:
        return [_repo_root()] + _FALLBACK_ROOTS

    def _find_server_exe(self) -> str:
        # 1. CONTROLPC's own explicit override.
        env = os.environ.get("CONTROLPC_LLAMA_SERVER")
        if env and os.path.exists(env):
            return env
        # 2. Bundled local copy (fully self-contained, no shared deps).
        local = os.path.join(_repo_root(), "llama", "llama-server.exe")
        if os.path.exists(local):
            return local
        # 3. Another app's shared env var, then the known fallback locations.
        env2 = os.environ.get("WOHHUP_LLAMA_SERVER")
        if env2 and os.path.exists(env2):
            return env2
        for root in _FALLBACK_ROOTS:
            candidate = os.path.join(root, "llama", "llama-server.exe")
            if os.path.exists(candidate):
                return candidate
        return ""

    def _find_model_file(self) -> str:
        # 1. CONTROLPC's own explicit override.
        env = os.environ.get("CONTROLPC_LLAMA_MODEL")
        if env and os.path.exists(env):
            return env
        # 2. Runtime selection via model_settings.json (set from the UI).
        cfg_path = load_model_config().get("model_path", "")
        if cfg_path and os.path.exists(cfg_path):
            return cfg_path
        # 3. Another app's shared env var, then the default bundled model.
        env2 = os.environ.get("WOHHUP_LLAMA_MODEL")
        if env2 and os.path.exists(env2):
            return env2
        for root in self._search_roots():
            candidate = os.path.join(root, "models", MODEL_FILENAME)
            if os.path.exists(candidate):
                return candidate
        return ""

    def reload_model_config(self) -> str:
        """Re-resolve the active model path (after model_settings.json changed)."""
        self.model_path = self._find_model_file()
        return self.model_path

    # ── Subprocess lifecycle ──────────────────────────────────────────────
    @staticmethod
    def _pick_free_port() -> int:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        finally:
            s.close()

    def _ensure_server(self) -> bool:
        """Start the llama-server subprocess if not already running. Returns
        True once /health responds OK."""
        with LocalLLM._lock:
            if LocalLLM._proc is not None and LocalLLM._proc.poll() is None and LocalLLM._base_url:
                return True

            if not self.server_exe or not self.model_path:
                logger.error(
                    "Cannot start GPU model server: missing components "
                    f"(llama-server.exe={self.server_exe!r}, model={self.model_path!r}). "
                    "Set CONTROLPC_LLAMA_SERVER / CONTROLPC_LLAMA_MODEL or drop them "
                    "into <repo>\\llama and <repo>\\models."
                )
                return False

            port = self._pick_free_port()
            threads = str(max(4, (os.cpu_count() or 8) // 2))
            ctx = str(load_model_config().get("context", 8192))
            args = [
                self.server_exe,
                "-m", self.model_path,
                "--host", "127.0.0.1",
                "--port", str(port),
                "-ngl", "99",         # full GPU offload (all layers on GPU)
                "-c", ctx,            # context window (configurable per model size)
                "-fa", "on",          # flash-attention: smaller KV cache → larger models fit 8GB
                "--threads", threads,
                "--log-disable",
            ]

            creationflags = 0
            if os.name == "nt":
                creationflags = 0x08000000  # CREATE_NO_WINDOW

            try:
                logger.info(f"Starting GPU llama-server: {self.server_exe} (port {port}, -ngl 99)")
                LocalLLM._proc = subprocess.Popen(
                    args,
                    cwd=os.path.dirname(self.server_exe),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            except Exception as e:
                logger.error(f"Failed to launch llama-server: {e}")
                LocalLLM._proc = None
                return False

            LocalLLM._base_url = f"http://127.0.0.1:{port}"
            if not LocalLLM._atexit_registered:
                atexit.register(LocalLLM.stop_server)
                LocalLLM._atexit_registered = True

            # Cold start: 4.97GB GGUF mmap + GPU upload typically 10-30s.
            deadline = time.time() + 90
            while time.time() < deadline:
                if LocalLLM._proc.poll() is not None:
                    logger.error("llama-server exited during startup.")
                    LocalLLM._proc = None
                    LocalLLM._base_url = ""
                    return False
                try:
                    r = requests.get(LocalLLM._base_url + "/health", timeout=2)
                    if r.status_code == 200:
                        logger.info(f"GPU llama-server ready at {LocalLLM._base_url}")
                        return True
                except Exception:
                    pass
                time.sleep(0.5)

            logger.error("llama-server health check timed out after 90s.")
            LocalLLM.stop_server()
            return False

    @classmethod
    def stop_server(cls):
        with cls._lock:
            p = cls._proc
            cls._proc = None
            cls._base_url = ""
            if p is not None and p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=3)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass

    def load_model(self) -> bool:
        return self._ensure_server()

    # ── Inference ─────────────────────────────────────────────────────────
    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.2,
                 stop: Optional[list] = None, json_schema: Optional[dict] = None,
                 system: Optional[str] = None) -> str:
        """Chat completion via llama.cpp ``/v1/chat/completions``.

        Model-agnostic: llama-server applies the model's OWN chat template (read
        from the GGUF), so switching between Gemma / Qwen / etc. just works — no
        hardcoded turn tokens. Chain-of-thought is disabled so short answers /
        JSON aren't preceded by <think> tokens. ``json_schema`` constrains the
        output to valid JSON (used by the planner)."""
        if not self._ensure_server():
            raise RuntimeError(
                "Local GPU model server is not available (llama-server.exe or GGUF model missing)."
            )
        # Capture the URL into a local so a concurrent stop_server()/set_model()
        # that clears the class-level _base_url can't turn this into a MissingSchema.
        base = LocalLLM._base_url
        if not base:
            raise RuntimeError("Local GPU model server is not available.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "controlpc",  # ignored: llama-server serves a single model
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            # Disable thinking for models that read this kwarg (Qwen3, Gemma).
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if stop:
            payload["stop"] = stop
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "controlpc_action", "schema": json_schema, "strict": True},
            }

        try:
            r = requests.post(base + "/v1/chat/completions", json=payload, timeout=180)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            return ((choices[0].get("message") or {}).get("content") or "").strip()
        except Exception as e:
            logger.error(f"Inference request failed: {e}")
            raise

    def generate_stream(self, prompt: str, max_tokens: int = 256, temperature: float = 0.2,
                        system: Optional[str] = None):
        """Like generate(), but yields content deltas as they arrive (OpenAI-style
        SSE from llama-server with stream=true). Used for smooth chat replies."""
        if not self._ensure_server():
            raise RuntimeError(
                "Local GPU model server is not available (llama-server.exe or GGUF model missing)."
            )
        base = LocalLLM._base_url
        if not base:
            raise RuntimeError("Local GPU model server is not available.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "controlpc",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        with requests.post(base + "/v1/chat/completions", json=payload,
                           stream=True, timeout=300) as r:
            r.raise_for_status()
            # llama-server streams UTF-8, but `requests` defaults a text/event-stream
            # body to latin-1 — which mangles Vietnamese ("Chào" -> "ChÃ o"). Force
            # UTF-8 so iter_lines(decode_unicode=True) decodes correctly.
            r.encoding = "utf-8"
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except Exception:
                    continue
