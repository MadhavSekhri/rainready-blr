# TechGig submission text (paste-ready)

**Title:** RainReady BLR: agentic flood early-action for Bengaluru
**Track:** 01 · Smarter Streets, Better Living
**Tagline:** Crews, pumps and alerts in place before the rain peaks, not after the water rises.

**Problem (who faces it, what needs to improve):**
The same Bengaluru spots flood with every heavy shower: Silk Board, the ORR at Bellandur, Rainbow Drive, Sai Layout, the KR Circle underpass. Residents and commuters get stranded and homes take in water, while ward control rooms react to complaints after the water has risen, sending limited crews and pumps to whoever complains first. Citizen reports arrive duplicated and disconnected from the rain forecast.

**Solution:**
RainReady BLR is an AI agent for ward control rooms. It senses a 48-hour rain forecast for 30 hotspots, assesses an explainable flood risk for each (rain burst, 24-hour total, flood history, citizen reports), plans which depot sends which pump, desilting crew or traffic team so they arrive before the peak, and acts by writing resident alerts in English and Kannada plus a control-room brief. Staff can ask what-if questions in plain English ("What if Bommanahalli depot loses its pumps?"); a tool-calling copilot on IBM Granite (watsonx.ai) re-plans and explains the impact. Citizens report problems from the web or WhatsApp with photos; duplicates are merged and routed to the right department. The agent can replay real Bengaluru flood days (Sep 2022, Oct 2024, May 2025) from archived forecasts.

**Bob Story:** [Fill in after the Bob playbook: which Bob modes you used, what Bob planned/built/tested/reviewed, time taken.]

**Impact (one measurable outcome):**
Lead time before peak rain at Critical hotspots goes from about 0 hours (reactive) to 8+ hours, with every Critical spot covered before the peak in the evening-thunderstorm scenario. The dashboard measures this on every run.

**Links:**
- Code: https://github.com/MadhavSekhri/rainready-blr
- Live demo: [deploy link]
- Demo video: [YouTube/Drive link]
