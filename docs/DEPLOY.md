# Deploying RainReady BLR (get a live link for judges)

## Option A: IBM Cloud Code Engine (fits the IBM story)
1. Sign in at cloud.ibm.com and open **Code Engine → Projects → Create** (any region, e.g. Chennai or Dallas).
2. In the project: **Applications → Create**.
   - Code: **Source code** → repository `https://github.com/MadhavSekhri/rainready-blr`, branch `main`, strategy **Dockerfile**.
   - Listening port: `8000`. Min instances: `0` (scale to zero), max `1`.
   - Optional environment variables: `WATSONX_APIKEY`, `WATSONX_PROJECT_ID` (switches the copilot to IBM Granite).
3. **Create**. When the build finishes, open the app URL and check `/api/health` returns `{"ok": true}`.

## Option B: Render (free, ~3 minutes)
1. Open `https://render.com/deploy?repo=https://github.com/MadhavSekhri/rainready-blr` and sign in with GitHub.
2. Leave the watsonx variables blank (or fill them), click **Apply**.
3. The free plan sleeps when idle; the first visit takes ~30 seconds to wake.

## After deploying
- Put the URL in the README, the deck (cover and closing slides) and the TechGig submission.
- Click **Live forecast** and **Historical replay** once on the live site to confirm Open-Meteo is reachable from the host.
- Reports are stored in SQLite inside the container; they reset when the host redeploys. That's fine for a demo.
