import os
from datetime import datetime, timedelta, timezone

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

# Hardcoded Israel Daylight Time (UTC+3, used April–October).
# For a production app this should use ZoneInfo("Asia/Jerusalem") to handle DST.
_ISRAEL_TZ = timezone(timedelta(hours=3))


class CalendarService:
    def __init__(self):
        self.service = self._authenticate()
        self.tz = _ISRAEL_TZ

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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_aware(self, date: str, time: str) -> datetime:
        """
        Parse the time the LLM output (local Israel time) and add 3h so that
        Google Calendar stores the correct absolute time.
        """
        naive = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        return (naive + timedelta(hours=3)).replace(tzinfo=self.tz)

    @staticmethod
    def _parse_google_dt(dt_str: str) -> datetime:
        """
        Parse a datetime string returned by the Google Calendar API.
        Handles both RFC3339 offset format ("...+03:00") and UTC "Z" suffix.
        """
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

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
        start_dt = self._make_aware(date, time)
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
        # Send a naive datetime string (no UTC offset) + timeZone so Google
        # interprets the time as local Israel time directly.
        start_dt = self._make_aware(date, time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        fmt = "%Y-%m-%dT%H:%M:%S"

        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.strftime(fmt), "timeZone": TIMEZONE},
            "end": {"dateTime": end_dt.strftime(fmt), "timeZone": TIMEZONE},
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
                try:
                    dt = self._parse_google_dt(start).astimezone(self.tz) - timedelta(hours=3)
                    formatted_time = dt.strftime("%a %b %d at %H:%M")
                except Exception:
                    formatted_time = start
            else:
                formatted_time = start
            lines.append(f"- {title}: {formatted_time}")

        return "\n".join(lines)

    def format_event_confirmation(self, event: dict) -> str:
        title = event.get("summary", "Event")
        start = event["start"].get("dateTime", "")
        if start:
            try:
                dt = self._parse_google_dt(start).astimezone(self.tz) - timedelta(hours=3)
                return f"{title} on {dt.strftime('%a %b %d at %H:%M')}"
            except Exception:
                pass
        return title


# ── Singleton ─────────────────────────────────────────────────────────────────
# Created once when the server starts. Returns None if not authenticated yet.

def get_calendar_service():
    try:
        return CalendarService()
    except Exception:
        return None


calendar_service = get_calendar_service()
