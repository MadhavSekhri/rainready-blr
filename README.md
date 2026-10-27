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

Citizens can report a problem in English, Kannada or Hinglish. The agent classifies the report, **merges duplicates** (same type within 150 m and 6 h), routes it to the right department (GBA SWD, Traffic Police, Forest cell, BESCOM), and feeds it into the next risk run.

## Measurable outcome

**Lead time.** In the reactive model, crews move once flooding is reported, so lead time is roughly 0 hours. In the evening-thunderstorm scenario RainReady BLR gets **every Critical hotspot covered before peak rain with 8 hours of lead time**. The dashboard tracks this directly with three KPIs: *Critical spots covered before peak*, *Lead time to first peak* and *Tasks arriving on time*.

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000
```

Or with Docker: `docker build -t rainready . && docker run -p 8000:8000 rainready`

Run the tests: `pytest -q` (12 tests: risk model, planner, dedupe, multilingual classifier, offline fallback, API).

### Optional: IBM Granite briefs
```bash
export WATSONX_APIKEY=...        # IBM Cloud API key
export WATSONX_PROJECT_ID=...    # watsonx.ai project
# optional: WATSONX_URL (default us-south), WATSONX_MODEL (default ibm/granite-3-8b-instruct)
```
If these aren't set, or the call fails, the app falls back to its rules engine. It never breaks.

## Try it (2-minute demo)
1. **Run agent** on *Evening thunderstorm*: watch the SENSE → ASSESS → PLAN → ACT trace, then the red hotspots and dispatch lines on the map.
2. Click a hotspot in *Top hotspots*: the map flies there, and the popup shows the reasons and a 48-hour rain chart.
3. **Dispatch** tab: every task shows its depot, distance, ETA and whether it arrives *before peak*.
4. **Alerts** tab: English and Kannada SMS/WhatsApp-ready alerts with a send time 3 hours before the peak.
5. Switch to **Flash storm** (peak in about 2 hours): the agent honestly flags tasks that are *Late — dispatch now*.
6. Switch to **Deluge** and drop pumps to 1: watch tasks spill into *Unassigned — needs mutual aid*, then add pumps and re-run.
7. **Report** tab: submit "drain blocked with plastic" near a hotspot, submit it again (it gets merged), then re-run and see the priority change.
8. Select **Live forecast** to use real Open-Meteo data. If you're offline it falls back to a scenario and says so.

## Architecture

```
app/
  main.py              FastAPI: /api/run, /api/reports, /api/scenarios, static UI
  agent/
    sense.py           Open-Meteo live forecast (one batched call) + synthetic storm scenarios
    assess.py          explainable risk model (burst, soak, vulnerability, citizen signals)
    plan.py            task generation by location type + greedy nearest-free-unit allocation
    act.py             EN/KN resident alerts, commuter advisories, control-room brief
    reports.py         multilingual classifier, 150 m / 6 h dedupe, department routing
    llm.py             optional IBM Granite (watsonx.ai) brief writer with safe fallback
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
Hotspot coordinates and vulnerability values are **approximate and for demonstration only**. They are compiled from commonly reported waterlogging locations and should be replaced with official data before any real use. Scenarios are synthetic. Kannada alert templates should be reviewed by a native speaker before deployment.

MIT License.
