from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.agent import pipeline
from app.agent.assess import assess_hotspot, level_for, rain_features
from app.agent.plan import allocate, build_tasks
from app.agent.reports import ReportStore, classify
from app.agent.sense import SCENARIOS, scenario_rain
from app.main import app

HS = {"id": "T1", "name": "Test Underpass", "lat": 12.97, "lng": 77.59, "zone": "East",
      "type": "underpass", "catchment": "Test valley", "base_vulnerability": 0.8}


def test_rain_features_finds_3h_peak():
    series = [0.0] * 48
    series[10:13] = [10, 30, 20]
    f = rain_features(series)
    assert f["max_3h_mm"] == 60
    assert f["peak_hour_offset"] == 11


def test_dry_day_is_low_risk():
    out = assess_hotspot(HS, scenario_rain(HS["lat"], HS["lng"], "dry"), [])
    assert out["level"] == "Low"


def test_storm_raises_risk_and_vulnerability_matters():
    series = [0.0] * 48
    series[6:9] = [20, 30, 20]
    high = assess_hotspot(HS, series, [])
    low = assess_hotspot({**HS, "base_vulnerability": 0.2}, series, [])
    assert high["risk"] > low["risk"]
    assert high["level"] in ("Warning", "Critical")


def test_citizen_reports_raise_risk_only_when_rain_is_coming():
    reports = [{"id": "R1", "lat": 12.9701, "lng": 77.5901, "type": "drain_blocked", "count": 3, "status": "open"}]
    dry = [0.0] * 48
    wet = [0.0] * 48
    wet[6:9] = [10, 15, 10]
    assert assess_hotspot(HS, dry, reports)["risk"] == assess_hotspot(HS, dry, [])["risk"]
    assert assess_hotspot(HS, wet, reports)["risk"] > assess_hotspot(HS, wet, [])["risk"]


def test_levels():
    assert level_for(0.9) == "Critical" and level_for(0.5) == "Warning" and level_for(0.3) == "Watch" and level_for(0.1) == "Low"


def test_underpass_needs_pump_and_traffic():
    hs = {**HS, "level": "Critical", "risk": 0.9, "peak_hour_offset": 8, "blocked_drain_reports": 0}
    needs = {t["resource"] for t in build_tasks([hs])}
    assert needs == {"pump_unit", "traffic_team"}


def test_allocation_respects_capacity_and_flags_late():
    depots = [{"id": "D", "name": "Depot", "lat": 12.97, "lng": 77.60}]
    hs_soon = {**HS, "level": "Critical", "risk": 0.9, "peak_hour_offset": 0, "blocked_drain_reports": 0}
    tasks = build_tasks([hs_soon, {**hs_soon, "id": "T2", "name": "Other"}])
    assigned, unassigned = allocate(tasks, depots, {"pump_unit": 1, "traffic_team": 1, "desilting_crew": 0})
    assert len(assigned) == 2 and len(unassigned) == 2
    assert all(a["status"] != "Before peak" for a in assigned)  # peak is now -> late


def test_classify_multilingual_and_safety_first():
    assert classify("drain near gate is blocked with plastic") == "drain_blocked"
    assert classify("ಚರಂಡಿ ತುಂಬಿದೆ") == "drain_blocked"
    assert classify("knee deep paani on road") == "waterlogging"
    assert classify("tree fallen and electric wire on road") == "power_hazard"


def test_dedupe_merges_nearby_same_type():
    st = ReportStore()
    now = datetime(2026, 10, 27, 10, 0)
    a = st.add(12.9, 77.6, "drain blocked", now=now)
    b = st.add(12.9005, 77.6005, "drain clogged", now=now + timedelta(hours=1))
    c = st.add(12.95, 77.6, "drain blocked", now=now)
    assert b["duplicate"] and b["id"] == a["id"] and b["count"] == 2
    assert not c["duplicate"]


def test_pipeline_all_scenarios_run():
    for sc in SCENARIOS:
        out = pipeline.run("scenario", sc)
        assert {t["step"] for t in out["trace"]} >= {"SENSE", "ASSESS", "PLAN", "ACT"}
        assert len(out["hotspots"]) == 30


def test_live_falls_back_when_offline(monkeypatch):
    import app.agent.sense as sense_mod

    def boom(*a, **k):
        raise ConnectionError("offline")
    monkeypatch.setattr(sense_mod, "fetch_live", boom)
    out = pipeline.run("live", "deluge")
    assert out["sense"]["source"] == "scenario" and "fell back" in out["sense"]["note"]


def test_api_end_to_end():
    c = TestClient(app)
    assert c.get("/api/health").json()["ok"]
    r = c.post("/api/run", json={"scenario": "deluge", "pump_unit": 2})
    assert r.status_code == 200 and r.json()["kpis"]["critical"] > 0
    rep = c.post("/api/reports", json={"lat": 12.95, "lng": 77.62, "text": "standing water knee deep"}).json()
    assert rep["type"] == "waterlogging"
    assert c.post("/api/reports", json={"lat": 1, "lng": 1}).status_code == 422
