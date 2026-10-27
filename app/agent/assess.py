"""ASSESS step: turn rainfall + local vulnerability + citizen signals into an
explainable 0-1 flood risk per hotspot.

Thresholds are anchored on IMD rainfall categories (heavy: 64.5 mm/24h,
very heavy: 115.6 mm/24h) and on the short-burst intensity that typically
overwhelms Bengaluru's storm-water drains (~40-60 mm in 3 hours).
"""
from __future__ import annotations

from .geo import haversine_km

LEVELS = [(0.65, "Critical"), (0.45, "Warning"), (0.25, "Watch"), (0.0, "Low")]
REPORT_RADIUS_KM = 0.6


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def rain_features(series: list[float]) -> dict:
    total_24 = sum(series[:24])
    max_3h, peak_idx = 0.0, 0
    for i in range(len(series) - 2):
        window = series[i] + series[i + 1] + series[i + 2]
        if window > max_3h:
            max_3h, peak_idx = window, i + 1
    peak_1h = max(series) if series else 0.0
    return {
        "total_24h_mm": round(total_24, 1),
        "max_3h_mm": round(max_3h, 1),
        "peak_1h_mm": round(peak_1h, 1),
        "peak_hour_offset": peak_idx if max_3h > 0.5 else None,
    }


def level_for(score: float) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "Low"


def assess_hotspot(hotspot: dict, series: list[float], reports: list[dict]) -> dict:
    f = rain_features(series)
    burst = _clamp(f["max_3h_mm"] / 60.0)
    soak = _clamp(f["total_24h_mm"] / 115.6)
    hazard = 0.65 * burst + 0.35 * soak
    vuln = hotspot["base_vulnerability"]

    reasons = []
    if f["max_3h_mm"] >= 40:
        reasons.append(f"Intense burst: {f['max_3h_mm']} mm in 3h")
    elif f["max_3h_mm"] >= 15:
        reasons.append(f"Moderate burst: {f['max_3h_mm']} mm in 3h")
    if f["total_24h_mm"] >= 64.5:
        reasons.append(f"IMD 'heavy' rain: {f['total_24h_mm']} mm in 24h")
    if vuln >= 0.75:
        reasons.append(f"History of severe waterlogging ({hotspot['catchment']})")

    nearby = [
        r for r in reports
        if r.get("status", "open") == "open"
        and haversine_km(r["lat"], r["lng"], hotspot["lat"], hotspot["lng"]) <= REPORT_RADIUS_KM
    ]
    blocked = sum(r.get("count", 1) for r in nearby if r["type"] == "drain_blocked")
    logged = sum(r.get("count", 1) for r in nearby if r["type"] == "waterlogging")
    signal_boost = _clamp(0.06 * blocked + 0.12 * logged, 0.0, 0.3)
    if blocked:
        reasons.append(f"{blocked} citizen report(s) of blocked drains nearby")
    if logged:
        reasons.append(f"{logged} citizen report(s) of water already standing")

    # Vulnerability amplifies hazard; citizen signals raise risk only when rain is coming.
    score = _clamp(hazard * (0.3 + 0.7 * vuln) + signal_boost * _clamp(hazard * 2.5))
    return {
        **hotspot,
        **f,
        "risk": round(score, 3),
        "level": level_for(score),
        "reasons": reasons or ["No significant rain expected"],
        "nearby_reports": [r["id"] for r in nearby],
        "blocked_drain_reports": blocked,
    }


def assess(hotspots: list[dict], rain: dict[str, list[float]], reports: list[dict]) -> list[dict]:
    out = [assess_hotspot(h, rain[h["id"]], reports) for h in hotspots]
    return sorted(out, key=lambda x: x["risk"], reverse=True)
