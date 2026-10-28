# Submission guide (step by step)

## 1. Run it locally first (about 10 min)

Zip extract karo, phir:

```bash
cd wind-forecast-monitor
docker compose up --build
```

Browser mein http://localhost:8080 kholo. Header pe "Live data: Elexon BMRS" dikhna chahiye. Teeno tabs check karo.

Docker nahi hai to README ka "Option B" follow karo.

Ek baar `cd backend && pytest -q` bhi chala lo. 27 tests pass hone chahiye.

## 2. GitHub repo (anonymous name)

1. github.com pe New repository banao. Naam random rakhna, jaise `kjhwr7` (company ka ya apna naam nahi). Visibility **Public** rakho.
2. Phir terminal mein:

```bash
cd wind-forecast-monitor
git init
git add .
git commit -m "Wind Forecast Monitor: initial version"
git branch -M main
git remote add origin https://github.com/<your-username>/kjhwr7.git
git push -u origin main
```

3. GitHub pe **Actions** tab kholo. CI green hona chahiye.

Note: repo public hoga to username dikhega. Doc mein sirf repo ka naam anonymous maanga hai, isliye ye theek hai.

## 3. Vercel deploy (free)

1. vercel.com pe GitHub se login karo.
2. **Add New → Project** pe jao aur apna repo import karo.
3. Framework preset "Other" rehne do aur Root Directory `/` rakho. Baaki settings `vercel.json` se apne aap aa jaayengi.
4. **Deploy** karo. 2-3 min mein URL milega, jaise `kjhwr7.vercel.app`.
5. Check karo:
   - `https://<url>/api/health` pe `{"status":"ok","data_source":"elexon"}` aana chahiye
   - App ke teeno tabs load hone chahiye. Pehla load 5-10 sec le sakta hai (cold start).
6. README mein "Live app" wali line mein ye URL daal ke dobara commit + push karo.

Agar Vercel pe API 500 de: Vercel dashboard mein **Deployments → Functions → Logs** dekho aur error mujhe bhej do.

## 4. Video

`VIDEO_SCRIPT.md` follow karo. YouTube pe upload karte waqt Visibility **Unlisted** rakhna. Video ka link bhi README mein daal do.

## 5. Form submit

Doc ke link se "Full Stack SWE challenge submission v4" form kholo aur ye 3 cheezein daalo:

- YouTube video link (unlisted)
- GitHub repo link
- Vercel app link

Submit se pehle teeno links **incognito window** mein khol ke check karo ki bina login ke chal rahe hain. Doc mein ye specifically likha hai.

## Interview mein ye points zaroor bolna

- "No hindsight" rule aur merge_asof
- WINDFOR mein past ke forecasts aate hain, jinhe filter kiya
- Bias finding (~1.8 GW, curtailment hypothesis) aur causal correction (~33% improvement)
- Causality test jo future data ko poison karke leakage na hone ka proof deta hai
