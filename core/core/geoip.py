from functools import lru_cache
import requests


@lru_cache(maxsize=5000)
def lookup_ip(ip: str) -> dict:
    """
    Lightweight IP geolocation lookup.
    Uses ipapi.co which does not require an API key
    for moderate usage.
    """

    try:
        r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        data = r.json()

        return {
            "ip": ip,
            "city": data.get("city", ""),
            "region": data.get("region", ""),
            "country": data.get("country_name", ""),
            "lat": data.get("latitude"),
            "lon": data.get("longitude"),
        }

    except Exception:
        return {
            "ip": ip,
            "city": "",
            "region": "",
            "country": "",
            "lat": None,
            "lon": None,
        }
