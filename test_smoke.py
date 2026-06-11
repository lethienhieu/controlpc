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
    from backend.app.main import app
    from fastapi.testclient import TestClient
    print("[SMOKE TEST] Import successful!")
except Exception as e:
    print(f"[SMOKE TEST ERROR] Import failed: {e}")
    sys.exit(1)

def run_test():
    print("[SMOKE TEST] Initializing TestClient...")
    client = TestClient(app)
    
    print("[SMOKE TEST] GET /api/status...")
    response = client.get("/api/status")
    
    print(f"[SMOKE TEST] Response Status Code: {response.status_code}")
    print(f"[SMOKE TEST] Response Body: {json.dumps(response.json(), ensure_ascii=True)}")
    
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
    
    data = response.json()
    assert "status" in data, "Response body should contain 'status'"
    assert "logs" in data, "Response body should contain 'logs'"
    assert "pending_action" in data, "Response body should contain 'pending_action'"
    
    print("[SMOKE TEST SUCCESS] All checks passed successfully!")

if __name__ == "__main__":
    run_test()
