"""
Run this script ONCE to authenticate with Google Calendar.
It will open a browser window asking you to log in.
After you approve, token.json is saved and the server can use
your calendar automatically without any further login prompts.

Usage:
    .venv/Scripts/activate
    python setup_calendar.py
"""
from app.services.calendar_service import CalendarService

print("Opening browser for Google Calendar authentication...")
print("Please log in and grant access when prompted.\n")

try:
    service = CalendarService()
    events = service.get_upcoming_events(days=3)
    print("Authentication successful!")
    print(f"Found {len(events)} event(s) in the next 3 days.")
    print("\nYou can now start the server normally:")
    print("  uvicorn app.main:app --reload")
except Exception as e:
    print(f"Something went wrong: {e}")
