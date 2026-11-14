@echo off
rem Daily hotshot lead scrape — used by Windows Task Scheduler (7am / 3pm)
cd /d "D:\Downloads\Santi\Hot shots"
echo === run started %date% %time% === >> scrape.log
python scrape_leads.py >> scrape.log 2>&1
