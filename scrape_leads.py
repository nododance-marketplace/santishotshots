#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HOT SHOT LEAD SCRAPER — NC-departing load leads
===============================================

WHAT THIS IS
    A market-scouting SNAPSHOT tool. It sweeps free, public load boards,
    gigs sites and auction marketplaces for freight departing North
    Carolina that fits a dually + gooseneck hotshot rig, then scores and
    exports the leads for lead_viewer.html.

    *** Loads on free boards get booked within HOURS. This file is a
        snapshot the moment it's written — run it 1-2x/day and work the
        viewer list the SAME DAY. ***

RULES OF THE ROAD
    - Public, freely-accessible pages only. No logins, no paywalled
      DAT/Truckstop data, no account circumvention of any kind.
    - Polite: max 1 request every 3-5 seconds, realistic User-Agent.
    - We STOP scraping a source the moment it blocks us (403/429/5xx).
    - Every source is isolated: if a site changes its HTML and breaks,
      we log the failure and the other sources still run.

USAGE
    python scrape_leads.py                      # all sources
    python scrape_leads.py --source craigslist  # one source only
    python scrape_leads.py --hours 24           # keep only last-24h posts
    python scrape_leads.py --max-requests 5     # quick smoke test

OUTPUT
    leads.csv, leads.json (with scraped_at timestamps), run_summary.txt,
    scrape.log

SOURCES (all free/public):
    1. Trulos free load board          (trulos.com/load-board)
    2. TruckSmarter free board         (trucksmarter.com)
    3. TruckerPath TruckLoads          (loadboard.truckerpath.com)
    4. uShip public listings           (uship.com)
    5. Craigslist gigs / labor haul    (NC city subdomains)
    6. GovDeals auction assets         (govdeals.com)
    7. Purple Wave auction assets      (purplewave.com)

    Boards 1-4 are JavaScript-rendered and need Playwright (optional).
    If Playwright isn't installed we try the static HTML anyway and log
    a clean skip when the page is empty. Craigslist is parsed from
    Craigslist's own RSS/HTML results — the most stable source here.
"""

import argparse
import csv
import difflib
import importlib.util
import json
import logging
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from math import radians, sin, cos, asin, sqrt
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

DELAY_MIN, DELAY_MAX = 3.0, 5.0          # seconds between ANY two requests
MAX_REQUESTS_DEFAULT = 60                # hard politeness cap per run

log = logging.getLogger("hotshot")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

PLAYWRIGHT_OK = importlib.util.find_spec("playwright") is not None


class BlockError(RuntimeError):
    """Site is blocking us — stop this source immediately, keep others."""


class SourceError(RuntimeError):
    """This source failed for a logged, non-fatal reason."""


# --------------------------------------------------------------------------
# GEO: straight-line distance fallback (loaded miles ≈ air miles × 1.15)
# --------------------------------------------------------------------------

CITY_COORDS = {
    # NC departure areas
    "charlotte, nc": (35.2271, -80.8431), "raleigh, nc": (35.7796, -78.6382),
    "greensboro, nc": (36.0726, -79.7920), "asheville, nc": (35.5951, -82.5515),
    "wilmington, nc": (34.2257, -77.9447), "hickory, nc": (35.7344, -81.3412),
    "fayetteville, nc": (35.0527, -78.8784), "durham, nc": (35.9940, -78.8986),
    "cary, nc": (35.7915, -78.7811), "high point, nc": (35.9557, -79.9921),
    "winston-salem, nc": (36.0999, -80.2442), "concord, nc": (35.4088, -80.5816),
    "gastonia, nc": (35.2621, -81.1873), "rocky mount, nc": (35.9386, -77.7905),
    "jacksonville, nc": (34.7541, -77.4304), "goldsboro, nc": (35.3849, -77.9928),
    "kinston, nc": (35.2409, -77.6037), "new bern, nc": (35.1085, -77.0400),
    "boone, nc": (36.2117, -81.6904), "morganton, nc": (35.7540, -81.6982),
    "statesville, nc": (35.8276, -80.8841), "monroe, nc": (34.9995, -80.5460),
    # common SE/Midwest destinations (extend freely)
    "columbia, sc": (34.0007, -81.0348), "charleston, sc": (32.7765, -79.9311),
    "greenville, sc": (34.8526, -82.3940), "myrtle beach, sc": (33.6891, -78.8867),
    "savannah, ga": (32.0809, -81.0912), "atlanta, ga": (33.7490, -84.3880),
    "augusta, ga": (33.4716, -81.9758), "macon, ga": (32.8407, -83.6324),
    "knoxville, tn": (35.9606, -83.9207), "nashville, tn": (36.1627, -86.7816),
    "chattanooga, tn": (35.0456, -85.3097), "memphis, tn": (35.1495, -90.0490),
    "richmond, va": (37.5407, -77.4360), "virginia beach, va": (36.8529, -75.9780),
    "norfolk, va": (36.8508, -76.2859), "roanoke, va": (37.2710, -79.9414),
    "arlington, va": (38.8816, -77.0910), "washington, dc": (38.9072, -77.0369),
    "baltimore, md": (39.2904, -76.6122), "philadelphia, pa": (39.9526, -75.1652),
    "pittsburgh, pa": (40.4406, -79.9959), "harrisburg, pa": (40.2732, -76.8867),
    "charleston, wv": (38.3498, -81.6326), "huntington, wv": (38.4190, -82.4452),
    "lexington, ky": (38.0406, -84.5037), "louisville, ky": (38.2527, -85.7585),
    "cincinnati, oh": (39.1031, -84.5120), "columbus, oh": (39.9612, -82.9988),
    "cleveland, oh": (41.4993, -81.6944), "indianapolis, in": (39.7684, -86.1581),
    "kansas city, mo": (39.0997, -94.5786), "st louis, mo": (38.6270, -90.1994),
    "chicago, il": (41.8781, -87.6298), "detroit, mi": (42.3314, -83.0458),
    "jacksonville, fl": (30.3322, -81.6557), "orlando, fl": (28.5383, -81.3792),
    "tampa, fl": (27.9506, -82.4572), "miami, fl": (25.7617, -80.1918),
    "gainesville, fl": (29.6516, -82.3248), "pensacola, fl": (30.4213, -87.2169),
    "mobile, al": (30.6954, -88.0399), "birmingham, al": (33.5186, -86.8104),
    "jackson, ms": (32.2988, -90.1848), "new orleans, la": (29.9511, -90.0715),
    "louisville, tn": (38.2527, -85.7585), "houston, tx": (29.7604, -95.3698),
    "dallas, tx": (32.7767, -96.7970), "san antonio, tx": (29.4241, -98.4936),
    "austin, tx": (30.2672, -97.7431), "oklahoma city, ok": (35.4676, -97.5165),
    "tulsa, ok": (36.1540, -95.9928), "little rock, ar": (34.7465, -92.2896),
    "knoxville, ky": (35.9606, -83.9207),
}

STATE_SET = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

NC_CITIES = {c.split(",")[0] for c in CITY_COORDS if c.endswith("nc")}


def _key(city, state):
    return f"{(city or '').strip().lower()}, {(state or '').strip().lower()}"


def haversine_miles(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * asin(min(1.0, sqrt(h)))


def estimate_miles(ocity, ostate, dcity, dstate):
    """Straight-line miles x 1.15 when we know both endpoints, else None."""
    o = CITY_COORDS.get(_key(ocity, ostate))
    d = CITY_COORDS.get(_key(dcity, dstate))
    if not (o and d):
        return None
    return round(haversine_miles(o, d) * 1.15)


# --------------------------------------------------------------------------
# TEXT EXTRACTION HEURISTICS (the "safety net" for shifting site HTML)
# --------------------------------------------------------------------------

ROUTE_RE = re.compile(
    r"\b([A-Z][A-Za-z .'-]{2,28}),\s*([A-Z]{2})\s*"
    r"(?:\u2192|->|>>|to|-{1,2}|\u2014|\u2013|\u25b8|\u00bb)\s*"
    r"([A-Z][A-Za-z .'-]{2,28}),\s*([A-Z]{2})\b"
)

PAIR_RE = re.compile(
    r"(?:pick\s?up|pickup|origin|ship\s?from|from|located(?:\s+in)?|location)\s*:?\s*"
    r"([A-Z][A-Za-z .'-]{2,28}),\s*([A-Z]{2})\b.{0,200}?"
    r"(?:deliver(?:y)?(?:\s+to)?|destination|ship\s?to|drop(?:\s?off)?|to)\s*:?\s*"
    r"([A-Z][A-Za-z .'-]{2,28}),\s*([A-Z]{2})\b",
    re.I | re.S,
)

LOCATED_RE = re.compile(
    r"(?:located(?:\s+in)?|item\s+location|asset\s+location|location)\s*:?\s*"
    r"([A-Z][A-Za-z .'-]{2,28}),\s*([A-Z]{2})\b",
    re.I,
)

RATE_RE = re.compile(r"\$\s?([\d,]{2,7}(?:\.\d{1,2})?)")
PERMILE_RE = re.compile(r"\$\s?([\d.]{1,5})\s*(?:/|per\s)\s*(?:mi|mile)", re.I)
PHONE_RE = re.compile(r"\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WEIGHT_RE = re.compile(r"([\d,]{3,7})\s*(?:lbs?|pounds?)\b", re.I)
SEMI_RE = re.compile(r"53\s?(?:ft|foot|feet|')|semi[- ]?trailer|semi\b|dry van|tractor[- ]?trailer", re.I)
HAZMAT_RE = re.compile(r"hazmat|hazardous|explosive|radioactive|corrosive|flammable", re.I)
CONTACT_LABEL_RE = re.compile(r"(?:broker|company|poster|dealer|seller|contact)\s*:?\s*([A-Za-z0-9 .,&'-]{3,45})", re.I)

EQUIP_KW = [
    ("Machinery/Equipment", ["skid steer", "skidsteer", "mini ex", "mini excavator", "excavator",
                             "backhoe", "dozer", "bobcat", "track loader", "forklift", "telehandler",
                             "boom lift", "scissor lift", "generator", "machinery", "equipment",
                             "loader", "mower", "zero turn", "paver", "roller", "compactor",
                             "air compressor", "welder", "mill"]),
    ("Vehicles", ["car haul", "haul a car", "vehicle", "sedan", "suv", "pickup truck",
                  "box truck", "moving truck", "van"]),
    ("Boats", ["boat", "pontoon", "jet ski", "kayak", "outboard", "pwc"]),
    ("LTL/Palletized", ["pallet", "crate", "ltl", "boxes", "bundle", "steel", "lumber",
                        "freight", "material", "bar stock"]),
    ("Livestock/Ag", ["horse", "cattle", "livestock", "goats", "hay"]),
]


def guess_equipment(text):
    t = text.lower()
    for label, kws in EQUIP_KW:
        if any(k in t for k in kws):
            return label
    return "General freight"


def clean_txt(s, limit=220):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:limit]


# --------------------------------------------------------------------------
# LEAD MODEL + ENRICHMENT + SCORING
# --------------------------------------------------------------------------

def new_lead(source, url):
    return {
        "source": source, "origin_city": "", "origin_state": "",
        "dest_city": "", "dest_state": "", "equipment_type": "",
        "hotshot_ok": True, "rate": None, "rate_note": "", "miles": None,
        "rate_per_mile": None, "posted_at": "", "poster": "", "contact": "",
        "url": url, "snippet": "", "score": None, "score_breakdown": "",
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def finish_lead(lead):
    """Fill miles / rate-per-mile / equipment / flags, then score it."""
    pa = lead.get("posted_at")
    if isinstance(pa, (int, float)):          # epoch from some APIs
        ts = pa / 1000 if pa > 1e12 else pa
        lead["posted_at"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
    text = f"{lead['origin_city']} {lead['dest_city']} {lead['snippet']} {lead['equipment_type']}"
    if not lead["equipment_type"]:
        lead["equipment_type"] = guess_equipment(text)
    lead["miles"] = estimate_miles(lead["origin_city"], lead["origin_state"],
                                   lead["dest_city"], lead["dest_state"])
    rate = lead["rate"]
    if rate and lead["miles"]:
        lead["rate_per_mile"] = round(rate / lead["miles"], 3)
    elif lead["rate_note"].startswith("~$") and "/mi" in lead["rate_note"]:
        try:
            lead["rate_per_mile"] = float(lead["rate_note"].strip("~$ /mi").strip())
        except ValueError:
            pass
    if not lead["rate"] and not lead["rate_note"]:
        lead["rate_note"] = "Call for rate"
    score_lead(lead)
    return lead


def score_lead(lead):
    """0-100 hotshot suitability score. Points, never handed to a model."""
    text = lead["snippet"].lower()
    pts, notes = [], 0.0

    def add(v, why):
        nonlocal notes
        notes += v
        pts.append(f"{'+' if v >= 0 else ''}{v:g} {why}")

    if lead["origin_state"] == "NC":
        add(25, "NC origin")
    else:
        add(8, "non-NC origin (verify deadhead)")

    if lead["rate"]:
        add(15, "rate posted")
    if lead["miles"] is not None:
        if lead["miles"] <= 600:
            add(15, f"short/medium haul ({lead['miles']} mi)")
        elif lead["miles"] <= 1200:
            add(5, f"long haul ({lead['miles']} mi)")
        else:
            add(-5, f"very long haul ({lead['miles']} mi)")
    eq = lead["equipment_type"].lower()
    if any(k in eq for k in ("machinery", "ltl", "pallet", "equipment")):
        add(15, "machinery/LTL/equipment freight")
    elif any(k in eq for k in ("vehicle", "boat", "livestock")):
        add(8, "hauler-friendly freight type")
    if lead["source"] in ("govdeals", "purplewave"):
        add(10, "auction delivery lead (buyers pay well per mile)")
    if lead["rate_per_mile"] and lead["rate_per_mile"] >= 2.0:
        add(8, f"strong RPM ({lead['rate_per_mile']:.2f}/mi)")
    elif lead["rate_per_mile"] and lead["rate_per_mile"] < 1.0:
        add(-8, f"weak RPM ({lead['rate_per_mile']:.2f}/mi)")

    m = SEMI_RE.search(text)
    if m:
        add(-30, f"needs semi/53ft ('{m.group(0)}')")
        lead["hotshot_ok"] = False
    m = HAZMAT_RE.search(text)
    if m:
        add(-25, f"hazmat ('{m.group(0)}')")
        lead["hotshot_ok"] = False
    m = WEIGHT_RE.search(text)
    if m:
        try:
            lbs = int(m.group(1).replace(",", ""))
            if lbs > 14000:
                add(-20, f"heavy load ({lbs:,} lbs)")
                lead["hotshot_ok"] = False
        except ValueError:
            pass

    lead["score"] = max(0, min(100, round(notes)))
    lead["score_breakdown"] = "; ".join(pts) or "no signals"


# --------------------------------------------------------------------------
# GENERIC HARVESTERS — used by every source as primary or fallback so that
# a site redesign still yields leads as long as routes appear in the text.
# --------------------------------------------------------------------------

def extract_block(text, url, source, posted_dt=None, require_dest=True):
    """Pull one lead out of a block of visible text (card, row, anchor...)."""
    t = " ".join((text or "").split())
    if len(t) < 15:
        return None

    ocity = ostate = dcity = dstate = None
    m = ROUTE_RE.search(t)
    if m:
        ocity, ostate, dcity, dstate = m.group(1).strip(" .-"), m.group(2), m.group(3).strip(" .-"), m.group(4)
    else:
        m = PAIR_RE.search(t)
        if m:
            ocity, ostate, dcity, dstate = m.group(1).strip(" .-"), m.group(2), m.group(3).strip(" .-"), m.group(4)
    if not ocity:
        return None
    if require_dest and not dcity:
        return None

    lead = new_lead(source, url)
    lead["origin_city"], lead["origin_state"] = ocity, (ostate or "").upper()
    lead["dest_city"], lead["dest_state"] = (dcity or ""), (dstate or "").upper()

    window = t[:500]
    mr = RATE_RE.search(window)
    if mr:
        try:
            val = float(mr.group(1).replace(",", ""))
            if val >= 10:
                lead["rate"] = val
        except ValueError:
            pass
    mp = PERMILE_RE.search(window)
    if mp and not lead["rate"]:
        lead["rate_note"] = f"~${mp.group(1)}/mi listed"
    mk = CONTACT_LABEL_RE.search(window)
    if mk:
        lead["poster"] = mk.group(1).strip()[:45]
    ph, em = PHONE_RE.search(window), EMAIL_RE.search(window)
    bits = []
    if ph:
        bits.append(ph.group(0))
    if em:
        bits.append(em.group(0))
    lead["contact"] = " / ".join(bits)
    lead["snippet"] = clean_txt(t, 260)
    if posted_dt:
        lead["posted_at"] = posted_dt
    return finish_lead(lead)


def harvest_anchors(html, source, base_url, require_dest=True):
    """Scan every <a> whose visible text looks like a listing; keep leads."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        block_text = a.get_text(" ", strip=True)
        parent = a.parent
        if parent is not None:
            block_text += " " + parent.get_text(" ", strip=True)
        lead = extract_block(block_text, urljoin(base_url, a["href"]), source,
                             require_dest=require_dest)
        if lead:
            out.append(lead)
    return out


def harvest_page_text(html, source, base_url):
    """Last-resort harvest: routes anywhere in the visible page text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    out = []
    for m in ROUTE_RE.finditer(text):
        start = max(0, m.start() - 200)
        lead = extract_block(text[start:m.end() + 250], base_url, source)
        if lead:
            out.append(lead)
    return out


def nc_origin(lead):
    st = (lead["origin_state"] or "").upper()
    if st == "NC":
        return True
    return not st and lead["origin_city"].lower() in NC_CITIES


# --------------------------------------------------------------------------
# POLITE TRANSPORT
# --------------------------------------------------------------------------

def polite_get(url, **kw):
    """Sleep 3-5s, GET with a real UA, raise BlockError if we're being blocked."""
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    log.info("GET %s", url)
    try:
        r = SESSION.get(url, timeout=30, **kw)
    except requests.RequestException as e:
        raise SourceError(f"network error: {e}")
    if r.status_code in (401, 403, 429, 511) or r.status_code >= 500:
        raise BlockError(f"HTTP {r.status_code} from {url} — site is blocking us; "
                         f"stopping this source politely.")
    r.raise_for_status()
    return r


def render_js(url, wait_ms=7000, click_texts=()):
    """Headless-browser render for JS-heavy boards. Requires optional Playwright."""
    if not PLAYWRIGHT_OK:
        raise SourceError("page is JavaScript-rendered and Playwright isn't installed "
                          "(pip install playwright && python -m playwright install chromium)")
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    from playwright.sync_api import sync_playwright
    log.info("RENDER %s", url)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900},
                                  locale="en-US")
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(wait_ms)
            for label in click_texts:
                try:
                    btn = page.get_by_text(label, exact=False).first
                    if btn.count():
                        btn.click(timeout=3000)
                        page.wait_for_timeout(3000)
                except Exception:
                    pass
            html = page.content()
        except Exception as e:
            raise SourceError(f"browser render failed: {e}")
        finally:
            browser.close()
    return html


def render_or_get(url, **kw):
    """Static first; if the body is empty/JS shell, fall back to a headless render."""
    r = polite_get(url, **kw)
    text = r.text
    if len(BeautifulSoup(text, "html.parser").get_text(strip=True)) > 600:
        return text
    try:
        return render_js(url)
    except SourceError:
        raise


# --------------------------------------------------------------------------
# SOURCE 1: TRULOS (free board)
# --------------------------------------------------------------------------

def scrape_trulos(max_requests):
    """Trulos trulos.com/load-board — free public board. We look for NC->X rows."""
    leads = []
    html = render_or_get("https://www.trulos.com/load-board")
    leads += harvest_anchors(html, "trulos", "https://www.trulos.com")
    if not leads:
        leads += harvest_page_text(html, "trulos", "https://www.trulos.com")
    # If the board needs a search submitted, run a plain NC search render too.
    if not leads:
        leads += harvest_anchors(
            render_js("https://www.trulos.com/load-board?originState=NC", wait_ms=8000),
            "trulos", "https://www.trulos.com")
    return leads


# --------------------------------------------------------------------------
# SOURCE 2: TRUCKSMARTER (free board, hotshot friendly)
# --------------------------------------------------------------------------

def scrape_trucksmarter(max_requests):
    leads = []
    for url in ("https://www.trucksmarter.com/load-board", "https://www.trucksmarter.com/"):
        if max_requests <= 0:
            break
        max_requests -= 1
        html = render_or_get(url)
        leads += harvest_anchors(html, "trucksmarter", url)
        if leads:
            break
    if not leads:
        leads += harvest_page_text(html, "trucksmarter", url)
    return leads


# --------------------------------------------------------------------------
# SOURCE 3: TRUCKERPATH TRUCKLOADS
# --------------------------------------------------------------------------

def scrape_truckerpath(max_requests):
    leads = []
    if max_requests <= 0:
        return leads
    max_requests -= 1
    # Try to flip the free board's "hotshot" filter if the button exists.
    html = render_js("https://loadboard.truckerpath.com/", wait_ms=9000,
                     click_texts=("Hotshot", "Hot shot"))
    leads += harvest_anchors(html, "truckerpath", "https://loadboard.truckerpath.com/")
    if not leads:
        leads += harvest_page_text(html, "truckerpath", "https://loadboard.truckerpath.com/")
    return leads


# --------------------------------------------------------------------------
# SOURCE 4: USHIP (public marketplace listings)
# --------------------------------------------------------------------------

def scrape_uship(max_requests):
    leads = []
    pages = [
        "https://www.uship.com/freight/north-carolina/",
        "https://www.uship.com/vehicles/north-carolina/",
        "https://www.uship.com/heavy-equipment/north-carolina/",
    ]
    for url in pages:
        if max_requests <= 0:
            break
        max_requests -= 1
        try:
            html = render_or_get(url)
        except BlockError:
            raise
        except (SourceError, requests.HTTPError) as e:
            log.warning("uship page skip: %s", e)
            continue
        found = harvest_anchors(html, "uship", url)
        if found:
            leads += found
    if not leads:
        leads += harvest_page_text(html, "uship", url)
    return leads


# --------------------------------------------------------------------------
# SOURCE 5: CRAIGSLIST (gigs + labor haul on NC city subdomains)
# --------------------------------------------------------------------------

CL_SUBDOMAINS = ["charlotte", "raleigh", "greensboro", "asheville", "wilmington",
                 "hickory", "fayetteville", "eastnc", "boone"]
CL_QUERIES = ["hot shot", "haul", "transport"]
CL_SECTIONS = ["ggg", "lbg"]          # gigs + labor gigs


def _cl_parse_rss(xml_text, source, base_url, sub):
    out = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return out
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = item.findtext("description") or ""
        date_raw = item.findtext("dc:date", default="", namespaces=ns)
        desc_txt = clean_txt(re.sub(r"<[^>]+>", " ", BeautifulSoup(desc, "html.parser").get_text(" ", strip=True)), 400)
        posted = parse_dt(date_raw)
        block = f"{title} {desc_txt}"
        lead = extract_block(block, link or base_url, source,
                             posted_dt=posted or "", require_dest=False)
        if not lead:
            # no destination parsed — keep it as a local NC pickup lead anyway
            if not title or len(title) < 8:
                continue
            lead = new_lead(source, link or base_url)
            lead["origin_city"], lead["origin_state"] = SUB_CITY[sub], "NC"
            lead["snippet"] = clean_txt(block, 260)
            lead["posted_at"] = posted or ""
            lead = finish_lead(lead)
        else:
            if not lead["origin_state"]:
                lead["origin_city"], lead["origin_state"] = SUB_CITY[sub], "NC"
                lead = finish_lead(lead)
        lead["source"] = "craigslist"
        out.append(lead)
    return out


def _cl_parse_html(html_text, source, sub):
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for li in soup.select("li"):
        a = li.find("a", href=True)
        if not a:
            continue
        txt = " ".join(li.get_text(" ", strip=True).split())
        t_el = li.find("time")
        posted = parse_dt(t_el["datetime"]) if t_el and t_el.has_attr("datetime") else None
        if len(txt) < 12:
            continue
        lead = extract_block(txt, urljoin(f"https://{sub}.craigslist.org", a["href"]),
                             source, posted_dt=posted or "", require_dest=False)
        if not lead:
            lead = new_lead(source, urljoin(f"https://{sub}.craigslist.org", a["href"]))
            lead["origin_city"], lead["origin_state"] = SUB_CITY[sub], "NC"
            lead["snippet"] = clean_txt(txt, 260)
            lead["posted_at"] = posted or ""
            lead = finish_lead(lead)
        else:
            if not lead["origin_state"]:
                lead["origin_city"], lead["origin_state"] = SUB_CITY[sub], "NC"
                lead = finish_lead(lead)
        lead["source"] = "craigslist"
        out.append(lead)
    return out


SUB_CITY = {
    "charlotte": "Charlotte", "raleigh": "Raleigh", "greensboro": "Greensboro",
    "asheville": "Asheville", "wilmington": "Wilmington", "hickory": "Hickory",
    "fayetteville": "Fayetteville", "eastnc": "Jacksonville NC", "boone": "Boone",
}


def scrape_craigslist(max_requests):
    """Craigslist posts its own RSS for searches — the most stable free feed here.
    Origin is the posting city (NC); destination parsed out of title/description."""
    leads = []
    for sub in CL_SUBDOMAINS:
        for section in CL_SECTIONS:
            for q in CL_QUERIES:
                if max_requests <= 0:
                    log.warning("craigslist: request cap reached, stopping politely")
                    return leads
                max_requests -= 1
                url = (f"https://{sub}.craigslist.org/search/{section}"
                       f"?query={quote_plus(q)}&format=rss")
                try:
                    r = polite_get(url)
                except BlockError:
                    raise                      # stop the whole source
                except SourceError as e:
                    log.warning("craigslist skip %s: %s", sub, e)
                    continue
                except requests.HTTPError as e:
                    log.warning("craigslist skip %s: %s", sub, e)
                    continue
                got = _cl_parse_rss(r.text, "craigslist", url, sub)
                if not got:
                    # RSS gone/empty — try the plain HTML search result list
                    try:
                        r2 = polite_get(f"https://{sub}.craigslist.org/search/{section}"
                                        f"?query={quote_plus(q)}")
                        got = _cl_parse_html(r2.text, "craigslist", sub)
                    except (BlockError, SourceError, requests.HTTPError) as e:
                        log.warning("craigslist html fallback skip %s: %s", sub, e)
                leads += got
    return leads


# --------------------------------------------------------------------------
# SOURCES 6-7: AUCTION SITES (GovDeals, Purple Wave)
# These are "buyer needs it delivered" leads: origin = asset location,
# destination unknown until you call — that's why require_dest=False.
# --------------------------------------------------------------------------

AUCTION_KW = ("skid steer", "excavator", "backhoe", "dozer", "forklift", "telehandler",
              "tractor", "loader", "generator", "mower", "bobcat", "trailer",
              "equipment", "machinery", "compressor", "boom", "trencher", "mini ex")


def scrape_govdeals(max_requests):
    leads = []
    urls = [
        "https://www.govdeals.com/en/find-assets?k=north%20carolina",
        "https://www.govdeals.com/en/filters?so=ff&sf=bestfit&kwd=north%20carolina",
    ]
    for url in urls:
        if max_requests <= 0:
            break
        max_requests -= 1
        try:
            html = render_or_get(url)
        except BlockError:
            raise
        except (SourceError, requests.HTTPError) as e:
            log.warning("govdeals skip %s: %s", url, e)
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            txt = a.get_text(" ", strip=True)
            parent_txt = (a.parent.get_text(" ", strip=True) if a.parent else "")
            block = f"{txt} {parent_txt}"
            low = block.lower()
            if len(txt) < 15 or not any(k in low for k in AUCTION_KW):
                continue
            m = LOCATED_RE.search(block)
            if not m:
                continue
            lead = new_lead("govdeals", urljoin("https://www.govdeals.com", a["href"]))
            lead["origin_city"], lead["origin_state"] = m.group(1).strip(" .-"), m.group(2)
            lead["snippet"] = clean_txt(block, 260)
            leads.append(finish_lead(lead))
    return leads


def scrape_purplewave(max_requests):
    """Purple Wave exposes the same JSON search API its own website uses
    (no login, public). We query upcoming auctions within ~120 mi of each
    NC departure city and keep only items located in NC — every one is a
    'winning bidder needs it delivered' lead."""
    leads = []
    for city, zc in PW_ZIPS.items():
        if max_requests <= 0:
            log.warning("purplewave: request cap reached, stopping politely")
            break
        max_requests -= 1
        url = ("https://www.purplewave.com/v1/search/search?callback=x"
               "&searchType=all&dateType=upcoming&dateRanges=&auctions="
               "&startPrice=0&endPrice=0&filters=&sortBy=distance&grouped=false"
               f"&resultsPerPage=100&zipcode={zc}&zipcodeRange=150")
        try:
            raw = polite_get(url).text
            data = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
        except (SourceError, ValueError, IndexError) as e:
            log.warning("purplewave skip %s: %s", city, e)
            continue
        for r in data:
            if str(r.get("state_abbreviation") or "").upper() != "NC":
                continue
            title = clean_txt(r.get("title") or "", 140)
            if not title:
                continue
            closing = (r.get("auction_closing") or r.get("auction_time")
                       or r.get("auction_endtime") or "")
            lead = new_lead("purplewave",
                            f"https://www.purplewave.com/auction/{r.get('auction')}"
                            f"/item/{r.get('id')}")
            lead["origin_city"] = clean_txt(r.get("city") or city, 40)
            lead["origin_state"] = "NC"
            lead["equipment_type"] = guess_equipment(title)
            lead["rate_note"] = "Auction item — winning bidder arranges delivery"
            lead["snippet"] = clean_txt(
                f"AUCTION: {title} · closes {clean_txt(closing, 24)} · "
                f"current bid {money(r.get('current_bid'))}. Buyer will need it "
                f"hauled from the auction site in {lead['origin_city']}, NC.",
                300)
            lead["posted_at"] = r.get("date_created") or ""
            leads.append(finish_lead(lead))
    return leads


PW_ZIPS = {"Charlotte": "28202", "Raleigh": "27601", "Greensboro": "27401",
           "Asheville": "28801", "Wilmington": "28401", "Hickory": "28601"}


def money(v):
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


SOURCES = {
    "trulos": scrape_trulos,
    "trucksmarter": scrape_trucksmarter,
    "truckerpath": scrape_truckerpath,
    "uship": scrape_uship,
    "craigslist": scrape_craigslist,
    "govdeals": scrape_govdeals,
    "purplewave": scrape_purplewave,
}


# --------------------------------------------------------------------------
# PIPELINE: dates, filters, dedupe
# --------------------------------------------------------------------------

def parse_dt(s):
    if not s:
        return None
    s = str(s).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S",
                "%a, %d %b %Y %H:%M:%S %z", "%m/%d/%Y %I:%M %p"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def dedupe(leads):
    """Deduplicate by URL, then by (origin, destination, description
    similarity >= 0.85, posted date)."""
    out = []
    for l in sorted(leads, key=lambda x: -(x.get("score") or 0)):
        dup = False
        n_desc = re.sub(r"[^a-z0-9 ]", " ", l["snippet"].lower())[:150]
        for o in out:
            if l["url"] and o["url"] == l["url"]:
                dup = True
                break
            same_lane = (o["origin_city"].lower() == l["origin_city"].lower()
                         and o["origin_state"] == l["origin_state"]
                         and (o["dest_city"].lower() == l["dest_city"].lower()
                              or not l["dest_city"] or not o["dest_city"]))
            same_day = (str(o["posted_at"] or ""))[:10] == (str(l["posted_at"] or ""))[:10]
            if same_lane and same_day and difflib.SequenceMatcher(
                    None, re.sub(r"[^a-z0-9 ]", " ", o["snippet"].lower())[:150],
                    n_desc).ratio() >= 0.85:
                dup = True
                break
        if not dup:
            out.append(l)
    return out


# --------------------------------------------------------------------------
# OUTPUT
# --------------------------------------------------------------------------

CSV_FIELDS = ["source", "score", "origin_city", "origin_state", "dest_city",
              "dest_state", "equipment_type", "hotshot_ok", "rate", "rate_note",
              "miles", "rate_per_mile", "posted_at", "poster", "contact", "url",
              "snippet", "score_breakdown", "scraped_at"]


def write_outputs(leads, results, args):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open("leads.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for l in leads:
            w.writerow({k: l.get(k, "") for k in CSV_FIELDS})

    with open("leads.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": stamp, "count": len(leads), "leads": leads},
                  f, indent=2, ensure_ascii=False)

    lines = [
        "HOT SHOT LEAD SCRAPE — run summary",
        f"Generated:  {stamp}",
        f"Params:     --source {args.source}  --hours {args.hours if args.hours else 'all-time'}"
        f"  --max-requests {args.max_requests}",
        f"Playwright: {'installed (JS boards scraped headlessly)' if PLAYWRIGHT_OK else 'NOT installed — JS boards were static-only attempts'}",
        "",
        "Per source:",
    ]
    for name, info in results.items():
        status = "OK" if info["ok"] else "FAILED"
        line = f"  {name:<12} found {info['found']:>4}  kept {info['kept']:>4}  {status}"
        if info["error"]:
            line += f"\n      └─ {info['error']}"
        lines.append(line)
    lines += [
        "",
        f"TOTAL: {len(leads)} leads after dedupe -> leads.csv / leads.json",
        "",
        "REMINDER: this is a market-scouting SNAPSHOT. Loads like these get",
        "booked within hours. Open lead_viewer.html and work the list TODAY.",
    ]
    with open("run_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    # Windows consoles default to cp1252 and choke on unicode in the summary
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Hot shot lead scraper (NC departures)")
    ap.add_argument("--source", choices=sorted(SOURCES.keys()) + ["all"], default="all",
                    help="run a single source instead of all of them")
    ap.add_argument("--hours", type=float, default=None,
                    help="keep only leads posted within the last N hours "
                         "(leads with no date are kept and marked)")
    ap.add_argument("--max-requests", type=int, default=MAX_REQUESTS_DEFAULT,
                    help="politeness cap on outbound requests (default %(default)s)")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler("scrape.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
    )
    log.info("Hot shot lead scrape starting — source=%s hours=%s", args.source, args.hours)
    if not PLAYWRIGHT_OK:
        log.info("Playwright not installed; JS-heavy boards will be tried statically "
                 "or skipped cleanly (pip install playwright && python -m playwright install chromium)")

    names = list(SOURCES) if args.source == "all" else [args.source]
    results, all_leads = {}, []
    for name in names:
        info = {"found": 0, "kept": 0, "ok": True, "error": ""}
        t0 = time.time()
        try:
            raw = SOURCES[name](args.max_requests)
            info["found"] = len(raw)
            keep = [finish_lead(l) if l.get("score") is None else l for l in raw]
            keep = [l for l in keep if nc_origin(l)]
            if args.hours is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
                dated, undated = [], []
                for l in keep:
                    dt = parse_dt(l.get("posted_at"))
                    (dated if dt else undated).append(l)
                keep = [l for l in dated if dt_ok(l, cutoff)] + undated
            info["kept"] = len(keep)
            all_leads += keep
            log.info("[%-11s] %s raw -> %s NC-origin leads (in %.1fs)",
                     name, info["found"], info["kept"], time.time() - t0)
        except BlockError as e:
            info["ok"], info["error"] = False, str(e)
            log.error("[%s] BLOCKED — moving on: %s", name, e)
        except SourceError as e:
            info["ok"], info["error"] = False, str(e)
            log.error("[%s] failed: %s", name, e)
        except Exception as e:                      # never let one source crash the run
            info["ok"], info["error"] = False, f"unexpected: {e!r}"
            log.exception("[%s] unexpected failure", name)
        results[name] = info

    leads = dedupe(all_leads)
    leads.sort(key=lambda l: (-(l.get("rate_per_mile") or 0), str(l.get("posted_at") or "")),
               reverse=False)
    leads.sort(key=lambda l: -(l["score"] or 0))

    summary = write_outputs(leads, results, args)
    print()
    print(summary)
    log.info("Done. %s leads written to leads.csv / leads.json — snapshot taken at %s",
             len(leads), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))


def dt_ok(lead, cutoff):
    dt = parse_dt(lead.get("posted_at"))
    return bool(dt and dt >= cutoff)


if __name__ == "__main__":
    main()
