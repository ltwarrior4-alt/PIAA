# Make the District 1 Football Tracker a public website

**No Mac Terminal, Python install, or command-line launcher is required for visitors.** This package contains the complete existing 2026 Class 6A tracker plus a cloud-compatible Python server and Render configuration.

## What the public site does

- Everyone sees **one official-results snapshot** fetched centrally from PIAA District 1. It checks the published official pages about every **15 minutes while the host is running**.
- Open browser tabs check the server for updates every **3 minutes**. Visitors who open the page get the last fetched results and an update is triggered if due.
- The MaxPreps schedule audit is attempted roughly every six hours. Out-of-District opponent records are supplemental; data gaps or unavailable sources are shown as warnings.
- **What-if scenarios stay separate in each person's browser** (`localStorage`). They do not alter public standings or other visitors' scenarios; use export/import to move scenarios to another device.
- Scores are *not* promised live immediately after a game: the tracker must wait for the published official PIAA schedule/rankings, which may be delayed. Missing external scores or unverified classifications remain provisional.

## Publish on the internet (browser-only process from a MacBook Air)

1. Sign in or create a **GitHub** account at https://github.com and a **Render** account at https://render.com.
2. On GitHub, choose **New repository**, name it e.g. `piaa-d1-2026-tracker`. Choose *Public* if you want the app code public (or Private if your Render connection supports it). Create the repository.
3. In the new GitHub repo choose **Add file → Upload files**. From this extracted package, upload these four files **into the root of the repo (not in a subfolder)**:
   - `index.html`
   - `sync_service.py`
   - `2026_rankings_and_games.json`
   - `render.yaml`
   Optional: upload this Markdown guide too.
4. Click **Commit changes**.
5. Go to https://dashboard.render.com/ → **New → Blueprint**; connect the GitHub repo and use `render.yaml` as the Blueprint path. Approve the service deployment.
6. Render gives you a public **`https://...onrender.com`** link once deployed. Share that one address with coaches or parents. Neither they nor you need a Mac launcher.
7. Visit the site, check that the top banner says it is fetching/has checked published results, and check `/health` in the same URL if you want to confirm the web server is alive.

The package defaults to Render's **Free** web-service plan so that deployment doesn't require committing to a paid plan. **Important:** Free services normally sleep after 15 minutes without a visitor, so the 15-minute schedule does **not** continue during those sleeping periods. When someone visits, the service wakes, serves the baseline or last available data, and starts checking results again. Render may discard its saved local feed across restarts; the latest data must then be re-fetched.

For scheduled checking even when nobody visits, upgrade the service to an **always-on paid instance** in the Render dashboard. Pricing and availability can change; verify current plans before committing to a subscription. External data websites can still be unavailable or delayed, regardless of hosting plan.

## Common issues

- **Site loads, but top banner says waiting:** First background result fetch may still be in progress, or PIAA/MaxPreps blocked or changed its pages. The original Oct. 15 dataset remains available; never interpret it as the current standings.
- **Live standings don't match the site:** Check the source link and the last successful sync time. Never treat a MaxPreps-only result as official until the District 1 point record catches up.
- **A user's scenario is missing on another device:** Scenarios are intentionally per-browser, not shared through a server. Use Export/Import in the app.
- **Free site is slow on first visit:** This is normal after the hosting service has spun down.
- **Costs:** Free is intended for testing; a paid always-on plan may incur monthly fees. Configure billing only after reviewing the provider's prices.

## Architecture / file list

- `index.html`: your existing what-if simulator and standings UI, changed to show the shared service wording.
- `2026_rankings_and_games.json`: baseline snapshot as of October 15, 2026, not a claim of current rankings.
- `sync_service.py`: Python standard-library HTTP server and background official-score synchronizer. Public refresh requests are limited to one external-sync attempt per 15 minutes. Exposes `/`, `/health`, `/api/data`, `/api/refresh`.
- `render.yaml`: deployment blueprint. Change `plan: free` to an appropriate paid plan or select a paid instance through Render when you need true 24/7 refresh.

**No public site has been deployed by creating this package.** It must be uploaded to a Git repository and connected to a hosting account first. Do not share the `127.0.0.1` address; it only works on your own machine.
