"""RainReady BLR - FastAPI app. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import pipeline
from .agent.reports import ReportStore, seed
from .agent.sense import SCENARIOS

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="RainReady BLR", version="1.0.0")
store = ReportStore()
seed(store)


class RunRequest(BaseModel):
    source: str = Field("scenario", pattern="^(live|scenario)$")
    scenario: str = "evening_thunderstorm"
    desilting_crew: int = Field(2, ge=0, le=10)
    pump_unit: int = Field(1, ge=0, le=10)
    traffic_team: int = Field(2, ge=0, le=10)


class ReportIn(BaseModel):
    lat: float = Field(..., ge=12.7, le=13.3)
    lng: float = Field(..., ge=77.3, le=77.9)
    text: str = Field("", max_length=500)
    type: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/scenarios")
def scenarios() -> dict:
    return {k: v["label"] for k, v in SCENARIOS.items()}


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    return pipeline.run(
        source=req.source,
        scenario=req.scenario,
        capacity={"desilting_crew": req.desilting_crew, "pump_unit": req.pump_unit, "traffic_team": req.traffic_team},
        reports=store.all(),
    )


@app.get("/api/reports")
def list_reports() -> list[dict]:
    return store.all()


@app.post("/api/reports")
def add_report(r: ReportIn) -> dict:
    return store.add(r.lat, r.lng, r.text, r.type)


@app.post("/api/reports/{report_id}/resolve")
def resolve_report(report_id: str) -> dict:
    if not store.resolve(report_id):
        raise HTTPException(404, "report not found")
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
