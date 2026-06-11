import os
import shutil
import logging
from typing import List, Dict, Any

from policy import permissions

logger = logging.getLogger("tools.file_tool")

def search_files(filename: str, search_roots: List[str] = None) -> Dict[str, Any]:
    """
    Searches for files matching filename within allowed directories.
    """
    if search_roots is None:
        # Load from permissions config
        config = permissions.load_permissions()
        search_roots = config.get("file_permissions", {}).get("allowed_read_dirs", [])
        
    found_files = []
    
    for root_dir in search_roots:
        # Check permission before scanning
        if not permissions.is_path_in_dirs(root_dir, permissions.load_permissions().get("file_permissions", {}).get("allowed_read_dirs", [])):
            logger.warning(f"Search skipped directory due to permissions: {root_dir}")
            continue
            
        if not os.path.exists(root_dir):
            continue
            
        try:
            for root, _, files in os.walk(root_dir):
                # Check if current directory path is blocked
                if permissions.is_path_in_dirs(root, permissions.load_permissions().get("file_permissions", {}).get("blocked_dirs", [])):
                    continue
                    
                for file in files:
                    if filename.lower() in file.lower():
                        full_path = os.path.join(root, file)
                        found_files.append({
                            "name": file,
                            "path": full_path,
                            "size_bytes": os.path.getsize(full_path) if os.path.exists(full_path) else 0,
                            "modified_time": os.path.getmtime(full_path) if os.path.exists(full_path) else 0.0
                        })
                        if len(found_files) >= 15:  # Cap at 15 results
                            break
                if len(found_files) >= 15:
                    break
        except Exception as e:
            logger.error(f"Error walking directory {root_dir}: {e}")
            
    return {"success": True, "results": found_files}

def open_file(filepath: str) -> Dict[str, Any]:
    """
    Opens a file using Windows default application association.
    """
    if not filepath:
        return {"success": False, "error": "No file path provided."}
        
    # Second-line safety check
    if not permissions.check_file_read_permission(filepath):
        return {"success": False, "error": f"Read permission denied for path: {filepath}"}
        
    if not os.path.exists(filepath):
        return {"success": False, "error": f"File not found: {filepath}"}
        
    try:
        norm_path = os.path.normpath(os.path.abspath(filepath))
        logger.info(f"Opening file natively: {norm_path}")
        os.startfile(norm_path)
        return {"success": True, "message": f"Successfully opened file: {norm_path}"}
    except Exception as e:
        logger.error(f"Failed to open file {filepath}: {e}")
        return {"success": False, "error": str(e)}

def copy_file(src: str, dest: str) -> Dict[str, Any]:
    """
    Copies a file from source to destination path.
    """
    if not src or not dest:
        return {"success": False, "error": "Source or destination path is missing."}
        
    # Permission checks
    if not permissions.check_file_read_permission(src):
        return {"success": False, "error": f"Read permission denied for source path: {src}"}
    if not permissions.check_file_write_permission(dest):
        return {"success": False, "error": f"Write permission denied for destination path: {dest}"}
        
    if not os.path.exists(src):
        return {"success": False, "error": f"Source file not found: {src}"}
        
    try:
        src_norm = os.path.normpath(os.path.abspath(src))
        dest_norm = os.path.normpath(os.path.abspath(dest))
        
        # Ensure destination directory exists
        dest_dir = os.path.dirname(dest_norm)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            
        shutil.copy2(src_norm, dest_norm)
        logger.info(f"Copied file from {src_norm} to {dest_norm}")
        return {"success": True, "message": f"Copied file to: {dest_norm}"}
    except Exception as e:
        logger.error(f"Failed to copy file from {src} to {dest}: {e}")
        return {"success": False, "error": str(e)}

def rename_file(src: str, dest: str) -> Dict[str, Any]:
    """
    Renames/Moves a file or directory.
    """
    if not src or not dest:
        return {"success": False, "error": "Source or destination path is missing."}
        
    # Permission checks
    if not permissions.check_file_read_permission(src) or not permissions.check_file_write_permission(src):
        return {"success": False, "error": f"Permission denied for source path: {src}"}
    if not permissions.check_file_write_permission(dest):
        return {"success": False, "error": f"Write permission denied for destination path: {dest}"}
        
    if not os.path.exists(src):
        return {"success": False, "error": f"Source path not found: {src}"}
        
    try:
        src_norm = os.path.normpath(os.path.abspath(src))
        dest_norm = os.path.normpath(os.path.abspath(dest))
        
        os.rename(src_norm, dest_norm)
        logger.info(f"Renamed {src_norm} to {dest_norm}")
        return {"success": True, "message": f"Renamed path to: {dest_norm}"}
    except Exception as e:
        logger.error(f"Failed to rename {src} to {dest}: {e}")
        return {"success": False, "error": str(e)}

def create_folder(dirpath: str) -> Dict[str, Any]:
    """
    Creates a new directory.
    """
    if not dirpath:
        return {"success": False, "error": "No directory path provided."}
        
    # Permission check
    if not permissions.check_file_write_permission(dirpath):
        return {"success": False, "error": f"Write permission denied for path: {dirpath}"}
        
    try:
        norm_path = os.path.normpath(os.path.abspath(dirpath))
        os.makedirs(norm_path, exist_ok=True)
        logger.info(f"Created folder: {norm_path}")
        return {"success": True, "message": f"Successfully created folder: {norm_path}"}
    except Exception as e:
        logger.error(f"Failed to create folder {dirpath}: {e}")
        return {"success": False, "error": str(e)}
