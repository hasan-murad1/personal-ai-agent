import os
import subprocess

SANDBOX_DIR = "automation_sandbox"

os.makedirs(SANDBOX_DIR, exist_ok=True)

ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
}


def _safe_sandbox_path(relative_path: str) -> str:
    full_path = os.path.abspath(os.path.join(SANDBOX_DIR, relative_path))
    sandbox_abs = os.path.abspath(SANDBOX_DIR)

    if not full_path.startswith(sandbox_abs):
        raise ValueError("Access outside the automation sandbox is not allowed.")

    return full_path


def open_application(app_name: str) -> str:
    app_key = app_name.strip().lower()

    if app_key not in ALLOWED_APPS:
        return f"Error: '{app_name}' is not allowed. Allowed apps: {list(ALLOWED_APPS.keys())}"

    try:
        subprocess.Popen(ALLOWED_APPS[app_key])
        return f"Opened {app_name}."
    except Exception as e:
        return f"Error opening {app_name}: {e}"


def list_sandbox_contents(subfolder: str = "") -> str:
    try:
        path = _safe_sandbox_path(subfolder)
        if not os.path.exists(path):
            return f"Error: '{subfolder}' does not exist in the sandbox."
        items = os.listdir(path)
        if not items:
            return "This sandbox folder is empty."
        return "\n".join(items)
    except ValueError as e:
        return f"Error: {e}"


def create_sandbox_folder(folder_name: str) -> str:
    try:
        path = _safe_sandbox_path(folder_name)
        os.makedirs(path, exist_ok=True)
        return f"Folder '{folder_name}' created in sandbox."
    except ValueError as e:
        return f"Error: {e}"


def open_sandbox_folder_in_explorer() -> str:
    try:
        sandbox_abs = os.path.abspath(SANDBOX_DIR)
        os.startfile(sandbox_abs)
        return "Opened the sandbox folder in File Explorer."
    except Exception as e:
        return f"Error opening folder: {e}"