"""Citizen report intake: classify, de-duplicate, route.

Free text can be English, Kannada or Hinglish/Kanglish. Classification is
keyword based so it works offline; an LLM can be plugged in later.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
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
    """Citizen reports, persisted in SQLite (":memory:" for tests and throwaway demos)."""

    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, lat REAL, lng REAL, type TEXT, routed_to TEXT, count INTEGER,
            status TEXT, created TEXT, last_seen TEXT, texts TEXT, photos TEXT, channel TEXT)""")
        self.db.commit()

    def _row(self, r: sqlite3.Row) -> dict:
        d = dict(r)
        d["texts"] = json.loads(d["texts"])
        d["photos"] = json.loads(d["photos"] or "[]")
        return d

    def _next_id(self) -> str:
        n = self.db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        return f"R{n + 1:04d}"

    def add(self, lat: float, lng: float, text: str = "", type_hint: str | None = None,
            now: datetime | None = None, photo: str | None = None, channel: str = "web") -> dict:
        now = now or datetime.now(IST)
        rtype = classify(text, type_hint)
        with self.lock:
            for r in self.all():
                if (r["type"] == rtype and r["status"] == "open"
                        and haversine_km(r["lat"], r["lng"], lat, lng) <= DEDUPE_RADIUS_KM
                        and now - datetime.fromisoformat(r["last_seen"]) <= DEDUPE_WINDOW):
                    r["count"] += 1
                    r["last_seen"] = now.isoformat()
                    r["texts"].append(text)
                    if photo:
                        r["photos"].append(photo)
                    self.db.execute("UPDATE reports SET count=?, last_seen=?, texts=?, photos=? WHERE id=?",
                                    (r["count"], r["last_seen"], json.dumps(r["texts"]), json.dumps(r["photos"]), r["id"]))
                    self.db.commit()
                    return {**r, "duplicate": True}
            rec = {
                "id": self._next_id(), "lat": lat, "lng": lng, "type": rtype, "routed_to": ROUTING[rtype],
                "count": 1, "status": "open", "created": now.isoformat(), "last_seen": now.isoformat(),
                "texts": [text], "photos": [photo] if photo else [], "channel": channel,
            }
            self.db.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (rec["id"], lat, lng, rtype, rec["routed_to"], 1, "open", rec["created"], rec["last_seen"],
                             json.dumps(rec["texts"]), json.dumps(rec["photos"]), channel))
            self.db.commit()
            return {**rec, "duplicate": False}

    def resolve(self, report_id: str) -> bool:
        with self.lock:
            cur = self.db.execute("UPDATE reports SET status='resolved' WHERE id=?", (report_id,))
            self.db.commit()
            return cur.rowcount > 0

    def all(self) -> list[dict]:
        return [self._row(r) for r in self.db.execute("SELECT * FROM reports ORDER BY created, id")]

    def empty(self) -> bool:
        return self.db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0


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
