import os
import sys

# Setup python path to import backend modules properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "backend", "app"))

from tools import file_tool, document_tool

# Portable workspace paths (resolve relative to this repo, not a hardcoded drive)
INPUT_DIR = os.path.join(BASE_DIR, "workspace", "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "workspace", "output")

def setup_test_files():
    print("[TEST SETUP] Creating test files in workspace...")
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(os.path.join(INPUT_DIR, "test_read.txt"), "w", encoding="utf-8") as f:
        f.write("CONTROLPC Test File.\nThis is a sample document for testing read and summarize.")
    print("[TEST SETUP] Done.")

def test_file_search():
    print("[TEST] Testing file.search...")
    # Search within allowed input folder
    res = file_tool.search_files("test_read", search_roots=[INPUT_DIR])
    assert res["success"], "Search should be successful"
    assert len(res["results"]) > 0, "Should find test_read.txt"
    assert res["results"][0]["name"] == "test_read.txt", f"Expected test_read.txt, got {res['results'][0]['name']}"
    
    # Search in blocked folder (should get skipped or filtered)
    res_blocked = file_tool.search_files("cmd.exe", search_roots=["C:\\Windows"])
    assert len(res_blocked["results"]) == 0, "Should block or return empty results for blocked dir C:\\Windows"
    print(" - file.search tests passed!")

def test_file_read_and_summarize():
    print("[TEST] Testing read_text and summarize_text...")
    filepath = os.path.join(INPUT_DIR, "test_read.txt")
    
    # Read text
    res_read = document_tool.read_text(filepath)
    assert res_read["success"], "Read should succeed"
    assert "CONTROLPC Test File" in res_read["content"]
    
    # Summarize text
    res_sum = document_tool.summarize_text(filepath)
    assert res_sum["success"], "Summarize should succeed"
    assert "File summary:" in res_sum["summary"]
    
    # Try reading blocked file
    res_blocked = document_tool.read_text("C:\\Windows\\System32\\cmd.exe")
    assert not res_blocked["success"], "Read blocked file should fail"
    assert "permission denied" in res_blocked["error"].lower()
    print(" - file read and summarize tests passed!")

def test_docx_creation():
    print("[TEST] Testing document.create_docx...")
    output_path = os.path.join(OUTPUT_DIR, "test_report.docx")
    
    # Remove existing if any
    if os.path.exists(output_path):
        os.remove(output_path)
        
    title = "Weekly work report"
    paragraphs = [
        "Completed the foundational setup for the CONTROLPC project.",
        "Successfully built the Policy Engine and Permission Engine.",
        "Integrated the file tool and document tool for risk control."
    ]
    
    res = document_tool.create_docx(output_path, title, paragraphs)
    assert res["success"], "Create docx should succeed"
    assert os.path.exists(output_path), "docx file should exist on disk"
    
    # Read it back using document_tool
    res_read = document_tool.read_text(output_path)
    assert res_read["success"], "Read docx back should succeed"
    assert "Weekly work report" in res_read["content"]
    assert "Successfully built the Policy Engine" in res_read["content"]
    
    # Try creating docx in blocked directory
    res_blocked = document_tool.create_docx("C:\\Windows\\evil_report.docx", "Title", ["Para"])
    assert not res_blocked["success"], "Create docx in blocked dir should fail"
    print(" - document.create_docx tests passed!")

if __name__ == "__main__":
    setup_test_files()
    try:
        test_file_search()
        test_file_read_and_summarize()
        test_docx_creation()
        print("\n[SUCCESS] All file and document tools tests passed successfully!")
    except AssertionError as e:
        print(f"\n[FAILURE] Tool test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error during testing: {e}")
        sys.exit(1)
