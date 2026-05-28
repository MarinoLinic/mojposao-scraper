"""
scraper_api_test.py
-------------------
Tests the hidden /api/proxy/* endpoints on mojposao.hr.

STEP 1: Run this script to probe candidate job-search API endpoints.
STEP 2: Check which URL returns actual job JSON (look for 200 + job list).
STEP 3: If none hit, open DevTools → Network → XHR/Fetch while loading
        https://mojposao.hr/pretraga-poslova?... and capture the correct
        endpoint, then update JOBS_ENDPOINT below.

Known working endpoints (from your captures):
  /api/proxy/suggestions/locations  - location autocomplete
  /api/proxy/suggestions/positions  - category list

Candidate job-search endpoints to probe (guesses based on pattern):
  /api/proxy/jobs
  /api/proxy/search
  /api/proxy/job-ads
  /api/proxy/offers
"""

import json
import time
import requests

# ── Config ────────────────────────────────────────────────────────────────────

# Location IDs (from your locations.txt response)
LOCATION_ZAGREB_CITY   = "ChIJOcwCyZLWZUcRisL7KJYkRTo"   # Zagreb (city)
LOCATION_ZAGREB_COUNTY = "ChIJe_jnWFN_ZkcRILQrhlCtAAM"   # Grad Zagreb i Zagrebačka županija

# Position/category IDs (from your positions.txt response)
POSITION_IT   = 11   # IT, telekomunikacije
POSITION_ALL  = None # omit for all categories

# Paste your current token cookie here if you want auth (optional for public search)
TOKEN_COOKIE = ""  # e.g. "eyJhbGci..."

BASE_URL = "https://mojposao.hr"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "hr",
    "x-app": "mojposao.hr",
    "Referer": "https://mojposao.hr/pretraga-poslova?locations=Zagreb&positions=IT,+telekomunikacije",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}

# ── Candidate endpoint patterns to probe ─────────────────────────────────────

CANDIDATE_PATHS = [
    "/api/proxy/jobs",
    "/api/proxy/search",
    "/api/proxy/job-ads",
    "/api/proxy/offers",
    "/api/proxy/vacancies",
    "/api/proxy/positions",
    "/api/proxy/job-listings",
]

# Query param variants to try alongside each path
PARAM_VARIANTS = [
    {"locations": LOCATION_ZAGREB_CITY, "positions": POSITION_IT, "page": 1},
    {"location": LOCATION_ZAGREB_CITY, "position": POSITION_IT, "page": 1},
    {"locationId": LOCATION_ZAGREB_CITY, "categoryId": POSITION_IT, "page": 1},
    {"q": "", "locations": LOCATION_ZAGREB_CITY, "categories": POSITION_IT},
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    if TOKEN_COOKIE:
        s.cookies.set("token", TOKEN_COOKIE, domain="mojposao.hr")
    return s


def probe_endpoints(session: requests.Session):
    """Try all candidate paths × param variants and print what comes back."""
    print("=" * 60)
    print("PROBING CANDIDATE ENDPOINTS")
    print("=" * 60)

    hits = []

    for path in CANDIDATE_PATHS:
        for params in PARAM_VARIANTS:
            url = BASE_URL + path
            try:
                r = session.get(url, params=params, timeout=10)
                ct = r.headers.get("Content-Type", "")
                print(f"\n[{r.status_code}] {r.url}")
                print(f"  Content-Type: {ct}")

                if r.status_code == 200 and "json" in ct:
                    try:
                        data = r.json()
                        print(f"  JSON keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        hits.append((r.url, data))
                        # Print a small preview
                        preview = json.dumps(data, ensure_ascii=False)[:400]
                        print(f"  Preview: {preview}...")
                    except Exception as e:
                        print(f"  Could not parse JSON: {e}")
                elif r.status_code not in (404, 405):
                    # Interesting non-404 response even if not JSON
                    print(f"  Body snippet: {r.text[:200]}")

            except requests.RequestException as e:
                print(f"\n  ERROR {url}: {e}")

            time.sleep(0.5)  # be polite between probes

    return hits


def fetch_jobs_api(session: requests.Session, url: str, params: dict) -> dict | None:
    """
    Once you know the correct endpoint + params, use this to fetch jobs.
    Returns parsed JSON or None on failure.
    """
    try:
        r = session.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None
    except ValueError as e:
        print(f"JSON parse failed: {e}")
        return None


def parse_jobs_from_api(data: dict) -> list[dict]:
    """
    Attempt to extract job list from common response shapes.
    Adjust the keys once you see the real response.
    """
    # Try common wrapper keys
    for key in ("jobs", "items", "data", "results", "ads", "offers"):
        if key in data and isinstance(data[key], list):
            return data[key]
    # If the top level IS a list
    if isinstance(data, list):
        return data
    print(f"  Unknown response shape, keys: {list(data.keys())}")
    return []


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    session = make_session()

    # Warm up with a homepage visit
    print("Warming up on homepage...")
    try:
        session.get(BASE_URL, timeout=10)
        time.sleep(2)
    except requests.RequestException as e:
        print(f"  Warmup failed (continuing): {e}")

    # Confirm the known-good suggestion endpoints still work
    print("\n--- Confirming known-good endpoints ---")
    r = session.get(
        f"{BASE_URL}/api/proxy/suggestions/locations",
        params={"locations": LOCATION_ZAGREB_CITY},
        timeout=10,
    )
    print(f"  /suggestions/locations → {r.status_code}")

    r = session.get(
        f"{BASE_URL}/api/proxy/suggestions/positions",
        params={"positions": POSITION_IT},
        timeout=10,
    )
    print(f"  /suggestions/positions → {r.status_code}")

    # Now probe for the actual job-search endpoint
    hits = probe_endpoints(session)

    if hits:
        print("\n" + "=" * 60)
        print(f"FOUND {len(hits)} HIT(S) — check above for the correct endpoint.")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("No JSON hits found.")
        print("→ Open DevTools (F12) → Network → XHR/Fetch")
        print("→ Load: https://mojposao.hr/pretraga-poslova?locations=Zagreb&positions=IT,+telekomunikacije")
        print("→ Look for a request that returns job data (title, link, date)")
        print("→ Copy that URL/path here and update CANDIDATE_PATHS")
        print("=" * 60)


if __name__ == "__main__":
    main()