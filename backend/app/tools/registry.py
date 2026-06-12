import logging
from typing import Dict, Any, Callable

from tools import file_tool, document_tool, email_tool, messaging_tool, shell_tool

logger = logging.getLogger("tools.registry")

# Map tool names to python functions
TOOL_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {
    "file.search": file_tool.search_files,
    "file.open": file_tool.open_file,
    "file.copy": file_tool.copy_file,
    "file.rename": file_tool.rename_file,
    "file.create_folder": file_tool.create_folder,
    "document.create_docx": document_tool.create_docx,
    "document.read_text": document_tool.read_text,
    "document.summarize": document_tool.summarize_text,
    "email.create_draft": email_tool.create_draft,
    "email.send": email_tool.send_email,
    "email.validate_recipient": email_tool.validate_recipient,
    "email.attach_file": email_tool.attach_file_to_draft,
    "email.list_recent": email_tool.list_recent,
    "message.create_draft": messaging_tool.create_draft,
    "message.send": messaging_tool.send_message,
    "message.find_contact": messaging_tool.find_contact,
    "message.open_thread": messaging_tool.open_thread,
    "shell.run": shell_tool.run_command
}

def execute_tool_call(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a tool call by looking up the name in the registry.
    """
    tool_name_lower = tool_name.lower().strip()
    if tool_name_lower not in TOOL_REGISTRY:
        logger.error(f"Tool not found in registry: {tool_name}")
        return {"success": False, "error": f"Tool '{tool_name}' not found in registry."}
        
    try:
        logger.info(f"Executing tool '{tool_name_lower}' with params: {params}")
        func = TOOL_REGISTRY[tool_name_lower]
        
        # Match python parameters
        # If parameters match exactly, call it. We can inspect the function signature if needed,
        # but since our tool signatures are clean, we can just unpack **params.
        # However, to avoid TypeError on extra arguments from planner, we can filter params.
        import inspect
        sig = inspect.signature(func)
        filtered_params = {}
        for param_name, param in sig.parameters.items():
            if param.kind in [inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY]:
                if param_name in params:
                    filtered_params[param_name] = params[param_name]
                elif param.default == inspect.Parameter.empty:
                    # Missing required parameter, but let's let python raise or set to None
                    pass
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                filtered_params.update(params)
                break
                
        res = func(**filtered_params)
        return res
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name_lower}': {e}")
        return {"success": False, "error": str(e)}
