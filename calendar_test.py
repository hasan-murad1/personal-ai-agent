import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import automation

TOKEN_FILE = automation.TOKEN_FILE
SCOPES = automation.CALENDAR_SCOPES


def sign_in():
    """Refresh the saved Google token, or open the browser sign-in if it is missing or can no longer be refreshed."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        print("Saved token is still valid.")
        return

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            print("Token refreshed without a browser sign-in.")
        except Exception:
            print("Token could not be refreshed, a browser sign-in is needed.")
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        print("Browser sign-in completed.")

    with open(TOKEN_FILE, "w") as token_file:
        token_file.write(creds.to_json())
    print(f"Saved {TOKEN_FILE}.")


if __name__ == "__main__":
    # Standalone re-authentication script. It only signs in and lists events; it never creates or deletes anything.
    sign_in()
    print("\nNext upcoming events:")
    print(automation.list_upcoming_events())