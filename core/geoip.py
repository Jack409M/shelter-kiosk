from __future__ import annotations

import json
from functools import lru_cache
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


def _empty(ip: str) -> dict:
    return {
        "ip": ip,
        "city": "",
        "region": "",
        "country": "",
        "lat": None,
        "lon": None,
    }


def _fetch_json(url: str) -> dict:
    req = Request(
        url,
        headers={
            "User-Agent": "DWC-SecurityDashboard/1.0"
        },
    )
    with urlopen(req, timeout=4) as resp:
        return json.loads(resp.read().decode("utf-8"))


@lru_cache(maxsize=5000)
def lookup_ip(ip: str) -> dict:
    if not ip:
        return _empty(ip)

    providers = [
        ("ipapi", f"https://ipapi.co/{ip}/json/"),
        ("ipwhois", f"https://ipwho.is/{ip}"),
        ("ipapi_com", f"http://ip-api.com/json/{ip}"),
    ]

    for provider_name, url in providers:
        try:
            data = _fetch_json(url)

            if provider_name == "ipapi":
                lat = data.get("latitude")
                lon = data.get("longitude")
                if lat is not None and lon is not None:
                    return {
                        "ip": ip,
                        "city": data.get("city", ""),
                        "region": data.get("region", ""),
                        "country": data.get("country_name", ""),
                        "lat": lat,
                        "lon": lon,
                    }

            elif provider_name == "ipwhois":
                lat = data.get("latitude")
                lon = data.get("longitude")
                if lat is not None and lon is not None:
                    return {
                        "ip": ip,
                        "city": data.get("city", ""),
                        "region": data.get("region", ""),
                        "country": data.get("country", ""),
                        "lat": lat,
                        "lon": lon,
                    }

            elif provider_name == "ipapi_com":
                lat = data.get("lat")
                lon = data.get("lon")
                if lat is not None and lon is not None and data.get("status") == "success":
                    return {
                        "ip": ip,
                        "city": data.get("city", ""),
                        "region": data.get("regionName", ""),
                        "country": data.get("country", ""),
                        "lat": lat,
                        "lon": lon,
                    }

        except (URLError, HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            continue

    return _empty(ip)
