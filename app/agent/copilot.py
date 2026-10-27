"""Ask RainReady: a tool-using control-room copilot.

The copilot answers questions such as "What if Mahadevapura depot loses its
pumps?" by calling tools over the agent pipeline (re-plan, inspect a hotspot,
list late tasks, draft an alert) and explaining the result.

Two engines, same tools:
- IBM Granite on watsonx.ai with native tool calling (when WATSONX_APIKEY and
  WATSONX_PROJECT_ID are set).
- An offline rules router that maps the question to the same tool calls, so
  the feature always works in a demo with no keys or network.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from typing import Any

import httpx

from . import llm, pipeline
from .act import resident_alert
from .plan import RESOURCES
from .sense import HISTORICAL_EVENTS, SCENARIOS

DEPOT_ALIASES = {
    "D-M": ["mahadevapura", "whitefield", "marathahalli"],
    "D-B": ["bommanahalli", "hsr", "silk board", "electronic city"],
    "D-E": ["east", "indiranagar"],
    "D-S": ["south", "jayanagar"],
    "D-W": ["west", "vijayanagar"],
    "D-Y": ["yelahanka", "hebbal", "north"],
}
RESOURCE_WORDS = {
    "pump_unit": ["pump"],
    "desilting_crew": ["desilt", "crew", "jcb"],
    "traffic_team": ["traffic", "police", "marshal"],
}
GENERIC = {"junction", "road", "layout", "underpass", "flyover", "signal", "gate", "town", "depot", "cross",
           "railway", "loop", "bus", "phase", "sector", "check", "post", "main", "satellite"}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "all": 99, "every": 99}


# ---------------------------------------------------------------- tools
class Toolbox:
    """Tools the copilot can call. Holds the baseline run and the latest run."""

    def __init__(self, settings: dict, reports: list[dict]):
        self.settings = settings
        self.reports = reports
        self.baseline = pipeline.run(reports=reports, **settings)
        self.latest = self.baseline
        self.changed = False

    # -- helpers
    def _kpi_line(self, r: dict) -> str:
        k = r["kpis"]
        return (f"{k['critical']} Critical / {k['warning']} Warning hotspots; {k['critical_covered']}/{k['critical_total']} "
                f"Critical covered before peak; {k['units_dispatched']} units dispatched; "
                f"{len(r['plan']['unassigned'])} task(s) need mutual aid; {k['on_time_pct']}% on time")

    def find_hotspot(self, name: str) -> dict | None:
        q = name.lower()
        best, best_score = None, 0.0
        for h in self.latest["hotspots"]:
            words = [w for w in re.findall(r"[a-z]+", h["name"].lower()) if len(w) >= 2 and w not in GENERIC]
            hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", q))
            score = hits / max(len(words), 1) + 0.01 * hits
            if hits and score > best_score:
                best, best_score = h, score
        if best:
            return best
        names = {h["name"].lower(): h for h in self.latest["hotspots"]}
        m = difflib.get_close_matches(q, list(names), n=1, cutoff=0.5)
        return names[m[0]] if m else None

    # -- tools
    def run_plan(self, scenario: str | None = None, source: str | None = None, date: str | None = None,
                 capacity: dict | None = None, depot_overrides: dict | None = None) -> dict:
        s = dict(self.settings)
        if scenario:
            s["scenario"], s["source"] = scenario, "scenario"
        if source:
            s["source"] = source
        if date:
            s["date"], s["source"] = date, "historical"
        if capacity:
            s["capacity"] = {**(s.get("capacity") or {}), **capacity}
        if depot_overrides:
            merged = {k: dict(v) for k, v in (s.get("depot_overrides") or {}).items()}
            for d, res in depot_overrides.items():
                merged.setdefault(d, {}).update(res)
            s["depot_overrides"] = merged
        self.latest = pipeline.run(reports=self.reports, **s)
        self.changed = True
        b, n = self.baseline, self.latest
        newly_uncovered = sorted({t["hotspot"] for t in n["plan"]["unassigned"]} - {t["hotspot"] for t in b["plan"]["unassigned"]})
        spare = {d: {r: v for r, v in res.items() if v > 0} for d, res in n["plan"]["spare"].items()}
        needed = sorted({t["resource"] for t in n["plan"]["unassigned"]})
        return {
            "data": n["sense"]["label"],
            "note": n["sense"].get("note", ""),
            "needed_resources": needed,
            "before": self._kpi_line(b),
            "after": self._kpi_line(n),
            "newly_needing_mutual_aid": newly_uncovered,
            "late_tasks": [f"{t['resource_label']} -> {t['hotspot']}" for t in n["plan"]["assigned"] if t["status"] != "Before peak"][:6],
            "depots_with_spare_units": {next(d["name"] for d in n["depots"] if d["id"] == k): v for k, v in spare.items() if v},
            "top_hotspots": [f"{h['name']} ({h['level']}, risk {h['risk']:.2f}, peak in {h['peak_hour_offset']}h)"
                             for h in n["hotspots"][:5]],
        }

    def get_hotspot(self, name: str) -> dict:
        h = self.find_hotspot(name)
        if not h:
            return {"error": f"No hotspot matching '{name}'"}
        tasks = [t for t in self.latest["plan"]["assigned"] + self.latest["plan"]["unassigned"] if t["hotspot_id"] == h["id"]]
        return {
            "name": h["name"], "zone": h["zone"], "type": h["type"].replace("_", " "), "level": h["level"],
            "risk": h["risk"], "reasons": h["reasons"], "max_3h_mm": h["max_3h_mm"], "total_24h_mm": h["total_24h_mm"],
            "peak_hour_offset": h["peak_hour_offset"],
            "tasks": [f"{t['resource_label']}: {t.get('status')}" + (f" from {t['depot']} (ETA {t['eta_min']} min)" if t.get("depot") else "")
                      for t in tasks],
        }

    def list_tasks(self, status: str = "late") -> dict:
        p = self.latest["plan"]
        if status == "unassigned":
            items = p["unassigned"]
        elif status == "late":
            items = [t for t in p["assigned"] if t["status"] != "Before peak"]
        else:
            items = p["assigned"]
        return {"status": status, "count": len(items),
                "tasks": [f"{t['resource_label']} -> {t['hotspot']} ({t['level']}, peak in {t['peak_hour_offset']}h)" for t in items[:10]]}

    def draft_alert(self, hotspot: str, language: str = "en") -> dict:
        h = self.find_hotspot(hotspot)
        if not h:
            return {"error": f"No hotspot matching '{hotspot}'"}
        a = resident_alert(h)
        return {"hotspot": h["name"], "level": h["level"], "send_at": a["send_at"],
                "text": a["kn"] if language == "kn" else a["en"]}

    def list_depots(self) -> dict:
        return {d["id"]: d["name"] for d in self.baseline["depots"]}

    def call(self, name: str, args: dict) -> dict:
        fn = {"run_plan": self.run_plan, "get_hotspot": self.get_hotspot, "list_tasks": self.list_tasks,
              "draft_alert": self.draft_alert, "list_depots": self.list_depots}.get(name)
        if not fn:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}


TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "run_plan",
        "description": "Re-run the flood agent with changed conditions (what-if) and compare with the current plan.",
        "parameters": {"type": "object", "properties": {
            "scenario": {"type": "string", "enum": list(SCENARIOS)},
            "source": {"type": "string", "enum": ["scenario", "live", "historical"]},
            "date": {"type": "string", "description": "YYYY-MM-DD for a historical replay"},
            "capacity": {"type": "object", "description": "Units per depot for every depot, e.g. {\"pump_unit\": 2}"},
            "depot_overrides": {"type": "object", "description": "Units for specific depots, e.g. {\"D-M\": {\"pump_unit\": 0}}. Depot ids: D-E East, D-S South, D-M Mahadevapura, D-B Bommanahalli, D-W West, D-Y Yelahanka."},
        }}}},
    {"type": "function", "function": {
        "name": "get_hotspot", "description": "Risk, reasons, rain and assigned tasks for one hotspot.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "list_tasks", "description": "List dispatch tasks that are late, unassigned (need mutual aid) or all.",
        "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["late", "unassigned", "all"]}}}}},
    {"type": "function", "function": {
        "name": "draft_alert", "description": "Draft the resident alert for a hotspot in English (en) or Kannada (kn).",
        "parameters": {"type": "object", "properties": {"hotspot": {"type": "string"}, "language": {"type": "string", "enum": ["en", "kn"]}},
                       "required": ["hotspot"]}}},
    {"type": "function", "function": {
        "name": "list_depots", "description": "List depot ids and names.", "parameters": {"type": "object", "properties": {}}}},
]

SYSTEM_PROMPT = (
    "You are RainReady BLR, the flood early-action copilot for a Bengaluru ward control room. "
    "Always use the tools to get facts; never invent numbers. For what-if questions call run_plan with the change "
    "and report the before/after numbers, which hotspots lose cover, and one concrete recommendation (for example "
    "which depot has spare units to lend). Answer in at most 5 short sentences."
)


# ---------------------------------------------------------------- rules router (offline engine)
def _num_before(text: str, word_pos: int) -> int | None:
    before = text[max(0, word_pos - 25):word_pos]
    m = re.findall(r"(\d+|one|two|three|four|five|all|every)\s*(?:of\s*(?:its|the)\s*)?$", before.strip())
    if not m:
        m = re.findall(r"(\d+|one|two|three|four|five|all|every)", before)
    if not m:
        return None
    v = m[-1]
    return int(v) if v.isdigit() else NUMBER_WORDS[v]


def route(question: str, tb: Toolbox) -> list[tuple[str, dict]]:
    q = question.lower()
    cap = {**pipeline.DEFAULT_CAPACITY, **(tb.settings.get("capacity") or {})}
    args: dict = {}

    # 1. Which weather? (historical replay, scenario or live)
    for date, label in HISTORICAL_EVENTS.items():
        month = label.split(":")[0].split()[-2].lower()
        if date[:4] in q and (month in q or "replay" in q or "flood" in q):
            args["date"] = date
    if "date" not in args:
        for key, words in {"flash_storm": ["flash"], "deluge": ["deluge", "cloudburst", "prolonged"],
                           "evening_thunderstorm": ["thunderstorm"], "dry": ["dry day", "no rain"]}.items():
            if any(w in q for w in words):
                args["scenario"] = key
        if "live" in q and ("forecast" in q or "real" in q):
            args["source"] = "live"

    # 2. Which resources change?
    resources = [r for r, words in RESOURCE_WORDS.items() if any(w in q for w in words)]
    depots = [d for d, aliases in DEPOT_ALIASES.items() if any(re.search(rf"\b{re.escape(a)}\b", q) for a in aliases)]
    losing = any(w in q for w in ["lose", "loses", "lost", "without", "broken", "unavailable", "fail", "breaks down"])
    adding = any(w in q for w in ["add", "extra", "double", "borrow", "one more", "two more"])
    if resources and (losing or adding or "only" in q):
        overrides, global_cap = {}, {}
        for r in resources:
            pos = min((q.find(w) for w in RESOURCE_WORDS[r] if w in q), default=0)
            n = _num_before(q, pos)
            targets = depots or [None]
            for d in targets:
                cur = (tb.settings.get("depot_overrides") or {}).get(d, {}).get(r, cap[r]) if d else cap[r]
                if "only" in q and n is not None:
                    new = n
                elif losing:
                    new = 0 if (d and n in (None, 99)) else max(0, cur - (n if n not in (None, 99) else cur if n == 99 else 1))
                elif "double" in q:
                    new = cur * 2
                else:
                    new = cur + (n if n not in (None, 99) else 1)
                if d:
                    overrides.setdefault(d, {})[r] = new
                else:
                    global_cap[r] = new
        if overrides:
            args["depot_overrides"] = overrides
        if global_cap:
            args["capacity"] = global_cap
    if args:
        return [("run_plan", args)]

    # 3. Other intents
    if any(w in q for w in ["alert", "message", "sms", "whatsapp"]):
        h = tb.find_hotspot(q)
        if h:
            lang = "kn" if any(w in q for w in ["kannada", "ಕನ್ನಡ"]) else "en"
            return [("draft_alert", {"hotspot": h["name"], "language": lang})]
    if any(w in q for w in ["late", "delay", "on time", "miss"]):
        return [("list_tasks", {"status": "late"})]
    if any(w in q for w in ["unassigned", "mutual aid", "not covered", "uncovered", "gap", "no unit", "no free", "without a unit"]):
        return [("list_tasks", {"status": "unassigned"})]
    h = tb.find_hotspot(q)
    if h:
        return [("get_hotspot", {"name": h["name"]})]
    return [("run_plan", {})]


def compose(question: str, calls: list[tuple[str, dict, dict]]) -> str:
    parts = []
    for name, args, res in calls:
        if "error" in res:
            parts.append(res["error"] + ".")
        elif name == "run_plan":
            if not args:
                parts.append(f"Current situation ({res['data']}): {res['after']}. Top risk: {', '.join(res['top_hotspots'][:3])}.")
                continue
            if res.get("note"):
                parts.append(f"Note: {res['note']}")
            parts.append(f"Before: {res['before']}.")
            parts.append(f"After the change: {res['after']}.")
            if res["newly_needing_mutual_aid"]:
                parts.append("Losing cover: " + ", ".join(res["newly_needing_mutual_aid"]) + ".")
            if res["late_tasks"]:
                parts.append("Late tasks: " + "; ".join(res["late_tasks"][:3]) + ".")
            if args.get("date") or args.get("scenario") or args.get("source"):
                parts.append("Highest risk now: " + "; ".join(res["top_hotspots"][:3]) + ".")
            spare = res["depots_with_spare_units"]
            if res["needed_resources"]:
                offers = [(dname, {r: units[r] for r in res["needed_resources"] if units.get(r)}) for dname, units in spare.items()]
                offers = [o for o in offers if o[1]]
                if offers:
                    dname, units = offers[0]
                    parts.append(f"Recommendation: request mutual aid from {dname}, which still has "
                                 + ", ".join(f"{n} spare {RESOURCES[r][1].lower()}{'s' if n > 1 else ''}" for r, n in units.items()) + ".")
                else:
                    parts.append("Recommendation: no depot has spare units of the type needed. Escalate to the zonal "
                                 "commissioner for contractor pumps or crews.")
        elif name == "get_hotspot":
            peak = f"peak rain in {res['peak_hour_offset']}h" if res["peak_hour_offset"] is not None else "no rain peak"
            parts.append(f"{res['name']} ({res['zone']}, {res['type']}) is {res['level']} at risk {res['risk']:.2f}, {peak}: "
                         + "; ".join(res["reasons"]) + ".")
            if res["tasks"]:
                parts.append("Tasks: " + "; ".join(res["tasks"]) + ".")
        elif name == "list_tasks":
            label = {"late": "arrive after the deadline", "unassigned": "have no free unit"}.get(res["status"], "are assigned")
            parts.append(f"{res['count']} task(s) {label}" + (": " + "; ".join(res["tasks"][:6]) + "." if res["count"] else "."))
        elif name == "draft_alert":
            parts.append(f"Alert for {res['hotspot']} (send at {res['send_at']}): {res['text']}")
    return "\n".join(parts) or "I couldn't find anything to act on. Try asking about a hotspot, a depot or a scenario."


# ---------------------------------------------------------------- Granite engine
def _granite_chat(messages: list[dict]) -> dict:
    token = llm._token(os.environ["WATSONX_APIKEY"])
    r = httpx.post(
        f"{os.getenv('WATSONX_URL', llm.DEFAULT_URL)}/ml/v1/text/chat?version=2024-10-08",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"model_id": os.getenv("WATSONX_CHAT_MODEL", "ibm/granite-3-8b-instruct"),
              "project_id": os.environ["WATSONX_PROJECT_ID"], "messages": messages, "tools": TOOL_SPECS,
              "tool_choice_option": "auto", "max_tokens": 400, "temperature": 0},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def ask_granite(question: str, tb: Toolbox) -> tuple[str, list]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    steps = []
    for _ in range(4):
        msg = _granite_chat(messages)
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip(), steps
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            args = json.loads(c["function"].get("arguments") or "{}")
            res = tb.call(c["function"]["name"], args)
            steps.append((c["function"]["name"], args, res))
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res)[:4000]})
    return compose(question, steps), steps


# ---------------------------------------------------------------- entry point
def ask(question: str, settings: dict, reports: list[dict]) -> dict:
    tb = Toolbox(settings, reports)
    engine, answer, steps = "rules", "", []
    if llm.enabled():
        try:
            answer, steps = ask_granite(question, tb)
            engine = "granite"
        except Exception:
            tb = Toolbox(settings, reports)
            steps = []
    if engine == "rules":
        for name, args in route(question, tb):
            steps.append((name, args, tb.call(name, args)))
        answer = compose(question, steps)
    return {
        "answer": answer,
        "engine": "IBM Granite on watsonx.ai (tool calling)" if engine == "granite" else "Offline rules router (same tools)",
        "steps": [{"tool": n, "args": a, "result": r} for n, a, r in steps],
        "run": tb.latest if tb.changed else None,
    }
