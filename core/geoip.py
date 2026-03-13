from __future__ import annotations

import json
from functools import lru_cache
from urllib.error import URLError
from urllib.request import urlopen


@lru_cache(maxsize=5000)
def lookup_ip(ip: str) -> dict:
    try:
        with urlopen(f"https://ipapi.co/{ip}/json/", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return {
            "ip": ip,
            "city": data.get("city", ""),
            "region": data.get("region", ""),
            "country": data.get("country_name", ""),
            "lat": data.get("latitude"),
            "lon": data.get("longitude"),
        }
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return {
            "ip": ip,
            "city": "",
            "region": "",
            "country": "",
            "lat": None,
            "lon": None,
        }
