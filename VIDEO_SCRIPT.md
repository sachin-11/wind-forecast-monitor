# Video script: Wind Forecast Monitor (max 10 min)

Recording setup: screen + face cam (Loom or OBS), 1080p, browser at 100% zoom. Keep the deployed app, the GitHub repo and VS Code open in separate tabs. Upload to YouTube as **Unlisted**.

Before recording, open the live app and note the real numbers on each tab. The numbers below are from the live January 2026 data I checked, so confirm them on screen and say whatever the app shows.

---

## PART 1: Client pitch (target 4:30, max 5:00)

Audience: the client's day-ahead trading team. Tone: business, outcome-first, no code.

**[0:00 – 0:30] Hook, on the Forecast monitor tab**
> "Hi, I'm Sachin. Every morning your team decides how much power to buy for tomorrow, and the biggest unknown in that decision is wind. Over the last few weeks we've built a tool that answers two questions: what does the wind forecast say, and how much should you trust it? Let me show you what we found for January."

**[0:30 – 1:45] Forecast monitor**
- Click **Week 2**. Point at the black line (actual) and the dashed blue line (forecast).
> "The black line is what the wind actually generated, every half hour. The dashed line is the forecast, and only the forecast that was available at decision time, so there's no hindsight."
- Switch to **Day-ahead cut-off**.
> "This is exactly your situation: the latest forecast published before 9 a.m. the day before delivery."
- Point at the KPI cards and the red/green error bars.
> "On average the forecast misses by about 2 GW an hour, and the red bars show something important: it's mostly too high. Wind under-delivers against the forecast."

**[1:45 – 3:00] Accuracy analysis**
- Point at the horizon curve.
> "The further ahead the forecast, the bigger the error. At your decision point, about 28 hours ahead on average, the typical miss is around 2.1 GW."
- Point at the bias insight.
> "The real finding is that across January the forecast was consistently about 1.8 GW too high, roughly 16% of average wind output. If you took it at face value, you'd systematically under-buy and cover the gap later at higher prices."
- Point at the teal 'bias-corrected' line.
> "Because that bias is persistent, we built a simple correction that learns from the previous two weeks, using only data you'd already have. It cuts the error by about a third, from roughly 2.1 to 1.4 GW, at zero extra cost."

**[3:00 – 4:15] Day-ahead planner (the "wow" moment)**
- Pick a day and untick **"Show what actually happened"**.
> "This replays a real decision. On the 14th at 9 a.m., this is what you'd have seen: the raw forecast, our corrected plan, and a shaded band showing the likely range based on recent errors."
- Point at **Suggested extra cover**.
> "Instead of a gut-feel safety margin, the tool tells you how much extra energy to secure: this many GWh."
- Tick **Show what actually happened**.
> "And here's what really happened. The actual sits inside the band, so the cover would have been enough."
- Click → to the next day once to show it's interactive.

**[4:15 – 4:50] Close**
> "So in short: you get one place to see the forecast you're really deciding on, a clear measure of how wrong it tends to be, and a data-driven safety margin. The next step I'd suggest is a pilot: run it alongside your current process for a month and compare purchase costs. Happy to take questions."

---

## PART 2: Technical walkthrough for the tech lead (target 4:30)

Audience: internal tech lead. Tone: structured and precise. Show code.

**[5:00 – 5:30] Overview, on the README architecture diagram**
> "Now for the technical review. It's a React and TypeScript SPA talking to a FastAPI backend. The backend pulls two Elexon BMRS streams: FUELHH for actuals and WINDFOR for forecasts. It's deployed as a single Vercel project, with the SPA as static files and FastAPI as a Python serverless function. Docker Compose runs the same stack locally."

**[5:30 – 6:00] Backend layering, in VS Code `backend/app`**
> "There are three layers. `data_sources.py` handles I/O: an Elexon client with retries, exponential backoff and a TTL cache, plus a synthetic source with the same schema so tests never hit the network. `analysis.py` holds pure pandas functions with no I/O, which makes them easy to test and lets the notebook reuse them. `main.py` is a thin HTTP layer with validation."

**[6:00 – 7:15] Core logic: forecast selection, open `analysis.py → select_forecasts`**
> "The key correctness rule is no hindsight. For each target time I compute a cutoff, either target minus horizon or D-1 at 9 a.m. UK time, which is DST-aware, and pick the latest forecast published at or before it. That's a `merge_asof` grouped by target time, so it's vectorised and O(n log n)."
> "Two data-quality details: WINDFOR contains 'forecasts' for times already in the past, which I drop, and forecasts are hourly while actuals are half-hourly, so I score on the hourly grid rather than interpolate."
- Open `add_scale_correction`.
> "The correction is causal. It uses cumulative sums and `searchsorted`, so each row only sees hours settled at least an hour before its cutoff."

**[7:15 – 8:00] Tests, open `tests/test_analysis.py` and run `pytest -q` in the terminal**
> "There are 27 tests. Parametrised tests cover the horizon rule, the DST cutoff (winter vs. summer), and a causality test where I poison future actuals and assert the correction doesn't change. That proves there's no leakage. The API tests run on the synthetic source, and the Elexon client is tested with httpx's MockTransport for retries and caching."
- Show `.github/workflows/ci.yml`.
> "CI runs ruff, pytest, the TypeScript type-check, vitest, the build and a Docker build on every push."

**[8:00 – 8:45] Frontend, open `frontend/src`**
> "On the frontend, a typed API client mirrors the backend schemas. A small `useApi` hook cancels stale requests with AbortController when you drag the slider. The components are split by tab, and all times are formatted in Europe/London. It's responsive and supports dark mode."

**[8:45 – 9:30] Analysis notebook and trade-offs**
> "The notebook reuses the same module and adds data-quality checks, the horizon curve, an investigation of the bias, a back-test across correction windows, and a coverage check on the P10–P90 band."
> "Trade-offs: the cache is in-memory per serverless instance, which is fine for a pilot, but in production I'd add Redis or a nightly ETL into Postgres. The daily low case sums hourly P10s, which is conservative by design. Next I'd add curtailment data to explain the bias, a regional split, and quantile regression for the band."

**[9:30 – 9:50] Wrap**
> "The README has setup, the API docs and these decisions written down. Thanks for reviewing."

---

### Recording checklist

- Total length under 10:00, with each part's overview under 5:00.
- Use the live Vercel URL in the video (not localhost) and make sure the header says "Live data: Elexon BMRS".
- Warm the app up once before recording, because the first load fetches from Elexon (cold start of about 5–10 s).
- Close notifications, use a clean browser profile, and speak a little slower than normal.
- In the YouTube description, add the app link and the GitHub link.
