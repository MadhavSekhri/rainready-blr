"""ACT step: produce the outputs people actually receive.

- Resident alerts in English and Kannada (SMS/WhatsApp length)
- Commuter advisories for junctions, arterials and underpasses
- A situation brief for the ward control room
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


_BASE: datetime | None = None  # start of a historical replay window; None = now


def _clock(offset_h: int | None) -> str:
    if offset_h is None:
        return "later today"
    now = datetime.now(IST).replace(minute=0, second=0, microsecond=0)
    base = _BASE or now
    t = base + timedelta(hours=offset_h)
    if _BASE is not None:
        return t.strftime("%I %p, %d %b %Y").lstrip("0")
    day = "today" if t.date() == now.date() else "tomorrow"
    return f"{t.strftime('%I %p').lstrip('0')} {day}"


def resident_alert(h: dict) -> dict:
    when = _clock(h["peak_hour_offset"])
    if h["type"] == "underpass":
        en = (f"RainReady BLR {h['level'].upper()}: Heavy rain expected near {h['name']} around {when}. "
              f"The underpass may flood - avoid it and use an alternate route.")
        kn = (f"ಎಚ್ಚರಿಕೆ: {h['name']} ಬಳಿ {when} ಸುಮಾರಿಗೆ ಭಾರೀ ಮಳೆ ನಿರೀಕ್ಷೆ. "
              f"ಅಂಡರ್‌ಪಾಸ್‌ನಲ್ಲಿ ನೀರು ನಿಲ್ಲುವ ಸಾಧ್ಯತೆ - ಪರ್ಯಾಯ ಮಾರ್ಗ ಬಳಸಿ.")
    elif h["type"] == "low_lying_layout":
        en = (f"RainReady BLR {h['level'].upper()}: Heavy rain expected near {h['name']} around {when}. "
              f"Move vehicles to higher ground, keep valuables off the floor, and call the ward helpline if water enters homes.")
        kn = (f"ಎಚ್ಚರಿಕೆ: {h['name']} ಬಳಿ {when} ಸುಮಾರಿಗೆ ಭಾರೀ ಮಳೆ ನಿರೀಕ್ಷೆ. "
              f"ವಾಹನಗಳನ್ನು ಎತ್ತರದ ಸ್ಥಳಕ್ಕೆ ಸ್ಥಳಾಂತರಿಸಿ.")
    else:
        en = (f"RainReady BLR {h['level'].upper()}: Heavy rain expected near {h['name']} around {when}. "
              f"Expect waterlogging and slow traffic - plan travel early.")
        kn = (f"ಎಚ್ಚರಿಕೆ: {h['name']} ಬಳಿ {when} ಸುಮಾರಿಗೆ ಭಾರೀ ಮಳೆ ನಿರೀಕ್ಷೆ. "
              f"ನೀರು ನಿಲ್ಲುವ ಸಾಧ್ಯತೆ - ಪ್ರಯಾಣವನ್ನು ಮುಂಚಿತವಾಗಿ ಯೋಜಿಸಿ.")
    return {"hotspot_id": h["id"], "hotspot": h["name"], "level": h["level"], "send_at": _clock(max((h["peak_hour_offset"] or 6) - 3, 0)), "en": en, "kn": kn}


def commuter_advisory(h: dict) -> dict | None:
    if h["type"] not in ("underpass", "junction", "arterial"):
        return None
    when = _clock(h["peak_hour_offset"])
    action = "Likely closure" if h["type"] == "underpass" and h["level"] == "Critical" else "Expect slow traffic"
    return {"hotspot_id": h["id"], "hotspot": h["name"], "level": h["level"], "text": f"{action} at {h['name']} around {when}."}


def situation_brief(assessed: list[dict], plan: dict, sense_meta: dict) -> str:
    crit = [h for h in assessed if h["level"] == "Critical"]
    warn = [h for h in assessed if h["level"] == "Warning"]
    if not crit and not warn:
        return (f"Source: {sense_meta['label']}. No hotspot crosses the Warning threshold in the next 48 hours. "
                f"Routine monitoring only. Use this window to clear the {sum(1 for h in assessed if h['blocked_drain_reports'])} "
                f"spots with open blocked-drain reports.")
    top = (crit or warn)[0]
    zones = sorted({h["zone"] for h in crit + warn})
    late = [a for a in plan["assigned"] if a["status"] != "Before peak"]
    lines = [
        f"Source: {sense_meta['label']}.",
        f"{len(crit)} Critical and {len(warn)} Warning hotspots across {', '.join(zones)}.",
        f"Highest risk: {top['name']} (risk {top['risk']:.2f}), peak rain around {_clock(top['peak_hour_offset'])} - {'; '.join(top['reasons'][:2])}.",
        f"{len(plan['assigned'])} units dispatched; {plan['critical_covered']}/{plan['critical_total']} Critical spots fully covered before peak.",
    ]
    if late:
        lines.append(f"{len(late)} task(s) will arrive after the deadline - dispatch immediately: " + ", ".join(sorted({a['hotspot'] for a in late})[:4]) + ".")
    if plan["unassigned"]:
        lines.append(f"{len(plan['unassigned'])} task(s) have no free unit - request mutual aid from neighbouring zones.")
    return " ".join(lines)


def act(assessed: list[dict], plan: dict, sense_meta: dict) -> dict:
    global _BASE
    _BASE = datetime.fromisoformat(sense_meta["start"]) if sense_meta.get("source") == "historical" else None
    at_risk = [h for h in assessed if h["level"] in ("Warning", "Critical")]
    return {
        "alerts": [resident_alert(h) for h in at_risk],
        "advisories": [a for a in (commuter_advisory(h) for h in at_risk) if a],
        "brief": situation_brief(assessed, plan, sense_meta),
    }
