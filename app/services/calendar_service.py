import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "Asia/Jerusalem"

_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
CREDENTIALS_PATH = os.path.join(PROJECT_ROOT, "credentials.json")
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")


class CalendarService:
    def __init__(self):
        self.service = self._authenticate()
        self.tz = ZoneInfo(TIMEZONE)

    def _authenticate(self):
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(
                f"credentials.json not found at {CREDENTIALS_PATH}."
            )

        creds = None

        if os.path.exists(TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_upcoming_events(self, days: int = 7) -> list:
        now = datetime.now(tz=self.tz)
        end = now + timedelta(days=days)

        result = self.service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        return result.get("items", [])

    def check_conflicts(self, date: str, time: str, duration_minutes: int = 60) -> list:
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=self.tz)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        result = self.service.events().list(
            calendarId="primary",
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            singleEvents=True,
        ).execute()

        return result.get("items", [])

    # ── Write ─────────────────────────────────────────────────────────────────

    def create_event(
        self,
        title: str,
        date: str,
        time: str,
        duration_minutes: int = 60,
        description: str = "",
    ) -> dict:
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=self.tz)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
        }

        return self.service.events().insert(
            calendarId="primary", body=event_body
        ).execute()

    def delete_event(self, event_id: str) -> None:
        """Deletes an event by its Google Calendar event ID."""
        self.service.events().delete(
            calendarId="primary", eventId=event_id
        ).execute()

    # ── Formatting ────────────────────────────────────────────────────────────

    def format_events_for_context(self, events: list) -> str:
        if not events:
            return "No upcoming events."

        lines = []
        for event in events:
            title = event.get("summary", "Untitled")
            start = event["start"].get("dateTime", event["start"].get("date", ""))
            if "T" in start:
                formatted_time = datetime.fromisoformat(start).strftime("%a %b %d at %H:%M")
            else:
                formatted_time = start
            lines.append(f"- {title}: {formatted_time}")

        return "\n".join(lines)

    def format_event_confirmation(self, event: dict) -> str:
        title = event.get("summary", "Event")
        start = event["start"].get("dateTime", "")
        if start:
            dt = datetime.fromisoformat(start)
            return f"{title} on {dt.strftime('%a %b %d at %H:%M')}"
        return title


# ── Singleton ─────────────────────────────────────────────────────────────────
# Created once when the server starts. Returns None if not authenticated yet.

def get_calendar_service():
    try:
        return CalendarService()
    except Exception:
        return None


calendar_service = get_calendar_service()
