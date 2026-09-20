import os
import subprocess
import webbrowser
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]

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
def _get_calendar_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", CALENDAR_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", CALENDAR_SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def list_upcoming_events() -> str:
    """List the next 5 upcoming events from the user's Google Calendar."""
    try:
        service = _get_calendar_service()
        events_result = service.events().list(
            calendarId="primary",
            maxResults=5,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return "No upcoming events found."

        output = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            output.append(f"{start} - {event['summary']}")
        return "\n".join(output)
    except Exception as e:
        return f"Error listing events: {e}"


def create_calendar_event(summary: str, start_datetime: str, end_datetime: str) -> str:
    """Create a new event on the user's Google Calendar."""
    try:
        service = _get_calendar_service()
        event = {
            "summary": summary,
            "start": {"dateTime": start_datetime, "timeZone": "Asia/Dhaka"},
            "end": {"dateTime": end_datetime, "timeZone": "Asia/Dhaka"},
        }
        created_event = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event '{summary}' created successfully from {start_datetime} to {end_datetime}. Link: {created_event.get('htmlLink')}"
    except Exception as e:
        return f"Error creating event: {e}"