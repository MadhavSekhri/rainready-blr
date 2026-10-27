# IBM Bob playbook (≈60–90 minutes)

Judges score a **"Bob Story": a short demo showing how Bob was used.** Earlier IBM Bob hackathons also weighted *depth of Bob adoption* heavily, meaning Bob is part of the workflow and not bolted on at the end. Do these steps in **IBM Bob** (the IDE) with this repo open. **Screen-record each session** (OBS or the built-in recorder) and commit after each step, so the Git history shows Bob's work.

> Setup: install Bob from bob.ibm.com, log in with your IBMid, then open the `rainready-blr` folder.
> Run `pip install -r requirements.txt && pytest -q` in Bob's terminal first. All 12 tests should pass.

---

### 1. Ask mode: understand the codebase (≈5 min) 🎥
Prompt:
```
Explain how the SENSE → ASSESS → PLAN → ACT agent loop works in this repo. Walk through app/agent/pipeline.py and show how a citizen blocked-drain report changes a hotspot's risk and the dispatch plan.
```
Screenshot Bob's explanation. It's good material for the "Bob Story" slide.

### 2. Plan mode, then Agent mode: build a new feature (≈20 min) 🎥 ⭐ *main Bob Story*
Prompt in **Plan** mode:
```
Plan a new feature: automatic escalation. If a blocked-drain citizen report stays open for more than 24 hours AND the hotspot it is near is forecast to reach Warning or Critical, escalate it to the zonal executive engineer. Add an "escalations" list to the pipeline output, a new trace line in the ACT step, an "Escalations" section in the Alerts tab, and pytest tests. Keep it consistent with the existing code style.
```
Review the plan, then switch to **Agent** mode: `Implement the plan.` Let Bob run `pytest -q`, fix anything that fails, then commit:
`git commit -am "feat: escalation of stale drain reports (built with IBM Bob)"`.

### 2b. Agent mode: secure the WhatsApp webhook (≈10 min) 🎥
```
In app/main.py, validate Twilio's X-Twilio-Signature header on /api/whatsapp when TWILIO_AUTH_TOKEN is set (reject with 403 if invalid), without adding the twilio package. Add pytest tests for a valid and an invalid signature.
```

### 3. Agent mode: resolve-report button (≈10 min) 🎥
```
In the Report tab of app/static/app.js, add a "Mark resolved" button to each open report that calls POST /api/reports/{id}/resolve, refreshes the list, and re-runs the agent so the map updates. Add an API test for the resolve endpoint.
```
Commit afterwards.

### 4. Agent mode: rain replay timeline (≈15 min) 🎥 *(optional, big wow factor)*
```
Add a time slider under the map (0–48h). Moving it recolours each hotspot by the rain falling in that hour, using the existing data.rain series, so users can watch the storm move across Bengaluru. Use no new libraries.
```

### 5. Code review with Bob (≈10 min) 🎥
Use Bob's code review / findings feature (or Ask mode):
```
Review this repository for bugs, security issues (input validation, XSS in the front end) and edge cases. List the findings, then fix the important ones.
```
Commit as `fix: issues found in IBM Bob review`.

### 6. Docs and deploy (≈10 min)
```
Update README.md with the new features, and add deployment steps for IBM Cloud Code Engine using the existing Dockerfile.
```
Then replace the placeholder line in the README's "How IBM Bob was used" section with a 4–5 line summary of what Bob did in steps 1–5. If you used **Bobalytics** or session stats, add the numbers.

---

## Recording the "Bob Story" (60–90 s)
Cut the recordings from step 2 (plan, then implement, then tests passing) and step 5 (review, then fix) into one clip. Suggested voice-over:
> "We built RainReady BLR with IBM Bob. Bob explained our agent loop in Ask mode, planned the escalation feature in Plan mode, then implemented it, wrote the tests and fixed a failing case in Agent mode. Finally, Bob's review caught *[the issue it found]*, and we fixed it. That took a feature from idea to tested code in under 20 minutes."

Once these steps are done, change the footer in `app/static/index.html` to "Built with IBM Bob for the IBM Bobathon".
