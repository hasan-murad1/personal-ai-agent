from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
import datetime

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


def list_upcoming_events():
    service = get_calendar_service()

    events_result = service.events().list(
        calendarId="primary",
        maxResults=5,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])

    if not events:
        print("No upcoming events found.")
        return

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(f"{start} - {event['summary']}")


def create_event(summary, start_datetime, end_datetime):
    service = get_calendar_service()

    event = {
        "summary": summary,
        "start": {"dateTime": start_datetime, "timeZone": "Asia/Dhaka"},
        "end": {"dateTime": end_datetime, "timeZone": "Asia/Dhaka"},
    }

    created_event = service.events().insert(calendarId="primary", body=event).execute()
    return created_event.get("htmlLink")


if __name__ == "__main__":
    list_upcoming_events()

    link = create_event(
        "Test Reminder from AI Agent",
        "2026-09-20T15:00:00",
        "2026-09-20T15:30:00"
    )
    print(f"\nEvent created: {link}")