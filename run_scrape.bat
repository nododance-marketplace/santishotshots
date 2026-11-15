@echo off
rem Daily hotshot lead scrape — used by Windows Task Scheduler (7am / 3pm)
cd /d "D:\Downloads\Santi\Hot shots"
echo === run started %date% %time% === >> scrape.log
python scrape_leads.py >> scrape.log 2>&1

rem Publish the fresh snapshot to the live site (auto-deploys via Vercel)
git add leads.csv leads.json 2>> scrape.log
git diff --cached --quiet 2>nul
if errorlevel 1 (
  git commit -m "Lead snapshot %date% %time%" >> scrape.log 2>&1
  git push >> scrape.log 2>&1
)
