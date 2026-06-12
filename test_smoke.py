import os
import sys
import json

# Reconfigure stdout to use UTF-8 if possible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

try:
    print("[SMOKE TEST] Attempting to import FastAPI app...")
    # Importing main exercises the whole graph (executor, llm, planner, tools,
    # policy, integrations, database) — a real smoke test of the backend.
    import main
    print("[SMOKE TEST] Import successful!")
except Exception as e:
    print(f"[SMOKE TEST ERROR] Import failed: {e}")
    sys.exit(1)

def run_test():
    # Call the /api/status route handler directly. This validates the same
    # response contract without needing an HTTP test client (httpx), keeping
    # the smoke test dependency-free.
    print("[SMOKE TEST] Calling /api/status handler...")
    data = main.get_status()

    print(f"[SMOKE TEST] Response Body: {json.dumps(data, ensure_ascii=True, default=str)}")

    assert isinstance(data, dict), "Status handler should return a dict"
    assert "status" in data, "Response body should contain 'status'"
    assert "logs" in data, "Response body should contain 'logs'"
    assert "pending_action" in data, "Response body should contain 'pending_action'"
    assert "model_path" in data, "Response body should contain 'model_path'"

    print("[SMOKE TEST SUCCESS] All checks passed successfully!")

if __name__ == "__main__":
    run_test()
