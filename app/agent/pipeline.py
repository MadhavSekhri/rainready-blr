"""The agent loop: SENSE -> ASSESS -> PLAN -> ACT, with a human-readable trace."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import llm
from .act import act
from .assess import assess
from .plan import plan
from .sense import sense

DATA = json.loads((Path(__file__).resolve().parent.parent / "data" / "hotspots.json").read_text())
HOTSPOTS = DATA["hotspots"]
DEPOTS = DATA["depots"]
DEFAULT_CAPACITY = {"desilting_crew": 2, "pump_unit": 1, "traffic_team": 2}


def run(source: str = "scenario", scenario: str = "evening_thunderstorm",
        capacity: dict | None = None, reports: list[dict] | None = None) -> dict:
    capacity = {**DEFAULT_CAPACITY, **(capacity or {})}
    reports = reports or []
    trace = []
    t0 = time.perf_counter()

    def step(name: str, msg: str) -> None:
        trace.append({"step": name, "ms": round((time.perf_counter() - t0) * 1000), "msg": msg})

    s = sense(HOTSPOTS, source, scenario)
    wettest = max(HOTSPOTS, key=lambda h: sum(s["rain"][h["id"]][:24]))
    step("SENSE", f"{s['label']}. 48h hourly rain for {len(HOTSPOTS)} hotspots. Wettest: {wettest['name']} "
                  f"({sum(s['rain'][wettest['id']][:24]):.0f} mm/24h)." + (f" {s['note']}" if s["note"] else ""))
    step("SENSE", f"{len([r for r in reports if r['status'] == 'open'])} open citizen reports loaded.")

    assessed = assess(HOTSPOTS, s["rain"], reports)
    counts = {lvl: sum(1 for h in assessed if h["level"] == lvl) for lvl in ("Critical", "Warning", "Watch", "Low")}
    step("ASSESS", "Risk = rain burst & 24h soak x local vulnerability + citizen signals. "
                   + ", ".join(f"{v} {k}" for k, v in counts.items()) + ".")
    boosted = [h for h in assessed if h["blocked_drain_reports"] and h["level"] in ("Warning", "Critical")]
    if boosted:
        step("ASSESS", "Citizen blocked-drain reports raised priority at: " + "; ".join(h["name"] for h in boosted) + ".")

    p = plan(assessed, DEPOTS, capacity)
    total_units = sum(capacity.values()) * len(DEPOTS)
    step("PLAN", f"{len(p['assigned']) + len(p['unassigned'])} tasks generated; {len(p['assigned'])} assigned from "
                 f"{total_units} available units across {len(DEPOTS)} depots (nearest free unit, highest priority first).")
    if p["unassigned"]:
        step("PLAN", f"{len(p['unassigned'])} task(s) left without a unit - flagged for mutual aid.")

    a = act(assessed, p, s)
    brief, engine = llm.polish_brief(a["brief"])
    a["brief"] = brief
    step("ACT", f"{len(a['alerts'])} resident alerts (EN + ಕನ್ನಡ), {len(a['advisories'])} commuter advisories, "
                f"control-room brief written by {'IBM Granite (watsonx.ai)' if engine == 'granite' else 'rules engine'}.")

    lead_hours = [h["peak_hour_offset"] for h in assessed if h["level"] == "Critical" and h["peak_hour_offset"] is not None]
    kpis = {
        "critical": counts["Critical"],
        "warning": counts["Warning"],
        "units_dispatched": len(p["assigned"]),
        "critical_covered": p["critical_covered"],
        "critical_total": p["critical_total"],
        "on_time_pct": round(100 * sum(1 for x in p["assigned"] if x["status"] == "Before peak") / len(p["assigned"])) if p["assigned"] else 100,
        "min_lead_hours": min(lead_hours) if lead_hours else None,
    }
    return {"sense": {k: v for k, v in s.items() if k != "rain"}, "rain": s["rain"], "hotspots": assessed,
            "depots": DEPOTS, "plan": p, "act": a, "kpis": kpis, "trace": trace, "capacity": capacity}
