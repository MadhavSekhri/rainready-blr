# RainReady BLR — Problem statement & solution

**Track:** 01 · Smarter Streets, Better Living (neighbourhood flood alerts, pothole/drain issue tracking)
**Team:** Madhav Sekhri
**Repository:** https://github.com/MadhavSekhri/rainready-blr
**Demo video:** <add YouTube/Drive link>

## 1. Problem: who faces it, and what needs to improve?

Every heavy shower floods the same Bengaluru spots: Silk Board, the ORR near Bellandur, Rainbow Drive on Sarjapur Road, Sai Layout in Horamavu, Koramangala ST Bed, and the KR Circle and Okalipuram underpasses.

- **Residents and commuters** lose hours stuck in traffic, homes in low-lying layouts get water inside, and people drive into flooded underpasses.
- **Ward engineers and the control room** react to complaints after the water has already risen. Crews and pumps are limited, so they get sent to whoever complained loudest, not to where the next storm will do the most damage.
- **Citizen reports are noisy.** The same blocked drain gets reported many times on different channels, and nobody links those reports to the rain forecast.

The rain forecast already exists hours in advance, and so do the flood-prone spots and the citizen reports. **What's missing is something that joins them up and decides what to do *before* the rain peaks.**

## 2. Solution

RainReady BLR is an **agentic early-action system** for ward and zonal control rooms. It runs a loop of SENSE → ASSESS → PLAN → ACT:

1. **Sense:** a 48-hour hourly rain forecast for each known hotspot (live Open-Meteo data, or replayable storm scenarios), plus open citizen reports.
2. **Assess:** an explainable 0–1 flood risk per hotspot. It combines the 3-hour burst intensity and the 24-hour total (anchored on IMD heavy-rain categories), the local history of waterlogging, and nearby blocked-drain reports. Every score comes with reasons such as "Intense burst: 70 mm in 3h" or "2 citizen reports of blocked drains nearby".
3. **Plan:** turns risk into the right tasks for each kind of location (pump and traffic team for underpasses, desilting for lake outflows, and so on). It allocates the nearest free crew from 6 depots, highest priority first, and checks whether each crew **arrives before the peak**. Tasks it can't cover go to a mutual-aid list.
4. **Act:** produces SMS/WhatsApp-ready resident alerts in **English and Kannada**, timed 3 hours before the peak, plus commuter advisories and a control-room brief. The brief can optionally be written by IBM Granite on watsonx.ai.

**Ask RainReady:** a tool-calling copilot (IBM Granite on watsonx.ai, with an offline fallback) answers what-if questions such as "What if Bommanahalli depot loses its pumps?" by re-planning and reporting before/after numbers, hotspots losing cover and which depot can lend units.

**Historical replay:** the agent can be replayed on real Bengaluru flood days (4–5 Sep 2022, 21–22 Oct 2024, 18–19 May 2025) using archived model forecasts.

**Citizen intake:** reports in English, Kannada or Hinglish are classified (blocked drain, waterlogging, tree fall, electrical hazard). Electrical hazards are always prioritised. Reports can come from the web or WhatsApp, with photos. Duplicates within 150 m and 6 hours are merged, and each report is routed to the right agency (GBA SWD, Traffic Police, Forest cell or BESCOM). Reports feed straight into the next risk run.

## 3. Prototype

The prototype is a working FastAPI service with a Leaflet dashboard. It shows a live agent trace, a risk map with dispatch lines, a dispatch plan, bilingual alerts and a report form, plus the Ask RainReady copilot, historical replays and WhatsApp intake. It runs fully offline (scenario data and a schematic basemap) and has 31 automated tests. It needs no API keys to run.

## 4. Impact: one measurable outcome

**Lead time before peak rain at Critical hotspots: from about 0 hours (reactive) to 8 or more hours.** In the evening-thunderstorm scenario, all 5 Critical hotspots have their pumps, desilting crews and traffic teams in place before the peak, with 100% of tasks arriving on time. The dashboard reports this as KPIs on every run, so a pilot ward can measure it from day one. Secondary outcomes: fewer duplicate complaint tickets, and alerts sent before the rain instead of after.

## 5. Feasibility

It uses free, open data sources and no paid dependencies. It deploys as one container and adds no extra work for citizens. A pilot in a single zone (for example Mahadevapura or Bommanahalli) needs only the official vulnerable-spot list and the depot and crew roster.
