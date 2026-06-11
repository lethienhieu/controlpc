import os
import logging
import multiprocessing
from typing import Dict, Any, Optional

logger = logging.getLogger("llm")

# Try importing llama-cpp
try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    LLAMA_AVAILABLE = False
    logger.warning("llama-cpp-python is not installed or available.")

# Auto-detect optimal thread count (use all physical cores)
_CPU_CORES = max(4, multiprocessing.cpu_count())

class LocalLLM:
    def __init__(self):
        self.model: Optional[Llama] = None
        self.model_path: str = ""
        
        # Scan for existing downloaded Gemma-4 model in multiple locations to prevent re-downloads
        paths_to_check = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "gemma-4-E4B-it-Q4_K_M.gguf"),
            os.path.join("C:\\Users\\admin\\.gemini\\antigravity\\scratch\\nova-os-agent\\backend\\models", "gemma-4-E4B-it-Q4_K_M.gguf")
        ]
        
        for path in paths_to_check:
            if os.path.exists(path):
                self.model_path = path
                logger.info(f"Detected Gemma 4 GGUF model at: {path}")
                break

    def load_model(self) -> bool:
        """Loads the GGUF model lazily."""
        if not LLAMA_AVAILABLE:
            logger.error("Cannot load model because llama-cpp-python is not installed.")
            return False
            
        if self.model is not None:
            return True
            
        if not self.model_path or not os.path.exists(self.model_path):
            logger.error("No valid GGUF model path found.")
            return False
            
        try:
            logger.info(f"Loading local GGUF model: {self.model_path} (threads={_CPU_CORES})...")
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=1024,        # Reduced context: enough for ReAct steps, faster KV-cache
                n_threads=_CPU_CORES,  # Use all available CPU cores
                n_batch=512,       # Larger prompt batch → faster prefill
                n_gpu_layers=0,    # CPU-only; set to -1 if you have compatible GPU
                use_mmap=True,     # Memory-map model file → faster cold load
                use_mlock=False,   # Don't pin RAM; let OS manage
                verbose=False
            )
            logger.info(f"Local LLM loaded OK (threads={_CPU_CORES}, ctx=1024, batch=512).")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.2, stop: Optional[list] = None) -> str:
        """Inference call to the GGUF model."""
        if not self.load_model() or self.model is None:
            raise RuntimeError("Model is not loaded.")
            
        try:
            response = self.model(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop or ["<end_of_turn>"]
            )
            return response["choices"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Inference generation failed: {e}")
            raise e
