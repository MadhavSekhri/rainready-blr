"""PLAN step: decide what to send where, before the rain peaks.

Each at-risk hotspot generates tasks based on what actually fails at that
kind of location. Tasks are then assigned greedily, highest priority first,
to the nearest depot that still has a free unit of the right kind. Every
assignment records whether the unit arrives before the deadline (peak rain
minus the lead time that task needs).
"""
from __future__ import annotations

from .geo import road_km

SPEED_KMPH = 18.0          # average city speed for a crew vehicle in rain
MOBILISE_MIN = 20          # time to load and leave the depot

# resource -> (minutes of work needed before peak, human label)
RESOURCES = {
    "desilting_crew": (120, "Desilting crew"),
    "pump_unit": (30, "Dewatering pump"),
    "traffic_team": (30, "Traffic police team"),
}

NEEDS_BY_TYPE = {
    "underpass": ["pump_unit", "traffic_team"],
    "low_lying_layout": ["pump_unit", "desilting_crew"],
    "lake_outflow": ["desilting_crew"],
    "junction": ["traffic_team", "desilting_crew"],
    "arterial": ["traffic_team", "desilting_crew"],
}

ACTION_TEXT = {
    "desilting_crew": "Clear inlets and culverts on {catchment} drain near {name}",
    "pump_unit": "Pre-position dewatering pump at {name}",
    "traffic_team": "Stand by for diversion at {name}; close if water exceeds 15 cm",
}


def build_tasks(assessed: list[dict]) -> list[dict]:
    tasks = []
    for h in assessed:
        if h["level"] not in ("Warning", "Critical"):
            continue
        needs = list(NEEDS_BY_TYPE.get(h["type"], ["desilting_crew"]))
        if h.get("blocked_drain_reports") and "desilting_crew" not in needs:
            needs.append("desilting_crew")
        peak = h["peak_hour_offset"] if h["peak_hour_offset"] is not None else 24
        for res in needs:
            urgency = 1.0 / (1.0 + max(peak, 0) / 6.0)
            priority = h["risk"] * (0.6 + 0.4 * urgency)
            if res == "desilting_crew" and h.get("blocked_drain_reports"):
                priority += 0.05
            tasks.append({
                "hotspot_id": h["id"],
                "hotspot": h["name"],
                "lat": h["lat"],
                "lng": h["lng"],
                "level": h["level"],
                "resource": res,
                "resource_label": RESOURCES[res][1],
                "action": ACTION_TEXT[res].format(name=h["name"], catchment=h["catchment"]),
                "peak_hour_offset": peak,
                "deadline_min": peak * 60 - RESOURCES[res][0],
                "priority": round(priority, 3),
            })
    return sorted(tasks, key=lambda t: t["priority"], reverse=True)


def allocate(tasks: list[dict], depots: list[dict], capacity: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """Greedy nearest-free-unit assignment. capacity is per depot per resource."""
    free = {d["id"]: {r: capacity.get(r, 0) for r in RESOURCES} for d in depots}
    assigned, unassigned = [], []
    for t in tasks:
        options = sorted(
            ((road_km(d["lat"], d["lng"], t["lat"], t["lng"]), d)
             for d in depots if free[d["id"]][t["resource"]] > 0),
            key=lambda x: x[0],
        )
        if not options:
            unassigned.append({**t, "status": "No unit free", "reason": "All units of this type committed to higher-priority spots"})
            continue
        km, depot = options[0]
        free[depot["id"]][t["resource"]] -= 1
        eta_min = round(MOBILISE_MIN + km / SPEED_KMPH * 60)
        on_time = eta_min <= t["deadline_min"]
        assigned.append({
            **t,
            "depot_id": depot["id"],
            "depot": depot["name"],
            "depot_lat": depot["lat"],
            "depot_lng": depot["lng"],
            "distance_km": round(km, 1),
            "eta_min": eta_min,
            "status": "Before peak" if on_time else "Late — dispatch now",
        })
    return assigned, unassigned


def plan(assessed: list[dict], depots: list[dict], capacity: dict[str, int]) -> dict:
    tasks = build_tasks(assessed)
    assigned, unassigned = allocate(tasks, depots, capacity)
    critical_ids = {h["id"] for h in assessed if h["level"] == "Critical"}
    covered = set()
    for hid in critical_ids:
        mine = [t for t in tasks if t["hotspot_id"] == hid]
        ok = [a for a in assigned if a["hotspot_id"] == hid and a["status"] == "Before peak"]
        if mine and len(ok) == len(mine):
            covered.add(hid)
    return {
        "assigned": assigned,
        "unassigned": unassigned,
        "critical_total": len(critical_ids),
        "critical_covered": len(covered),
    }
