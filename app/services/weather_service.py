"""
Weather service using wttr.in (https://wttr.in).
No API key required. Returns up to 3 days of forecast.
"""
import httpx
from datetime import datetime


# wttr.in weather codes → human-readable descriptions
WTTR_DESCRIPTIONS = {
    113: "Clear sky",
    116: "Partly cloudy",
    119: "Cloudy",
    122: "Overcast",
    143: "Mist",
    176: "Patchy rain",
    179: "Patchy snow",
    200: "Thundery outbreaks",
    248: "Fog",
    260: "Freezing fog",
    263: "Light drizzle",
    266: "Light drizzle",
    281: "Freezing drizzle",
    284: "Heavy freezing drizzle",
    293: "Light rain",
    296: "Light rain",
    299: "Moderate rain",
    302: "Moderate rain",
    305: "Heavy rain",
    308: "Heavy rain",
    311: "Freezing rain",
    314: "Heavy freezing rain",
    317: "Light sleet",
    320: "Sleet",
    323: "Light snow",
    326: "Light snow",
    329: "Moderate snow",
    332: "Moderate snow",
    335: "Heavy snow",
    338: "Heavy snow",
    353: "Light rain showers",
    356: "Rain showers",
    359: "Torrential rain",
    362: "Sleet showers",
    368: "Snow showers",
    371: "Heavy snow showers",
    386: "Rain with thunder",
    389: "Heavy rain with thunder",
    392: "Snow with thunder",
    395: "Heavy snow with thunder",
}

BAD_WEATHER_CODES = {
    176, 179, 200, 248, 260, 263, 266, 281, 284,
    293, 296, 299, 302, 305, 308, 311, 314, 317, 320,
    323, 326, 329, 332, 335, 338, 353, 356, 359,
    362, 365, 368, 371, 374, 377, 386, 389, 392, 395,
}


class WeatherService:

    def get_forecast(self, location: str, days: int = 3) -> list[dict]:
        """
        Returns a list of daily forecast dicts (up to 3 days).
        Each dict has: date, description, temp_max, temp_min, precipitation_mm, code.
        """
        response = httpx.get(
            f"https://wttr.in/{location}",
            params={"format": "j1"},
            timeout=8,
            follow_redirects=True,
        )
        response.raise_for_status()
        data = response.json()

        result = []
        for day in data.get("weather", [])[:days]:
            # Use midday hourly entry (index 4 = 12:00) for the day's weather code
            hourly = day.get("hourly", [])
            midday = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
            code = int(midday.get("weatherCode", 113))
            precip = float(midday.get("precipMM", 0))

            result.append({
                "date": day["date"],
                "description": WTTR_DESCRIPTIONS.get(code, "Unknown"),
                "temp_max": int(day["maxtempC"]),
                "temp_min": int(day["mintempC"]),
                "precipitation_mm": precip,
                "code": code,
            })

        return result

    def get_weather_for_date(self, location: str, target_date: str) -> dict | None:
        """Returns forecast for a specific date (YYYY-MM-DD), or None if out of range."""
        forecast = self.get_forecast(location, days=3)
        for day in forecast:
            if day["date"] == target_date:
                return day
        return None

    # ── Formatting ────────────────────────────────────────────────────────────

    def format_forecast(self, forecast: list[dict]) -> str:
        if not forecast:
            return "No forecast available."
        lines = []
        for day in forecast:
            dt = datetime.strptime(day["date"], "%Y-%m-%d")
            label = dt.strftime("%a %b %d")
            desc = day["description"]
            hi = day["temp_max"]
            lo = day["temp_min"]
            rain = day["precipitation_mm"]
            rain_str = f", {rain}mm rain" if rain and rain > 0 else ""
            lines.append(f"- {label}: {desc}, {lo}°C – {hi}°C{rain_str}")
        return "\n".join(lines)

    def format_single_day(self, day: dict) -> str:
        dt = datetime.strptime(day["date"], "%Y-%m-%d")
        label = dt.strftime("%A %b %d")
        desc = day["description"]
        hi = day["temp_max"]
        lo = day["temp_min"]
        rain = day["precipitation_mm"]
        rain_str = f" with {rain}mm of rain expected" if rain and rain > 0 else ""
        return f"{label}: {desc}{rain_str}, {lo}°C – {hi}°C"

    def is_bad_weather(self, day: dict) -> bool:
        """Returns True if the weather involves rain, snow, storms, or fog."""
        return day.get("code", 113) in BAD_WEATHER_CODES


# ── Singleton ─────────────────────────────────────────────────────────────────

def get_weather_service():
    try:
        return WeatherService()
    except Exception:
        return None


weather_service = get_weather_service()
