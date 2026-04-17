"""
Geocoding Service
Converts a US address string to latitude/longitude.

Primary: Nominatim (OpenStreetMap) — free, no API key
Fallback: Google Maps Geocoding API (requires GOOGLE_MAPS_API_KEY env var)
"""

import asyncio
import os
from urllib.parse import quote

import httpx


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Required by Nominatim usage policy
NOMINATIM_USER_AGENT = "SkyBase-Intelligence/0.1 (andrewmarcucci13@gmail.com)"


async def geocode_address(address: str) -> dict:
    """
    Convert an address string to latitude/longitude.

    Tries Nominatim (OpenStreetMap) first, then falls back to Google Maps
    Geocoding API if GOOGLE_MAPS_API_KEY is set.

    Args:
        address: US address string (e.g. "1600 Pennsylvania Ave NW, Washington DC")

    Returns:
        {
            "lat": float,
            "lon": float,
            "formatted": str,       # canonical display address
            "source": "nominatim" | "google",
        }

    Raises:
        ValueError: If neither service can geocode the address.
    """
    # ── 1. Try Nominatim ──────────────────────────────────────────────────────
    try:
        params = {
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": "us",
        }
        headers = {"User-Agent": NOMINATIM_USER_AGENT}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(NOMINATIM_URL, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    hit = data[0]
                    return {
                        "lat": float(hit["lat"]),
                        "lon": float(hit["lon"]),
                        "formatted": hit.get("display_name", address),
                        "source": "nominatim",
                    }
    except Exception:
        pass  # Fall through to Google

    # ── 2. Try Google Maps Geocoding ──────────────────────────────────────────
    google_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if google_key:
        try:
            params = {"address": address, "key": google_key}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(GOOGLE_GEOCODE_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        hit = results[0]
                        loc = hit["geometry"]["location"]
                        return {
                            "lat": float(loc["lat"]),
                            "lon": float(loc["lng"]),
                            "formatted": hit.get("formatted_address", address),
                            "source": "google",
                        }
        except Exception:
            pass

    raise ValueError(f"Could not geocode address: {address}")


def geocode_address_sync(address: str) -> dict:
    """Synchronous wrapper around geocode_address — use from Celery/sync code."""
    return asyncio.run(geocode_address(address))
