import os
import sys
from fastapi.testclient import TestClient

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from backend.app.main import app
import desktop

def test_rotating_logs_exist():
    print("[TEST] Verifying rotating log files configuration...")
    log_file_path = os.path.join(BASE_DIR, "backend", "logs", "controlpc.log")
    
    # Trigger a log call to ensure log file is created
    import logging
    logger = logging.getLogger("main")
    logger.info("Test packaging log entry")
    
    assert os.path.exists(log_file_path), f"Log file should be created at: {log_file_path}"
    print(" - Rotating log file verified: OK")

def test_settings_export_import():
    print("[TEST] Testing Settings Export & Import API endpoints...")
    client = TestClient(app)
    
    # 1. Export settings
    res_export = client.get("/api/settings/export")
    assert res_export.status_code == 200
    export_data = res_export.json()
    assert "config/permissions.json" in export_data
    assert "config/contacts.json" in export_data
    print(" - Settings Export assertion: OK")
    
    # 2. Import settings
    # Modify permissions slightly to check
    original_permissions = export_data["config/permissions.json"]
    modified_permissions = original_permissions.copy()
    modified_permissions["safety_settings"]["test_flag"] = "hello_world"
    
    payload = {
        "settings": {
            "config/permissions.json": modified_permissions
        }
    }
    
    res_import = client.post("/api/settings/import", json=payload)
    assert res_import.status_code == 200
    import_data = res_import.json()
    assert "config/permissions.json" in import_data["imported"]
    
    # Verify change reflected in permissions cache
    from policy.permissions import load_permissions
    perms = load_permissions()
    assert perms["safety_settings"].get("test_flag") == "hello_world"
    print(" - Settings Import & Cache reload assertion: OK")
    
    # 3. Restore original permissions
    restore_payload = {
        "settings": {
            "config/permissions.json": original_permissions
        }
    }
    client.post("/api/settings/import", json=restore_payload)
    print(" - Settings Restored: OK")

def test_health_check():
    print("[TEST] Verifying health check script run...")
    # desktop.perform_health_check shouldn't raise any exceptions
    desktop.perform_health_check()
    print(" - Health check run verified: OK")

if __name__ == "__main__":
    try:
        test_rotating_logs_exist()
        test_settings_export_import()
        test_health_check()
        print("\n[SUCCESS] Packaging and operation tests passed successfully!")
    except AssertionError as e:
        import traceback
        print(f"\n[FAILURE] Test assertion failed:")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Error occurred:")
        traceback.print_exc()
        sys.exit(1)
