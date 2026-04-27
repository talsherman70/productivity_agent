"""
Jewish calendar service using the Hebcal API (https://www.hebcal.com).
No API key required. Provides Shabbat times and Jewish holidays for Israel.
"""
import httpx
from datetime import date, datetime, timedelta


TEL_AVIV_GEONAME_ID = 293397  # Hebcal geoname ID for Tel Aviv


class JewishCalendarService:

    def get_events(self, start: str, end: str) -> list[dict]:
        """
        Fetches Jewish calendar events (holidays, candle lighting, havdalah)
        between start and end dates (YYYY-MM-DD).
        Returns a list of event dicts with keys: date, category, title.
        """
        response = httpx.get(
            "https://www.hebcal.com/hebcal",
            params={
                "v": 1,
                "cfg": "json",
                "maj": "on",       # major holidays
                "min": "on",       # minor holidays
                "ss": "on",        # special shabbatot
                "c": "on",         # candle lighting / havdalah
                "geonameid": TEL_AVIV_GEONAME_ID,
                "geo": "geoname",
                "M": "on",
                "start": start,
                "end": end,
            },
            timeout=8,
        )
        response.raise_for_status()
        return response.json().get("items", [])

    def get_context_for_range(self, start: str, end: str) -> list[dict]:
        """
        Returns a simplified list of planning-relevant constraints for the date range.
        Each item has: date (YYYY-MM-DD), type ('shabbat'|'holiday'|'candles'|'havdalah'), title.
        """
        raw = self.get_events(start, end)
        result = []
        for item in raw:
            raw_date = item.get("date", "")
            # Normalise datetime strings to date only
            date_str = raw_date[:10]
            category = item.get("category", "")
            title = item.get("title", "")

            if category in ("holiday", "candles", "havdalah"):
                result.append({
                    "date": date_str,
                    "type": "shabbat" if category in ("candles", "havdalah") else "holiday",
                    "title": title,
                    "raw_time": raw_date if "T" in raw_date else None,
                })

        return result

    def format_for_planner(self, start: str, end: str) -> str:
        """
        Returns a plain-text summary of Shabbat and holiday constraints
        suitable for injecting into the planner context.
        """
        events = self.get_context_for_range(start, end)
        if not events:
            return ""

        # Group candles/havdalah into Shabbat blocks
        shabbat_starts = {}   # date → time string
        shabbat_ends = {}
        holidays = []

        for e in events:
            if e["type"] == "shabbat":
                if "Candle lighting" in e["title"]:
                    time_str = e["title"].replace("Candle lighting: ", "")
                    shabbat_starts[e["date"]] = time_str
                elif "Havdalah" in e["title"]:
                    time_str = e["title"].replace("Havdalah: ", "")
                    shabbat_ends[e["date"]] = time_str
            elif e["type"] == "holiday":
                # Avoid duplicates
                entry = f"{e['date']}: {e['title']}"
                if entry not in holidays:
                    holidays.append(entry)

        lines = []

        if holidays:
            lines.append("Jewish holidays in this period:")
            lines.extend(f"  - {h}" for h in holidays)

        for start_date, start_time in sorted(shabbat_starts.items()):
            # Find the matching havdalah (next day)
            next_day = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            end_time = shabbat_ends.get(next_day, "nightfall")
            lines.append(f"Shabbat: {start_date} from {start_time} until {next_day} at {end_time} — shops, most restaurants closed; avoid scheduling commitments.")

        return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────────────────────

def get_jewish_calendar_service():
    try:
        return JewishCalendarService()
    except Exception:
        return None


jewish_calendar_service = get_jewish_calendar_service()
