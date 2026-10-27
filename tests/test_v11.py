import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent import copilot, pipeline, sense
from app.agent.reports import ReportStore, seed
from app.main import app

SETTINGS = {"source": "scenario", "scenario": "evening_thunderstorm",
            "capacity": {"desilting_crew": 2, "pump_unit": 1, "traffic_team": 2}}


def _store():
    st = ReportStore()
    seed(st)
    return st


def test_depot_override_reduces_capacity():
    base = pipeline.run(scenario="deluge")
    cut = pipeline.run(scenario="deluge", depot_overrides={"D-M": {"pump_unit": 0, "desilting_crew": 0}})
    assert not any(a["depot_id"] == "D-M" and a["resource"] in ("pump_unit", "desilting_crew") for a in cut["plan"]["assigned"])
    assert len(cut["plan"]["unassigned"]) > len(base["plan"]["unassigned"])
    assert any(t["step"] == "PLAN" and "overrides" in t["msg"] for t in cut["trace"])


def test_spare_units_are_consistent():
    r = pipeline.run(scenario="flash_storm")
    used = len(r["plan"]["assigned"])
    total = sum(sum(v.values()) for v in r["plan"]["spare"].values())
    assert used + total == sum(pipeline.DEFAULT_CAPACITY.values()) * len(pipeline.DEPOTS)


@pytest.mark.parametrize("question,tool,check", [
    ("What if Mahadevapura depot loses its pumps?", "run_plan", lambda a: a["depot_overrides"]["D-M"]["pump_unit"] == 0),
    ("What if Mahadevapura loses 1 desilting crew and the deluge hits?", "run_plan",
     lambda a: a["scenario"] == "deluge" and a["depot_overrides"]["D-M"]["desilting_crew"] == 1),
    ("What if we only have 1 traffic team per depot?", "run_plan", lambda a: a["capacity"]["traffic_team"] == 1),
    ("Replay the September 2022 ORR floods", "run_plan", lambda a: a["date"] == "2022-09-04"),
    ("Why is Silk Board critical?", "get_hotspot", lambda a: a["name"] == "Silk Board Junction"),
    ("Which tasks will be late?", "list_tasks", lambda a: a["status"] == "late"),
    ("Which tasks have no unit?", "list_tasks", lambda a: a["status"] == "unassigned"),
    ("Draft a Kannada alert for KR Circle Underpass", "draft_alert", lambda a: a["language"] == "kn"),
])
def test_router_maps_questions_to_tools(question, tool, check):
    out = copilot.ask(question, SETTINGS, _store().all())
    assert out["steps"][0]["tool"] == tool
    assert check(out["steps"][0]["args"])
    assert out["answer"]


def test_what_if_returns_new_run_and_numbers_are_grounded():
    out = copilot.ask("What if we lose 1 pump everywhere?", SETTINGS, _store().all())
    res = out["steps"][0]["result"]
    assert out["run"] is not None
    assert f"{out['run']['kpis']['critical_covered']}/{out['run']['kpis']['critical_total']}" in res["after"]
    assert res["after"] in out["answer"]


def test_granite_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "x")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "y")

    def boom(*a, **k):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(copilot, "_granite_chat", boom)
    out = copilot.ask("Which tasks will be late?", SETTINGS, [])
    assert out["engine"].startswith("Offline")


def test_granite_tool_loop(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "x")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "y")
    replies = iter([
        {"content": "", "tool_calls": [{"id": "c1", "function": {"name": "get_hotspot", "arguments": json.dumps({"name": "Silk Board"})}}]},
        {"content": "Silk Board is Critical because of an intense burst."},
    ])
    monkeypatch.setattr(copilot, "_granite_chat", lambda messages: next(replies))
    out = copilot.ask("why silk board?", SETTINGS, [])
    assert out["engine"].startswith("IBM Granite")
    assert out["steps"][0]["result"]["name"] == "Silk Board Junction"


def test_historical_replay_uses_archive(monkeypatch):
    def fake(hotspots, date, timeout=15.0):
        assert date == "2022-09-04"
        return [[0.0] * 10 + [30.0, 40.0, 30.0] + [0.0] * 35 for _ in hotspots]
    monkeypatch.setattr(sense, "fetch_historical", fake)
    r = pipeline.run(source="historical", date="2022-09-04")
    assert r["sense"]["source"] == "historical" and r["sense"]["start"].startswith("2022-09-04")
    assert r["kpis"]["critical"] > 0
    assert "Sep 2022" in r["act"]["alerts"][0]["en"]


def test_historical_falls_back_offline(monkeypatch):
    monkeypatch.setattr(sense, "fetch_historical", lambda *a, **k: (_ for _ in ()).throw(ConnectionError()))
    r = pipeline.run(source="historical", date="2022-09-04")
    assert r["sense"]["source"] == "scenario" and "Historical data unavailable" in r["sense"]["note"]


def test_sqlite_persists(tmp_path):
    db = str(tmp_path / "r.db")
    a = ReportStore(db)
    a.add(12.9, 77.6, "drain blocked")
    b = ReportStore(db)
    assert len(b.all()) == 1 and b.all()[0]["type"] == "drain_blocked"
    assert b.resolve("R0001") and ReportStore(db).all()[0]["status"] == "resolved"


def test_photo_upload_and_validation():
    c = TestClient(app)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 20).decode()
    r = c.post("/api/reports", json={"lat": 12.95, "lng": 77.62, "text": "knee deep water", "photo": f"data:image/png;base64,{png}"})
    assert r.status_code == 200 and r.json()["photos"][0].startswith("/uploads/")
    assert c.get(r.json()["photos"][0]).status_code == 200
    bad = c.post("/api/reports", json={"lat": 12.95, "lng": 77.62, "photo": "data:text/html;base64,PGI+"})
    assert bad.status_code == 422


def test_whatsapp_flow():
    c = TestClient(app)
    first = c.post("/api/whatsapp", data={"From": "whatsapp:+910000000001", "Body": "Drain blocked near my gate"})
    assert "share your location" in first.text
    second = c.post("/api/whatsapp", data={"From": "whatsapp:+910000000001", "Latitude": "12.9500", "Longitude": "77.6300"})
    assert "Ticket" in second.text and "Storm Water Drain" in second.text
    far = c.post("/api/whatsapp", data={"From": "whatsapp:+910000000002", "Body": "flood", "Latitude": "19.0", "Longitude": "72.8"})
    assert "outside Bengaluru" in far.text


def test_api_ask_and_historical_events():
    c = TestClient(app)
    assert "2022-09-04" in c.get("/api/historical-events").json()
    r = c.post("/api/ask", json={"question": "What if Bommanahalli depot loses its pumps?"})
    assert r.status_code == 200 and r.json()["run"]["depot_overrides"] == {"D-B": {"pump_unit": 0}}
    assert c.post("/api/run", json={"depot_overrides": {"D-X": {"pump_unit": 5}}}).status_code == 200
