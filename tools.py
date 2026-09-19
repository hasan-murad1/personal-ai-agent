import os
import datetime
import ast
import operator
import rag
import automation

WORKSPACE_DIR = "agent_workspace"

os.makedirs(WORKSPACE_DIR, exist_ok=True)


def _safe_path(filename: str) -> str:
    """Resolve a filename to an absolute path inside the workspace, blocking any attempt to escape it."""
    full_path = os.path.abspath(os.path.join(WORKSPACE_DIR, filename))
    workspace_abs = os.path.abspath(WORKSPACE_DIR)

    if not full_path.startswith(workspace_abs):
        raise ValueError("Access outside the workspace folder is not allowed.")

    return full_path


def write_file(filename: str, content: str) -> str:
    """Create or overwrite a file inside the workspace. Returns the actual content written, to prevent the model from hallucinating a different summary."""
    try:
        path = _safe_path(filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File '{filename}' written successfully. Actual content saved: {content}"
    except Exception as e:
        return f"Error writing file: {e}"


def delete_file(filename: str) -> str:
    """Delete a file from the workspace, if it exists."""
    try:
        path = _safe_path(filename)
        if not os.path.exists(path):
            return f"Error: file '{filename}' does not exist."
        os.remove(path)
        return f"File '{filename}' deleted successfully."
    except Exception as e:
        return f"Error deleting file: {e}"


def list_workspace_files() -> str:
    """List all files currently in the workspace folder."""
    files = os.listdir(WORKSPACE_DIR)
    if not files:
        return "The workspace folder is empty."
    return "\n".join(files)


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(node):
    """Recursively evaluate a parsed math expression, allowing only a fixed set of safe operators (no eval())."""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in ALLOWED_OPERATORS:
            raise ValueError("Unsupported operation")
        return ALLOWED_OPERATORS[op_type](_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in ALLOWED_OPERATORS:
            raise ValueError("Unsupported operation")
        return ALLOWED_OPERATORS[op_type](_safe_eval(node.operand))
    else:
        raise ValueError("Unsupported expression")


def calculator(expression: str) -> str:
    """Safely evaluate a basic math expression without using Python's eval()."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)
    except Exception as e:
        return f"Error: could not calculate ({e})"


def get_current_datetime() -> str:
    """Return the current date and time as a formatted string."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic math expression (add, subtract, multiply, divide, power).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression, e.g. '2 + 2 * 3'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current date and time.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search the user's personal documents (PDFs, DOCX files) for relevant information. Use this when the user asks a question that might be answered by their uploaded documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query or question to look up in the documents."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a text file inside the agent's workspace folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the file, e.g. 'notes.txt'"},
                    "content": {"type": "string", "description": "Text content to write into the file"}
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file from the agent's workspace folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the file to delete"}
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_workspace_files",
            "description": "List all files currently in the agent's workspace folder.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open an allowed application (notepad or calculator).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Name of the app to open: 'notepad' or 'calculator'"}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_sandbox_contents",
            "description": "List files and folders inside the automation sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subfolder": {"type": "string", "description": "Optional subfolder path within the sandbox, leave empty for root"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_sandbox_folder",
            "description": "Create a new folder inside the automation sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string", "description": "Name of the new folder to create"}
                },
                "required": ["folder_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_sandbox_folder_in_explorer",
            "description": "Open the automation sandbox folder in Windows File Explorer so the user can see its contents.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "open_youtube_search",
            "description": "Open YouTube search results in the browser for a given query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for on YouTube"}
                },
                "required": ["query"]
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to the pre-approved recipient. Use only when the user explicitly asks to send an email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body content"}
                },
                "required": ["subject", "body"]
            }
        }
    }
]

AVAILABLE_FUNCTIONS = {
    "calculator": calculator,
    "get_current_datetime": get_current_datetime,
    "search_documents": rag.search_documents,
    "write_file": write_file,
    "delete_file": delete_file,
    "list_workspace_files": list_workspace_files,
    "open_application": automation.open_application,
    "list_sandbox_contents": automation.list_sandbox_contents,
    "create_sandbox_folder": automation.create_sandbox_folder,
    "open_sandbox_folder_in_explorer": automation.open_sandbox_folder_in_explorer,
    "open_youtube_search": automation.open_youtube_search,
    "send_email": automation.send_email,
}

RISKY_TOOLS = {
    "write_file": True,
    "delete_file": True,
    "open_application": True,
    "create_sandbox_folder": True,
    "send_email": True,
}
