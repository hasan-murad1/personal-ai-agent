import os
import subprocess
import webbrowser
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SANDBOX_DIR = "automation_sandbox"

os.makedirs(SANDBOX_DIR, exist_ok=True)

ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
}

AGENT_EMAIL = os.environ.get("AGENT_EMAIL")
AGENT_EMAIL_PASSWORD = os.environ.get("AGENT_EMAIL_PASSWORD")
ALLOWED_RECIPIENT = "hmefat28@gmail.com"


def _safe_sandbox_path(relative_path: str) -> str:
    """Resolve a path to an absolute location inside the sandbox, blocking any attempt to escape it."""
    full_path = os.path.abspath(os.path.join(SANDBOX_DIR, relative_path))
    sandbox_abs = os.path.abspath(SANDBOX_DIR)

    if not full_path.startswith(sandbox_abs):
        raise ValueError("Access outside the automation sandbox is not allowed.")

    return full_path


def open_application(app_name: str) -> str:
    """Open an application, restricted to a fixed allow-list. Rejects anything not explicitly permitted."""
    app_key = app_name.strip().lower()

    if app_key not in ALLOWED_APPS:
        return f"Error: '{app_name}' is not allowed. Allowed apps: {list(ALLOWED_APPS.keys())}"

    try:
        subprocess.Popen(ALLOWED_APPS[app_key])
        return f"Opened {app_name}."
    except Exception as e:
        return f"Error opening {app_name}: {e}"


def list_sandbox_contents(subfolder: str = "") -> str:
    """List files and folders inside the automation sandbox, or a subfolder within it."""
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
    """Create a new folder inside the automation sandbox."""
    try:
        path = _safe_sandbox_path(folder_name)
        os.makedirs(path, exist_ok=True)
        return f"Folder '{folder_name}' created in sandbox."
    except ValueError as e:
        return f"Error: {e}"


def open_sandbox_folder_in_explorer() -> str:
    """Open the automation sandbox folder in Windows File Explorer."""
    try:
        sandbox_abs = os.path.abspath(SANDBOX_DIR)
        os.startfile(sandbox_abs)
        return "Opened the sandbox folder in File Explorer."
    except Exception as e:
        return f"Error opening folder: {e}"


def open_youtube_search(query: str) -> str:
    """Open a YouTube search results page in the default browser for the given query."""
    search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    webbrowser.open(search_url)
    return f"Opened YouTube search for '{query}' in your browser."


def send_email(subject: str, body: str) -> str:
    """Send an email through the agent's dedicated test account, restricted to a single pre-approved recipient."""
    if not AGENT_EMAIL or not AGENT_EMAIL_PASSWORD:
        return "Error: email credentials are not configured."

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = AGENT_EMAIL
        msg["To"] = ALLOWED_RECIPIENT

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(AGENT_EMAIL, AGENT_EMAIL_PASSWORD)
            server.send_message(msg)

        return f"Email sent to {ALLOWED_RECIPIENT} with subject '{subject}' and body: {body}"
    except Exception as e:
        return f"Error sending email: {e}"