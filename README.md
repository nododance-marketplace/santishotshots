# 🔥 Hot Shot Lead Scraper + Viewer

Market-scouting tool for hotshot loads **departing North Carolina**
(Charlotte, Raleigh, Greensboro, Asheville, Wilmington, Hickory areas).

> **This is a snapshot, not a live feed.** Loads on the free boards get
> booked within HOURS. Scrape → open `lead_viewer.html` → work the list
> **the same day**. A 24-hour-old CSV triggers a big red STALE banner in
> the viewer for exactly this reason.

## Files

| File | What it is |
|---|---|
| `scrape_leads.py` | The scraper. Sweeps public/free sources, dedupes, scores, writes `leads.csv` / `leads.json` / `run_summary.txt` / `scrape.log` |
| `lead_viewer.html` | Dark-theme dashboard. Double-click it, load `leads.csv` with the 📂 button (no server needed) |
| `hot-shot-load-manager.html` | Your existing load manager (now with a ⬆ Import button) |
| `run_scrape.bat` | One-double-click scraper run, used by Task Scheduler |
| `leads.csv` / `leads.json` | Lead snapshot (regenerated every run) |
| `run_summary.txt` | Per-source found/failed report from the last run |
| `scrape.log` | Full request log, so you can see exactly what broke |

## Sources (public / free only — no logins, no DAT/Truckstop)

1. **Trulos** free load board
2. **TruckSmarter** free board
3. **TruckerPath TruckLoads** free tier (hotshot filter click attempt)
4. **uShip** public machinery/vehicle/boat listings
5. **Craigslist** gigs + labor haul on 9 NC city subdomains (parsed from Craigslist's own RSS/HTML — most stable source)
6. **GovDeals** — auction assets in NC (buyers need delivery; pay well per mile)
7. **Purple Wave** — auction assets in NC

Each source is a separate function with its own try/except: one broken
site logs a failure and the run continues. If a site starts blocking us
(403/429/5xx), we stop hitting **that site** immediately and move on.
Requests are throttled to 1 every 3–5 s with a realistic User-Agent.

## Setup

```
pip install requests beautifulsoup4
```

Optional but **recommended** — Trulos/TruckSmarter/TruckerPath/uShip render
with JavaScript, so without Playwright those sources may come back empty:

```
pip install playwright
python -m playwright install chromium
```

## Run it

```
python scrape_leads.py                       # everything
python scrape_leads.py --source craigslist   # one source only
python scrape_leads.py --hours 24            # keep only last-24h posts
python scrape_leads.py --max-requests 5      # quick smoke test
```

Scoring (0–100) adds points for NC origin, posted rates, sub-600-mile
hauls, machinery/LTL/equipment freight and auction-delivery leads, and
subtracts for 53ft/semi requirements, hazmat, and >14,000 lb loads.

## Using the viewer

1. Double-click `lead_viewer.html`.
2. Click **📂 Load leads.csv**, pick the file.
3. Filter: *NC departure only* (default on), *rate posted only*, max
   distance, min rate/mile, search, source.
4. **➜ Add** on a lead queues it; **⬇ Download import file** produces
   `load-manager-import.json`.
5. Open `hot-shot-load-manager.html` → **⬆ Import** → pick that file.
   Your leads land in the Loads tab as "Browsing" with the lead's score
   and source pasted into the notes.

## Run it daily (Windows Task Scheduler, 7am + 3pm)

Easiest — one-time commands in an **elevated** PowerShell or CMD:

```bat
schtasks /Create /TN "HotShot Lead Scrape AM" /TR "D:\Downloads\Santi\Hot shots\run_scrape.bat" /SC DAILY /ST 07:00
schtasks /Create /TN "HotShot Lead Scrape PM" /TR "D:\Downloads\Santi\Hot shots\run_scrape.bat" /SC DAILY /ST 15:00
```

Verify / manage:

```bat
schtasks /Run   /TN "HotShot Lead Scrape AM"
schtasks /Query /TN "HotShot Lead Scrape AM" /V
schtasks /Delete /TN "HotShot Lead Scrape PM" /F
```

(Or the GUI way: Task Scheduler → Create Basic Task → Daily 7:00 →
Start a Program → `run_scrape.bat`, then repeat for 15:00.)

## When sites break (they will)

- A failed source **never** crashes the run — check `run_summary.txt`
  and `scrape.log` for which source and why.
- Most breakage is just changed HTML. The scraper's harvesters match
  route/location *patterns* in page text rather than brittle CSS
  selectors, so minor redesigns usually survive. For a real structural
  change, the site's function lives alone in `scrape_leads.py` — update
  just that function.
- If a source starts returning 403s, leave it alone for a few days
  rather than hammering it; run `--source` for the healthy ones.
- Note: **GovDeals actively blocks automated browsers** (Akamai). Expect
  it to show `FAILED` in `run_summary.txt` fairly often — that's the
  polite-stop design working, not a crash. Purple Wave is scraped via
  the same public JSON search API its own site uses, so it's solid.
