import os
import subprocess
import webbrowser
import smtplib
import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from safe_paths import resolve_inside

load_dotenv()

SANDBOX_DIR = "automation_sandbox"
os.makedirs(SANDBOX_DIR, exist_ok=True)

ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
}

AGENT_EMAIL = os.environ.get("AGENT_EMAIL")
AGENT_EMAIL_PASSWORD = os.environ.get("AGENT_EMAIL_PASSWORD")
# The only address the agent may email. Kept in .env so it never appears in the public repository.
ALLOWED_RECIPIENT = os.environ.get("ALLOWED_RECIPIENT")

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.json"
CALENDAR_SIGN_IN_MESSAGE = (
    "Google Calendar sign-in is needed. Tell the user to stop the agent and run "
    "'python calendar_test.py' once in the terminal, then restart the agent."
)


def _now_rfc3339() -> str:
    """Return the current time in the RFC 3339 format the Calendar API expects for timeMin."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class CalendarAuthError(Exception):
    """Raised when the calendar token is missing or can no longer be refreshed without a browser sign-in."""


def _mask_email(address: str) -> str:
    """Hide most of an email address (yourname@gmail.com -> yo***@gmail.com).

    Tool results go to the LLM provider, the action log and the screen, so the full address never appears there.
    """
    if not address or "@" not in address:
        return "the pre-approved recipient"
    local, domain = address.split("@", 1)
    visible = 2 if len(local) > 4 else 1  # never reveal most of a short name
    return f"{local[:visible]}***@{domain}"


def _safe_sandbox_path(relative_path: str) -> str:
    """Resolve a path to an absolute location inside the sandbox, blocking any attempt to escape it."""
    return resolve_inside(SANDBOX_DIR, relative_path)


def open_application(app_name: str) -> str:
    """Open an application, restricted to a fixed allow-list."""
    app_key = app_name.strip().lower()
    if app_key not in ALLOWED_APPS:
        return f"Error: '{app_name}' is not allowed. Allowed apps: {list(ALLOWED_APPS.keys())}"
    try:
        subprocess.Popen(ALLOWED_APPS[app_key])
        return f"Opened {app_name}."
    except Exception as e:
        return f"Error opening {app_name}: {e}"


def list_sandbox_contents(subfolder: str = "") -> str:
    """List files and folders inside the automation sandbox."""
    try:
        path = _safe_sandbox_path(subfolder)
        if not os.path.isdir(path):
            return f"Error: '{subfolder}' does not exist in the sandbox."
        items = os.listdir(path)
        if not items:
            return "This sandbox folder is empty."
        return "\n".join(items)
    except ValueError as e:
        return f"Error: {e}"


def create_sandbox_folder(folder_name: str) -> str:
    """Create a new folder inside the automation sandbox."""
    if not folder_name or not folder_name.strip():
        return "Error: folder name is empty."
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
    """Open a YouTube search results page in the default browser."""
    search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    webbrowser.open(search_url)
    return f"Opened YouTube search for '{query}' in your browser."


def send_email(subject: str, body: str) -> str:
    """Send an email through the agent's dedicated test account, restricted to a single pre-approved recipient."""
    if not AGENT_EMAIL or not AGENT_EMAIL_PASSWORD:
        return "Error: email credentials are not configured."
    if not ALLOWED_RECIPIENT:
        return "Error: ALLOWED_RECIPIENT is not configured in .env, so no email was sent."
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = AGENT_EMAIL
        msg["To"] = ALLOWED_RECIPIENT
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(AGENT_EMAIL, AGENT_EMAIL_PASSWORD)
            server.send_message(msg)
        return f"Email sent to {_mask_email(ALLOWED_RECIPIENT)} with subject '{subject}' and body: {body}"
    except Exception as e:
        # Some SMTP errors include the recipient address, so mask it in the error text too.
        error_text = str(e).replace(ALLOWED_RECIPIENT, _mask_email(ALLOWED_RECIPIENT))
        return f"Error sending email: {error_text}"


def _get_calendar_service():
    """Build a Google Calendar client from the saved token, refreshing it silently when possible.

    This never opens a browser. The browser sign-in would block the voice loop, so it only
    happens in calendar_test.py, which the user runs by hand.
    """
    if not os.path.exists(TOKEN_FILE):
        raise CalendarAuthError(CALENDAR_SIGN_IN_MESSAGE)
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, CALENDAR_SCOPES)
    except Exception:
        raise CalendarAuthError(CALENDAR_SIGN_IN_MESSAGE)

    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise CalendarAuthError(CALENDAR_SIGN_IN_MESSAGE)
        try:
            creds.refresh(Request())
        except RefreshError:
            raise CalendarAuthError(CALENDAR_SIGN_IN_MESSAGE)
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def list_upcoming_events() -> str:
    """List the next 5 upcoming events from the user's Google Calendar."""
    try:
        service = _get_calendar_service()
        events_result = service.events().list(
            calendarId="primary", timeMin=_now_rfc3339(), maxResults=5, singleEvents=True, orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return "No upcoming events found."
        output = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            output.append(f"{start} - {event.get('summary', '(no title)')}")
        return "\n".join(output)
    except CalendarAuthError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing events: {e}"


def create_calendar_event(title: str, start_datetime: str, end_datetime: str) -> str:
    """Create a new event on the user's Google Calendar. 'title' is the event's name."""
    try:
        service = _get_calendar_service()
        event = {
            "summary": title,
            "start": {"dateTime": start_datetime, "timeZone": "Asia/Dhaka"},
            "end": {"dateTime": end_datetime, "timeZone": "Asia/Dhaka"},
        }
        created_event = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event '{title}' created successfully from {start_datetime} to {end_datetime}. Link: {created_event.get('htmlLink')}"
    except CalendarAuthError as e:
        return f"Error: {e} No event was created."
    except Exception as e:
        return f"Error creating event: {e}"


def delete_calendar_event(event_title: str) -> str:
    """Find and delete a calendar event by matching its title among upcoming events."""
    try:
        service = _get_calendar_service()
        events_result = service.events().list(
            calendarId="primary", timeMin=_now_rfc3339(), maxResults=20, singleEvents=True, orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])

        matching_events = [e for e in events if event_title.lower() in e.get("summary", "").lower()]

        if not matching_events:
            return f"No upcoming event found matching '{event_title}'."

        if len(matching_events) > 1:
            titles = [e.get("summary", "(no title)") for e in matching_events]
            return f"Multiple matching events found: {titles}. Please be more specific."

        event = matching_events[0]
        service.events().delete(calendarId="primary", eventId=event["id"]).execute()
        return f"Event '{event.get('summary', '(no title)')}' deleted successfully."
    except CalendarAuthError as e:
        return f"Error: {e} No event was deleted."
    except Exception as e:
        return f"Error deleting event: {e}"