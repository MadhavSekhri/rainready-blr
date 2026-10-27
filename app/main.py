"""RainReady BLR - FastAPI app. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

import base64
import binascii
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import copilot, pipeline
from .agent.reports import ReportStore, seed
from .agent.sense import HISTORICAL_EVENTS, SCENARIOS

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.getenv("RAINREADY_DATA", ROOT.parent / "data"))
UPLOADS = DATA_DIR / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="RainReady BLR", version="1.1.0")
store = ReportStore(os.getenv("RAINREADY_DB", str(DATA_DIR / "rainready.db")))
if store.empty():
    seed(store)

MAX_PHOTO_BYTES = 3_000_000
DEPOT_IDS = {d["id"] for d in pipeline.DEPOTS}
RESOURCE_KEYS = set(pipeline.DEFAULT_CAPACITY)


class RunRequest(BaseModel):
    source: str = Field("scenario", pattern="^(live|scenario|historical)$")
    scenario: str = "evening_thunderstorm"
    date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    desilting_crew: int = Field(2, ge=0, le=10)
    pump_unit: int = Field(1, ge=0, le=10)
    traffic_team: int = Field(2, ge=0, le=10)
    depot_overrides: dict[str, dict[str, int]] = {}

    def settings(self) -> dict:
        overrides = {d: {r: max(0, min(10, n)) for r, n in res.items() if r in RESOURCE_KEYS}
                     for d, res in self.depot_overrides.items() if d in DEPOT_IDS}
        return {
            "source": self.source, "scenario": self.scenario, "date": self.date,
            "capacity": {"desilting_crew": self.desilting_crew, "pump_unit": self.pump_unit, "traffic_team": self.traffic_team},
            "depot_overrides": overrides or None,
        }


class AskRequest(RunRequest):
    question: str = Field(..., min_length=2, max_length=500)


class ReportIn(BaseModel):
    lat: float = Field(..., ge=12.7, le=13.3)
    lng: float = Field(..., ge=77.3, le=77.9)
    text: str = Field("", max_length=500)
    type: str | None = None
    photo: str | None = Field(None, description="Optional image as a data: URL (jpeg/png/webp, max 3 MB)")


def _save_photo(data_url: str) -> str:
    m = re.match(r"^data:image/(jpeg|jpg|png|webp);base64,(.+)$", data_url, re.S)
    if not m:
        raise HTTPException(422, "photo must be a jpeg/png/webp data URL")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "photo is not valid base64")
    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo larger than 3 MB")
    ext = "jpg" if m.group(1) in ("jpeg", "jpg") else m.group(1)
    name = f"{os.urandom(8).hex()}.{ext}"
    (UPLOADS / name).write_bytes(raw)
    return f"/uploads/{name}"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/scenarios")
def scenarios() -> dict:
    return {k: v["label"] for k, v in SCENARIOS.items()}


@app.get("/api/historical-events")
def historical_events() -> dict:
    return HISTORICAL_EVENTS


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    return pipeline.run(reports=store.all(), **req.settings())


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    return copilot.ask(req.question, req.settings(), store.all())


@app.get("/api/reports")
def list_reports() -> list[dict]:
    return store.all()


@app.post("/api/reports")
def add_report(r: ReportIn) -> dict:
    photo = _save_photo(r.photo) if r.photo else None
    return store.add(r.lat, r.lng, r.text, r.type, photo=photo)


@app.post("/api/reports/{report_id}/resolve")
def resolve_report(report_id: str) -> dict:
    if not store.resolve(report_id):
        raise HTTPException(404, "report not found")
    return {"ok": True}


# --- WhatsApp (Twilio-compatible webhook) -------------------------------------
# Point a Twilio WhatsApp sandbox "When a message comes in" URL at /api/whatsapp.
# Citizens send a description (and optionally a photo), then share their location.
_pending: dict[str, dict] = {}


def _twiml(message: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>',
                    media_type="application/xml")


@app.post("/api/whatsapp")
def whatsapp(From: str = Form(""), Body: str = Form(""), Latitude: float | None = Form(None),
             Longitude: float | None = Form(None), NumMedia: int = Form(0), MediaUrl0: str | None = Form(None)) -> Response:
    sender = From or "anonymous"
    pending = _pending.setdefault(sender, {"text": "", "photo": None})
    if Body.strip():
        pending["text"] = (pending["text"] + " " + Body.strip()).strip()[:500]
    if NumMedia and MediaUrl0:
        pending["photo"] = MediaUrl0
    if Latitude is None or Longitude is None:
        return _twiml("Thanks! Now share your location (📎 → Location) so we can route this to the right team. "
                      "ಧನ್ಯವಾದಗಳು! ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸ್ಥಳವನ್ನು ಹಂಚಿಕೊಳ್ಳಿ.")
    if not (12.7 <= Latitude <= 13.3 and 77.3 <= Longitude <= 77.9):
        _pending.pop(sender, None)
        return _twiml("That location is outside Bengaluru, so we can't log it. Please try again from the spot.")
    rec = store.add(Latitude, Longitude, pending["text"] or "waterlogging", photo=pending["photo"], channel="whatsapp")
    _pending.pop(sender, None)
    if rec["duplicate"]:
        return _twiml(f"Already reported as {rec['id']} ({rec['count']} reports). Your report adds priority. "
                      f"Routed to {rec['routed_to']}.")
    return _twiml(f"Ticket {rec['id']} created: {rec['type'].replace('_', ' ')}. Routed to {rec['routed_to']}. "
                  "RainReady will factor it into the next flood plan.")


app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
