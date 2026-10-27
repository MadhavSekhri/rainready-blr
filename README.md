# RainReady BLR 🌧️ — agentic flood early-action for Bengaluru

> **Track 1: Smarter Streets, Better Living**, IBM Bobathon: Build for Bengaluru
> *Most flood response starts after the water does. RainReady BLR acts first.*

When a heavy shower hits Bengaluru, the same places go under water again and again: Silk Board, the Bellandur stretch of the ORR, Rainbow Drive, Sai Layout, the KR Circle underpass. Today the response is mostly **reactive**. Complaints come in, crews get dispatched, pumps arrive once the water is already knee-deep. Meanwhile citizens report the same blocked drain five times, and nobody joins those reports up with the forecast.

**RainReady BLR is an AI agent for a ward or zonal control room.** Every run, it:

| Step | What the agent does |
|---|---|
| **SENSE** | Pulls a 48-hour hourly rain forecast for 30 known waterlogging hotspots (live from Open-Meteo, or a replayable storm scenario) and loads open citizen reports. |
| **ASSESS** | Scores each hotspot's flood risk from the 3-hour burst intensity and 24-hour soak (anchored on IMD heavy-rain thresholds), weighted by local vulnerability. Blocked-drain reports nearby raise the risk too. Every score comes with plain-English reasons. |
| **PLAN** | Turns risk into tasks that fit the location type: underpass → pump + traffic team, low-lying layout → pump + desilting, lake outflow → clear the outfall. It assigns the nearest free unit from 6 depots, highest priority first, and checks whether each unit **arrives before the peak**. |
| **ACT** | Writes resident alerts in **English and ಕನ್ನಡ**, commuter advisories, and a control-room brief. The brief can optionally be written by **IBM Granite on watsonx.ai**. Tasks that can't be covered go to a mutual-aid list. |

**Ask RainReady (the agentic copilot).** Control-room staff ask questions in plain English, for example *"What if Mahadevapura depot loses its pumps and the deluge hits?"*. The copilot calls tools over the agent (`run_plan`, `get_hotspot`, `list_tasks`, `draft_alert`), re-plans, and answers with before/after numbers, the hotspots that lose cover, and which depot can lend units. With watsonx.ai credentials it runs on **IBM Granite with native tool calling**. Without them, an offline router calls the same tools, so the demo never breaks.

**Historical replay on real storms.** Replay real Bengaluru flood days (4–5 Sep 2022 ORR/Bellandur, 21–22 Oct 2024 Yelahanka, 18–19 May 2025 Sai Layout/Silk Board) using Open-Meteo's archive of what the weather models *forecast at the time*. This shows how much warning the agent would have given.

Citizens can report a problem in English, Kannada or Hinglish, with an optional photo, from the web or over **WhatsApp** (Twilio-compatible webhook). The agent classifies the report, **merges duplicates** (same type within 150 m and 6 h), routes it to the right department (GBA SWD, Traffic Police, Forest cell, BESCOM), and feeds it into the next risk run.

## Measurable outcome

**Lead time.** In the reactive model, crews move once flooding is reported, so lead time is roughly 0 hours. In the evening-thunderstorm scenario RainReady BLR gets **every Critical hotspot covered before peak rain with 8 hours of lead time**. The dashboard tracks this directly with three KPIs: *Critical spots covered before peak*, *Lead time to first peak* and *Tasks arriving on time*.

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000
```

Or with Docker: `docker build -t rainready . && docker run -p 8000:8000 rainready`

Run the tests: `pytest -q` (31 tests: risk model, planner and what-if overrides, copilot routing and Granite tool loop, historical replay, SQLite persistence, photo upload, WhatsApp webhook, API).

Reports are stored in SQLite at `data/rainready.db` (override with `RAINREADY_DB`); photos go to `data/uploads/`.

### Optional: IBM Granite (copilot + briefs)
```bash
export WATSONX_APIKEY=...        # IBM Cloud API key
export WATSONX_PROJECT_ID=...    # watsonx.ai project
# optional: WATSONX_URL (default us-south), WATSONX_CHAT_MODEL (copilot, default ibm/granite-3-8b-instruct),
#           WATSONX_MODEL (brief writer, default ibm/granite-3-8b-instruct)
```
If these aren't set, or a call fails, the app falls back to its rules engine. It never breaks.

### Optional: WhatsApp reporting
Create a Twilio WhatsApp sandbox and set its "When a message comes in" webhook to `https://<your-host>/api/whatsapp`. Citizens send a description and photo, then share their location; the bot replies with a ticket number or tells them the issue is already reported.

## Try it (2-minute demo)
1. **Run agent** on *Evening thunderstorm*: watch the SENSE → ASSESS → PLAN → ACT trace, then the red hotspots and dispatch lines on the map.
2. Click a hotspot in *Top hotspots*: the map flies there, and the popup shows the reasons and a 48-hour rain chart.
3. **Dispatch** tab: every task shows its depot, distance, ETA and whether it arrives *before peak*.
4. **Alerts** tab: English and Kannada SMS/WhatsApp-ready alerts with a send time 3 hours before the peak.
5. Switch to **Flash storm** (peak in about 2 hours): the agent honestly flags tasks that are *Late — dispatch now*.
6. Switch to **Deluge** and drop pumps to 1: watch tasks spill into *Unassigned — needs mutual aid*, then add pumps and re-run.
7. **Report** tab: submit "drain blocked with plastic" near a hotspot, submit it again (it gets merged), then re-run and see the priority change.
8. Select **Live forecast** to use real Open-Meteo data. If you're offline it falls back to a scenario and says so.
9. **Ask ✦** tab: click *"What if Bommanahalli depot loses its pumps?"*. Watch the tool call, the before/after answer, the purple what-if banner and the re-drawn map. Try *"Draft a Kannada alert for KR Circle Underpass"*.
10. Select **Historical replay** and pick *4–5 Sep 2022*: the agent runs on what the forecast said that night.

## Architecture

```
app/
  main.py              FastAPI: /api/run, /api/ask, /api/reports (+photos), /api/whatsapp, static UI
  agent/
    sense.py           Open-Meteo live forecast, historical-forecast replay of real storms, synthetic scenarios
    assess.py          explainable risk model (burst, soak, vulnerability, citizen signals)
    plan.py            task generation by location type + greedy nearest-free-unit allocation
    act.py             EN/KN resident alerts, commuter advisories, control-room brief
    reports.py         multilingual classifier, 150 m / 6 h dedupe, department routing, SQLite store
    llm.py             optional IBM Granite (watsonx.ai) brief writer with safe fallback
    copilot.py         Ask RainReady: tool-calling copilot (Granite) + offline router over the same tools
    pipeline.py        the agent loop + human-readable trace + KPIs
  data/hotspots.json   30 hotspots, 6 depots (approximate demo data)
  static/              vanilla JS + Leaflet (vendored), offline schematic basemap
tests/                 pytest suite
docs/                  problem statement, IBM Bob playbook
```

Design choices: no API keys are needed to run it. It works offline, with a schematic Bengaluru basemap when map tiles can't load. Every decision is explainable, and the whole thing runs in one process.

## How IBM Bob was used
See [`docs/BOB_PLAYBOOK.md`](docs/BOB_PLAYBOOK.md). Bob was used in Ask, Plan and Agent modes to understand the codebase, plan and implement features with tests, and review the code. *(Add your Bob session screenshots and summary here after completing the playbook.)*

## Roadmap
- Plug in the official GBA vulnerable-spot list, live storm-water-drain sensor levels and lake-level telemetry.
- Integrate WhatsApp Business / SMS gateways for alerts, and a citizen bot that accepts photos.
- Learn vulnerability weights from confirmed waterlogging after each storm.
- Hand off to traffic-police diversion plans and BMTC route advisories.

## Data & honesty notes
Historical replays use archived *model* forecasts at roughly 1–10 km resolution, which smooth out cloudbursts, so replayed peaks understate the real rain. Hotspot coordinates and vulnerability values are **approximate and for demonstration only**. They are compiled from commonly reported waterlogging locations and should be replaced with official data before any real use. Scenarios are synthetic. Kannada alert templates should be reviewed by a native speaker before deployment.

MIT License.
