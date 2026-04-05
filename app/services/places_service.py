import os
import math
from dotenv import load_dotenv
import googlemaps

load_dotenv()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Returns the great-circle distance in kilometres between two lat/lng points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

DEFAULT_RADIUS = 2000  # metres
DEFAULT_RESULT_LIMIT = 5


class PlacesService:
    def __init__(self):
        api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY not found in .env file")
        self.client = googlemaps.Client(key=api_key)

    # ── Search ────────────────────────────────────────────────────────────────

    def text_search(self, query: str, limit: int = DEFAULT_RESULT_LIMIT) -> list:
        """
        Search for places by text query (e.g. "Italian restaurant in Tel Aviv").
        Returns up to `limit` place dicts.
        """
        response = self.client.places(query=query)
        results = response.get("results", [])
        return results[:limit]

    def nearby_search(
        self,
        location: str,
        query: str,
        radius: int = DEFAULT_RADIUS,
        limit: int = DEFAULT_RESULT_LIMIT,
    ) -> list:
        """
        Search for places near a location string within a given radius (metres).
        Geocodes the location first, then uses text search with location bias.
        Returns up to `limit` place dicts.
        """
        geocode_result = self.client.geocode(location)
        if not geocode_result:
            raise ValueError(f"Could not geocode location: {location!r}")

        latlng = geocode_result[0]["geometry"]["location"]
        response = self.client.places(
            query=query,
            location=latlng,
            radius=radius,
        )
        results = response.get("results", [])[:limit]

        # Annotate each result with its distance from the search centre
        for place in results:
            place_loc = place.get("geometry", {}).get("location", {})
            if place_loc:
                place["_distance_km"] = round(
                    _haversine_km(latlng["lat"], latlng["lng"], place_loc["lat"], place_loc["lng"]),
                    1,
                )

        return results

    def get_place_details(self, place_id: str) -> dict:
        """
        Fetch full details for a place by its place_id.
        Returns the place detail dict (name, address, phone, hours, website, rating).
        """
        fields = [
            "name",
            "formatted_address",
            "formatted_phone_number",
            "opening_hours",
            "website",
            "rating",
            "place_id",
        ]
        result = self.client.place(place_id=place_id, fields=fields)
        return result.get("result", {})

    # ── Formatting ────────────────────────────────────────────────────────────

    def format_places_for_context(self, places: list, include_distances: bool = False) -> str:
        """
        Returns a numbered list of places suitable for displaying to the user.
        Pass include_distances=True to append straight-line distance to each entry.
        """
        if not places:
            return "No places found."

        lines = []
        for i, place in enumerate(places, start=1):
            name = place.get("name", "Unknown")
            address = place.get("formatted_address") or place.get("vicinity", "")
            rating = place.get("rating")
            distance = place.get("_distance_km")
            rating_str = f" ★ {rating}" if rating else ""
            distance_str = f" (~{distance} km straight-line)" if (include_distances and distance is not None) else ""
            lines.append(f"{i}. {name}{rating_str}{distance_str} — {address}")

        return "\n".join(lines)

    def format_place_for_event(self, place: dict) -> tuple[str, str]:
        """
        Returns (event_title, event_description) for creating a calendar event
        at this place.
        """
        name = place.get("name", "Visit")
        address = (
            place.get("formatted_address")
            or place.get("vicinity", "")
        )
        description = f"Location: {address}" if address else ""
        return name, description


# ── Singleton ─────────────────────────────────────────────────────────────────

def get_places_service():
    try:
        return PlacesService()
    except Exception:
        return None


places_service = get_places_service()
