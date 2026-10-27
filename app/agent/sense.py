"""SENSE step: get a 48-hour hourly rainfall outlook for every hotspot.

Sources
- live:      Open-Meteo forecast API (free, no key). One request for all hotspots.
- scenario:  deterministic synthetic storms so the agent can be demoed and
             tested on any day, including dry ones.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .geo import haversine_km

IST = ZoneInfo("Asia/Kolkata")
HOURS = 48
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Storm cells: (lat, lng, radius_km, peak_hour_offset, peak_mm_per_hr, duration_hr)
SCENARIOS: dict[str, dict] = {
    "dry": {
        "label": "Dry day (baseline)",
        "cells": [],
        "drizzle": 0.2,
    },
    "evening_thunderstorm": {
        "label": "Evening thunderstorm over South-Central Bengaluru",
        "cells": [(12.935, 77.625, 9.0, 8, 30.0, 3)],
        "drizzle": 0.5,
    },
    "flash_storm": {
        "label": "Flash storm over Central Bengaluru arriving in ~2 hours",
        "cells": [(12.975, 77.590, 6.0, 2, 32.0, 2)],
        "drizzle": 0.3,
    },
    "deluge": {
        "label": "Prolonged deluge over East Bengaluru (synthetic, ~130 mm/24h at core)",
        "cells": [
            (12.935, 77.690, 11.0, 10, 25.0, 6),
            (13.030, 77.640, 8.0, 12, 22.0, 4),
        ],
        "drizzle": 1.0,
    },
}


def _hour_axis(now: datetime | None = None) -> list[datetime]:
    now = (now or datetime.now(IST)).replace(minute=0, second=0, microsecond=0)
    return [now + timedelta(hours=h) for h in range(HOURS)]


def scenario_rain(lat: float, lng: float, scenario: str) -> list[float]:
    """Hourly rain (mm) for one location under a synthetic scenario."""
    spec = SCENARIOS[scenario]
    series = [spec["drizzle"] * (0.5 + 0.5 * math.sin(h / 5.0)) ** 2 for h in range(HOURS)]
    for c_lat, c_lng, radius, peak_h, peak_mm, duration in spec["cells"]:
        d = haversine_km(lat, lng, c_lat, c_lng)
        spatial = math.exp(-((d / radius) ** 2))
        sigma = max(duration / 2.0, 1.0)
        for h in range(HOURS):
            temporal = math.exp(-(((h - peak_h) / sigma) ** 2))
            series[h] += peak_mm * spatial * temporal
    return [round(v, 2) for v in series]


def fetch_live(hotspots: list[dict], timeout: float = 8.0) -> list[list[float]]:
    """Return hourly precipitation for each hotspot from Open-Meteo.

    Raises on any network/format error so the caller can fall back.
    """
    params = {
        "latitude": ",".join(str(h["lat"]) for h in hotspots),
        "longitude": ",".join(str(h["lng"]) for h in hotspots),
        "hourly": "precipitation",
        "forecast_days": 3,
        "timezone": "Asia/Kolkata",
    }
    resp = httpx.get(OPEN_METEO_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict):
        payload = [payload]
    now_key = datetime.now(IST).strftime("%Y-%m-%dT%H:00")
    out = []
    for loc in payload:
        times = loc["hourly"]["time"]
        values = loc["hourly"]["precipitation"]
        start = times.index(now_key) if now_key in times else 0
        window = [float(v or 0.0) for v in values[start:start + HOURS]]
        window += [0.0] * (HOURS - len(window))
        out.append(window)
    if len(out) != len(hotspots):
        raise ValueError("Open-Meteo returned an unexpected number of locations")
    return out


def sense(hotspots: list[dict], source: str = "scenario", scenario: str = "evening_thunderstorm") -> dict:
    """Return {'source', 'label', 'hours', 'rain': {hotspot_id: [mm,...]}, 'note'}."""
    hours = _hour_axis()
    note = ""
    if source == "live":
        try:
            series = fetch_live(hotspots)
            return {
                "source": "live",
                "label": "Live forecast (Open-Meteo, next 48h)",
                "hours": [h.isoformat() for h in hours],
                "rain": {h["id"]: s for h, s in zip(hotspots, series)},
                "note": note,
            }
        except Exception as exc:  # network blocked, API down, etc.
            note = f"Live forecast unavailable ({type(exc).__name__}); fell back to scenario '{scenario}'."
    if scenario not in SCENARIOS:
        scenario = "evening_thunderstorm"
    return {
        "source": "scenario",
        "scenario": scenario,
        "label": SCENARIOS[scenario]["label"],
        "hours": [h.isoformat() for h in hours],
        "rain": {h["id"]: scenario_rain(h["lat"], h["lng"], scenario) for h in hotspots},
        "note": note,
    }
