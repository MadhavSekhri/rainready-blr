"""Citizen report intake: classify, de-duplicate, route.

Free text can be English, Kannada or Hinglish/Kanglish. Classification is
keyword based so it works offline; an LLM can be plugged in later.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .geo import haversine_km

IST = ZoneInfo("Asia/Kolkata")
DEDUPE_RADIUS_KM = 0.15
DEDUPE_WINDOW = timedelta(hours=6)

KEYWORDS = {
    "drain_blocked": ["drain", "blocked", "clog", "choke", "garbage in", "silt", "nala", "naala",
                      "ಚರಂಡಿ", "ಮೋರಿ", "kachra", "plastic"],
    "waterlogging": ["water logging", "waterlogging", "flood", "knee", "standing water", "pani", "paani",
                     "ನೀರು", "submerged", "stuck", "logged"],
    "tree_fall": ["tree", "branch", "fallen", "ಮರ"],
    "power_hazard": ["wire", "electric", "current", "pole", "transformer", "shock", "ವಿದ್ಯುತ್"],
}

ROUTING = {
    "drain_blocked": "GBA Storm Water Drain (SWD) division",
    "waterlogging": "GBA SWD division + Bengaluru Traffic Police",
    "tree_fall": "GBA Forest cell",
    "power_hazard": "BESCOM emergency",
}

_ids = itertools.count(1)


def classify(text: str, hint: str | None = None) -> str:
    if hint in ROUTING:
        return hint
    t = (text or "").lower()
    scores = {k: sum(1 for w in words if w.lower() in t) for k, words in KEYWORDS.items()}
    # Safety first: any electrical hazard wins.
    if scores["power_hazard"]:
        return "power_hazard"
    best = max(scores, key=scores.get)
    return best if scores[best] else "waterlogging"


class ReportStore:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, lat: float, lng: float, text: str = "", type_hint: str | None = None,
            now: datetime | None = None) -> dict:
        now = now or datetime.now(IST)
        rtype = classify(text, type_hint)
        for r in self.items:
            if (r["type"] == rtype and r["status"] == "open"
                    and haversine_km(r["lat"], r["lng"], lat, lng) <= DEDUPE_RADIUS_KM
                    and now - datetime.fromisoformat(r["last_seen"]) <= DEDUPE_WINDOW):
                r["count"] += 1
                r["last_seen"] = now.isoformat()
                r["texts"].append(text)
                return {**r, "duplicate": True}
        rec = {
            "id": f"R{next(_ids):04d}",
            "lat": lat,
            "lng": lng,
            "type": rtype,
            "routed_to": ROUTING[rtype],
            "count": 1,
            "status": "open",
            "created": now.isoformat(),
            "last_seen": now.isoformat(),
            "texts": [text],
        }
        self.items.append(rec)
        return {**rec, "duplicate": False}

    def resolve(self, report_id: str) -> bool:
        for r in self.items:
            if r["id"] == report_id:
                r["status"] = "resolved"
                return True
        return False

    def all(self) -> list[dict]:
        return list(self.items)


SEED_REPORTS = [
    (12.9124, 77.6869, "Drain near Rainbow Drive gate fully blocked with plastic and silt", None),
    (12.9126, 77.6866, "same drain blocked, garbage in nala", None),
    (13.0272, 77.6603, "Sai Layout main road drain choked, ಚರಂಡಿ ತುಂಬಿದೆ", None),
    (12.9351, 77.6249, "ST Bed 1st cross drain clogged since last week", None),
    (12.9770, 77.5884, "KR Circle underpass inlet grill blocked with leaves", "drain_blocked"),
    (12.9605, 77.6385, "Electric wire hanging low near Domlur bus stop", None),
]


def seed(store: ReportStore) -> None:
    for lat, lng, text, hint in SEED_REPORTS:
        store.add(lat, lng, text, hint)
