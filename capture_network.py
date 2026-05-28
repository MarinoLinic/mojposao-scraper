"""
capture_network_general.py
--------------------------
A GENERAL-PURPOSE network tab recorder and hidden-API finder.
Opens a real (visible) browser, loads any URLs you give it,
intercepts ALL network traffic, and produces a rich analysis:

  - network_log.json        → every captured request/response
  - api_candidates.json     → filtered calls that look like data APIs
  - api_report.txt          → human-readable summary with parameter analysis
  - {site}_{label}.html     → full rendered HTML per URL (post-JS, after scroll)

QUICK START
-----------
1.  pip install playwright
    playwright install chromium

2.  Edit the CONFIG block below (URLs, site name, optional auth cookie)

3.  python capture_network_general.py

4.  Read api_report.txt first — it explains what APIs were found and
    what query parameters they accept.

WHAT IT DETECTS
---------------
- JSON APIs (XHR / Fetch)
- GraphQL endpoints
- REST-style pagination patterns
- Query parameters on API calls (so you know what filters exist)
- Request payloads (POST bodies)
- Repeated API calls (pagination / infinite scroll)
- Redirects and 3xx chains
- Auth headers / tokens (redacted for safety)
- Location / geo APIs
- Search suggestion / autocomplete APIs
- Static data files (manifests, config JSONs)
"""

import json
import re
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path
from playwright.sync_api import sync_playwright, Response


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG — edit this section for each new site
# ══════════════════════════════════════════════════════════════════════════════

# Leave as None to auto-derive from the first URL's hostname (e.g. "njuskalo_hr")
SITE_NAME: str | None = None

SEARCH_URLS = [
    # Add as many URLs as you want to probe.
    # 'label' is just for your reference in the output.
    {
        "label": "Apartments for sale / Zagreb",
        "url": "https://www.njuskalo.hr/prodaja-stanova?geo[locationIds]=1247,1248,1249,1250,1252,1253,1254,1255,1256,1257,1258,1259,1260,1261,1262,1263,1264,1251&price[max]=360000&livingArea[max]=100&adsWithImages=1&numberOfRooms[min]=four-rooms&numberOfRooms[max]=five-rooms&buildingInfo[lift]=1&sort=new",
    },
    {
        "label": "Njuskalo.hr",
        "url": "https://www.njuskalo.hr/",
    },
    {
        "label": "Cars for sale",
        "url": "https://www.njuskalo.hr/auti?geo[locationIds]=1153&adsWithImages=1&condition[used]=1&sort=cheap",
    },
    {
        "label": "Renting apartments",
        "url": "https://www.njuskalo.hr/iznajmljivanje-stanova?geo[locationIds]=1153,1170&sort=old",
    },
    {
        "label": "Marketplace",
        "url": "https://www.njuskalo.hr/marketplace",
    },
    {
        "label": "Blago",
        "url": "https://www.njuskalo.hr/blago",
    },
    # --- Examples for other sites (uncomment / edit as needed) ---
    # {
    #     "label": "Cars under 10k",
    #     "url": "https://www.njuskalo.hr/automobili?price_max=10000",
    # },
]

# Optional: paste a valid session cookie string here if the site requires login.
# Leave as None to browse anonymously.
# Example: "session_id=abc123; auth_token=xyz"
SESSION_COOKIE: str | None = None

# How many seconds to wait after page load for async/lazy calls
WAIT_AFTER_LOAD = 6

# Scroll depth: how many times to scroll down (triggers lazy loading / pagination)
SCROLL_STEPS = 3

# Headless mode: False = visible browser window (good for watching + debugging)
HEADLESS = False

# Save full rendered HTML for each URL? (post-JS, after scroll — good for BeautifulSoup analysis)
SAVE_HTML = True

# Output files
OUTPUT_DIR = Path(".")   # change to e.g. Path("output") if you prefer


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER RULES — controls what gets kept / flagged
# ══════════════════════════════════════════════════════════════════════════════

# URL patterns to ignore completely (static assets, trackers, etc.)
NOISE_PATTERNS = [
    r"\.(js|css|svg|png|jpg|jpeg|gif|webp|ico|woff2?|ttf|eot|map)(\?|$)",
    r"/(chunk|bundle|vendor|runtime|polyfill|webpack)",
    # Analytics & tracking — never useful for scraping
    r"google(tag|analytics|syndication|fonts|apis)\.com",
    r"region\d*\.google-analytics\.com",
    r"facebook\.net|fbcdn",
    r"sentry\.io|bugsnag",
    r"(doubleclick|clarity|hotjar|mixpanel|amplitude|segment)\.",
    r"analytics\.tiktok\.com",
    r"perfdrive\.com",           # bot-detection / fingerprinting
    r"cloudfront\.net/static",
    r"_nuxt/|__nuxt",
    r"/_next/static",
    r"/assets/[a-f0-9]{8,}\.",   # hashed static assets
    r"/g/collect",               # GA4 event ping
    r"/measurement/conversion",  # GA4 conversion ping
    r"gtm\.js|gtag",
]

# Patterns that suggest an interesting data / API call
SIGNAL_PATTERNS = [
    r"/api/",
    r"/v\d+/",            # versioned REST: /v1/, /v2/ …
    r"\.json(\?|$)",      # explicit JSON files
    r"graphql",
    r"proxy",
    r"search",
    r"suggest",
    r"autocomplete",
    r"geo|location|region|city|place",
    r"job|posao|oglas|ad|offer|listing",
    r"category|kategor",
    r"filter|facet|refine",
    r"page|offset|limit|per_page|pageSize",
    r"token|auth(?!or)",  # auth tokens (but not "author")
]

# HTTP methods that always get captured regardless of URL patterns.
# POST is intentionally NOT here — too many analytics POSTs are noise.
# POSTs only get captured if they also match a SIGNAL_PATTERN or return JSON.
ALWAYS_CAPTURE_METHODS = {"PUT", "PATCH", "DELETE"}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_noise(url: str) -> bool:
    return any(re.search(p, url, re.I) for p in NOISE_PATTERNS)

def has_signal(url: str) -> bool:
    return any(re.search(p, url, re.I) for p in SIGNAL_PATTERNS)

def classify_url(url: str) -> list[str]:
    """Return a list of category tags for the URL."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path.lower()
    full = url.lower()

    # Don't tag known third-party / analytics domains with meaningful categories
    TRACKER_HOSTS = (
        "google-analytics.com", "googletagmanager.com", "doubleclick.net",
        "tiktok.com", "facebook.net", "perfdrive.com", "sentry.io",
        "hotjar.com", "clarity.ms", "amplitude.com", "segment.io",
    )
    if any(t in host for t in TRACKER_HOSTS):
        return ["tracker"]

    tags = []
    if "graphql" in full:                                    tags.append("graphql")
    if re.search(r"/v\d+/", path):                          tags.append("versioned-rest")
    if re.search(r"suggest|autocomplete|typeahead", full):   tags.append("autocomplete")
    if re.search(r"geo|location|region|city|district|place|coord|lat|lon", full): tags.append("geo/location")
    if re.search(r"search|query", full):                     tags.append("search")
    if re.search(r"filter|facet", full):                     tags.append("filter")
    if re.search(r"page|offset|limit|cursor|hierarchy", full): tags.append("pagination")
    if re.search(r"auth|token|session|login", full):         tags.append("auth")
    if re.search(r"category|categor|tree|taxonomy", full):   tags.append("category-tree")
    if re.search(r"config|settings|init|bootstrap", full):   tags.append("site-config")
    if re.search(r"listing|ad|oglas|job|posao|offer|stan|nekretnin", full): tags.append("listings")
    if re.search(r"banner|targeting|advert", full):          tags.append("ads/targeting")
    if re.search(r"papi/", full):                            tags.append("internal-api")
    return tags or ["data"]

def parse_query_params(url: str) -> dict:
    """Extract and decode query parameters from a URL."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {k: v[0] if len(v) == 1 else v for k, v in params.items()}

def redact_auth(headers: dict) -> dict:
    """Replace sensitive header values with [REDACTED]."""
    sensitive = {"authorization", "x-auth-token", "cookie", "x-api-key",
                 "x-csrf-token", "x-session-id"}
    return {
        k: "[REDACTED]" if k.lower() in sensitive else v
        for k, v in headers.items()
    }

def extract_json_keys(body, depth=0, max_depth=3) -> list[str]:
    """Recursively collect dot-notation keys from a JSON body."""
    keys = []
    if depth > max_depth:
        return keys
    if isinstance(body, dict):
        for k, v in body.items():
            keys.append(k)
            sub = extract_json_keys(v, depth + 1, max_depth)
            keys.extend(f"{k}.{s}" for s in sub)
    elif isinstance(body, list) and body:
        sub = extract_json_keys(body[0], depth + 1, max_depth)
        keys.extend(f"[]{s}" and f"[].{s}" for s in sub)
    return keys

def summarise_json_shape(body) -> dict:
    """Return a compact shape summary of a JSON response."""
    if isinstance(body, dict):
        shape = {}
        for k, v in body.items():
            if isinstance(v, list):
                shape[k] = f"array[{len(v)}]"
                if v and isinstance(v[0], dict):
                    shape[k] += " of {" + ", ".join(list(v[0].keys())[:8]) + "}"
            elif isinstance(v, dict):
                shape[k] = "{" + ", ".join(list(v.keys())[:6]) + "}"
            elif isinstance(v, str) and len(v) > 80:
                shape[k] = f'"{v[:40]}…"'
            else:
                shape[k] = repr(v)[:60]
        return shape
    elif isinstance(body, list):
        return {"(root array)": f"array[{len(body)}]",
                "(first item keys)": list(body[0].keys())[:10] if body and isinstance(body[0], dict) else "?"}
    return {}


# ══════════════════════════════════════════════════════════════════════════════
#  EMBEDDED STATE EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════

# These are the global JS variables that frameworks use to embed server-side
# state into HTML. We try them all in order.
STATE_PATTERNS = [
    # Nuxt 2 / Vue SSR
    (r'window\.__INITIAL_STATE__\s*=\s*', "__INITIAL_STATE__"),
    # Next.js
    (r'<script id="__NEXT_DATA__"[^>]*>\s*', "__NEXT_DATA__"),
    # Nuxt 3
    (r'window\.__NUXT__\s*=\s*', "__NUXT__"),
    # Generic
    (r'window\.__APP_STATE__\s*=\s*', "__APP_STATE__"),
    (r'window\.__STATE__\s*=\s*', "__STATE__"),
    (r'window\.__data__\s*=\s*', "__data__"),
    (r'window\.__PRELOADED_STATE__\s*=\s*', "__PRELOADED_STATE__"),  # Redux
    (r'window\.__STORE__\s*=\s*', "__STORE__"),
]

def extract_page_state(html: str) -> dict:
    """
    Scan HTML for embedded server-side JSON state objects.
    Returns a dict keyed by state variable name, value is parsed JSON.
    Tries all known framework patterns (Nuxt, Next.js, Redux, etc.)
    """
    found = {}
    for pattern, name in STATE_PATTERNS:
        match = re.search(pattern, html)
        if not match:
            continue
        start = match.end()
        # Walk forward to find the matching closing brace/bracket
        opener = html[start] if start < len(html) else ""
        if opener not in ("{", "["):
            continue
        closer = "}" if opener == "{" else "]"
        depth, i, in_str, escape = 0, start, False, False
        for i, ch in enumerate(html[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_str:
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
        raw = html[start:i + 1]
        try:
            found[name] = json.loads(raw)
            print(f"  [STATE] Found {name} ({len(raw):,} bytes)")
        except Exception:
            # Sometimes Nuxt uses a non-standard format — try eval-safe extraction
            pass
    return found


def extract_filter_schema(state: dict) -> dict:
    """
    Given a parsed state object, try to find filter/parameter schema.
    Returns a dict with keys: url_params, fields, listings_sample, pagination.
    Works generically by walking the tree looking for known key names.
    """
    result = {
        "url_params":      [],   # ordered list of valid URL param names
        "fields":          {},   # current filter values / structure
        "listings_sample": [],   # first few listing objects
        "pagination":      {},   # page count, total count
        "raw_keys":        [],   # all top-level keys found for debugging
    }

    def walk(obj, depth=0):
        """Recursively search the state tree for known scraping-relevant keys."""
        if depth > 6 or not isinstance(obj, (dict, list)):
            return
        if isinstance(obj, list):
            for item in obj[:3]:
                walk(item, depth + 1)
            return

        keys = set(obj.keys())
        if depth <= 2:
            result["raw_keys"].extend(f"{'  '*depth}{k}" for k in keys)

        # URL parameter order list
        if "urlParametersOrder" in keys and not result["url_params"]:
            result["url_params"] = obj["urlParametersOrder"]

        # Filter field definitions
        if "fields" in keys and isinstance(obj["fields"], dict) and not result["fields"]:
            result["fields"] = obj["fields"]

        # Listings (try several common key names)
        for listings_key in ("regularListings", "listings", "items", "results", "ads", "data"):
            if listings_key in keys and isinstance(obj[listings_key], list) and obj[listings_key]:
                if not result["listings_sample"]:
                    result["listings_sample"] = obj[listings_key][:2]
                break

        # Pagination
        for count_key in ("listingsCount", "totalCount", "total", "count"):
            if count_key in keys and not result["pagination"].get("total"):
                result["pagination"]["total"] = obj[count_key]
        for page_key in ("totalPageCount", "pageCount", "totalPages", "pages"):
            if page_key in keys and not result["pagination"].get("pages"):
                result["pagination"]["pages"] = obj[page_key]

        for v in obj.values():
            walk(v, depth + 1)

    for state_obj in state.values():
        walk(state_obj)

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  CAPTURE LOGIC
# ══════════════════════════════════════════════════════════════════════════════

def capture_page(page, search: dict, all_entries: list, candidate_entries: list, site_name: str = "site") -> dict:
    """Capture network calls and HTML for one URL. Returns extracted page state (may be empty dict)."""
    label = search["label"]
    url   = search["url"]
    print(f"\n{'═'*65}")
    print(f"  {label}")
    print(f"  {url}")
    print(f"{'═'*65}")

    seen_urls: set[str] = set()

    def on_response(response: Response):
        req_url  = response.url
        method   = response.request.method
        status   = response.status

        if is_noise(req_url):
            return

        # --- Try to read body ---
        body = None
        body_raw = None
        try:
            ct = response.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = response.json()
                    body_raw = "json"
                except Exception:
                    body_raw = response.text()
            elif "text" in ct and len(response.text()) < 50_000:
                # Catch text/plain JSON or misconfigured content-type
                raw = response.text()
                try:
                    body = json.loads(raw)
                    body_raw = "json-in-text"
                except Exception:
                    pass  # plain text, not interesting
        except Exception:
            pass

        is_json = body is not None

        # --- Decide if interesting ---
        interesting = (
            method in ALWAYS_CAPTURE_METHODS
            or has_signal(req_url)
            or is_json
        )
        if not interesting:
            return

        query_params = parse_query_params(req_url)

        # --- Try to read request POST body ---
        req_body = None
        try:
            post_data = response.request.post_data
            if post_data:
                try:
                    req_body = json.loads(post_data)
                except Exception:
                    req_body = post_data[:500]
        except Exception:
            pass

        entry = {
            "label":        label,
            "url":          req_url,
            "method":       method,
            "status":       status,
            "content_type": response.headers.get("content-type", ""),
            "query_params": query_params,
            "request_body": req_body,
            "tags":         classify_url(req_url),
            "repeated":     req_url in seen_urls,
            "body":         body,
            "body_shape":   summarise_json_shape(body) if is_json else None,
        }
        seen_urls.add(req_url)
        all_entries.append(entry)
        candidate_entries.append(entry)

        # Console feedback
        repeat_tag = " [REPEAT]" if entry["repeated"] else ""
        tags_str   = " | ".join(entry["tags"])
        print(f"  [{status}] {method:6s} [{tags_str}]{repeat_tag}")
        print(f"    {req_url[:100]}")
        if query_params:
            print(f"    params: {query_params}")
        if is_json and entry["body_shape"]:
            shape_str = str(entry["body_shape"])[:200]
            print(f"    shape:  {shape_str}")

    page.on("response", on_response)

    # Navigate
    try:
        page.goto(url, wait_until="networkidle", timeout=40_000)
    except Exception as e:
        print(f"  [WARN] networkidle timeout ({e}), continuing anyway")

    print(f"  Waiting {WAIT_AFTER_LOAD}s for async calls…")
    time.sleep(WAIT_AFTER_LOAD)

    # Scroll to trigger lazy-loaded content / infinite scroll
    for step in range(SCROLL_STEPS):
        page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {(step+1)/SCROLL_STEPS})")
        time.sleep(1.5)
    page.evaluate("window.scrollTo(0, 0)")  # scroll back up
    time.sleep(1)

    page.remove_listener("response", on_response)

    # ── Save full rendered HTML + extract embedded state ─────────────────────
    page_state = {}
    if SAVE_HTML:
        safe_label = re.sub(r"[^\w\-]", "_", label).strip("_").lower()
        html_path  = OUTPUT_DIR / f"{site_name}_{safe_label}.html"
        html       = page.content()
        html_path.write_text(html, encoding="utf-8")
        print(f"  HTML saved → {html_path}  ({len(html):,} bytes)")

        # Extract embedded JS state (Nuxt, Next.js, Redux, etc.)
        raw_state = extract_page_state(html)
        if raw_state:
            schema = extract_filter_schema(raw_state)
            page_state = {"label": label, "url": url, "raw": raw_state, "schema": schema}
            # Save state as clean JSON alongside HTML
            state_path = OUTPUT_DIR / f"{site_name}_{safe_label}_state.json"
            state_path.write_text(
                json.dumps(raw_state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"  State saved → {state_path}")
            if schema["pagination"]:
                print(f"  Pagination: {schema['pagination']}")
            if schema["url_params"]:
                print(f"  Filter params found: {len(schema['url_params'])} parameters")

    print(f"  Done: {label}")
    return page_state


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def build_report(candidate_entries: list, site_name: str = "site", page_states: list | None = None) -> str:
    lines = []
    W = 70

    def h1(t): lines.append("\n" + "═" * W); lines.append(f"  {t}"); lines.append("═" * W)
    def h2(t): lines.append(f"\n── {t} " + "─" * max(0, W - len(t) - 4))
    def li(t): lines.append(f"  • {t}")
    def kv(k, v): lines.append(f"    {k:<22} {v}")

    lines.append("NETWORK ANALYSIS REPORT")
    lines.append(f"Site: {site_name}   |   {len(candidate_entries)} captured calls")

    # ── Embedded state (most valuable — show first) ───────────────────────────
    if page_states:
        h1("EMBEDDED PAGE STATE (server-rendered data in HTML)")
        for ps in page_states:
            schema = ps["schema"]
            h2(ps["label"].upper())
            li(f"URL: {ps['url']}")

            # State variable names found
            state_vars = list(ps["raw"].keys())
            li(f"State objects found: {', '.join(state_vars)}")

            # Pagination
            if schema["pagination"]:
                pg = schema["pagination"]
                total   = pg.get("total", "?")
                pages   = pg.get("pages", "?")
                li(f"Pagination: {total} total listings across {pages} pages")

            # Listings sample
            if schema["listings_sample"]:
                sample = schema["listings_sample"][0]
                li(f"Listing fields available: {list(sample.keys())}")
                li(f"Sample listing:")
                for k, v in sample.items():
                    lines.append(f"      {k:<30} {repr(v)[:60]}")

            # Filter fields
            if schema["fields"]:
                li("Filter fields (current values from this page load):")
                for k, v in schema["fields"].items():
                    lines.append(f"      {k:<30} {repr(v)[:60]}")

            # Full URL parameter list
            if schema["url_params"]:
                li(f"All valid URL parameters ({len(schema['url_params'])} total):")
                # Group into rows of 4 for readability
                params = schema["url_params"]
                for i in range(0, len(params), 4):
                    chunk = params[i:i+4]
                    lines.append("      " + "  |  ".join(f"{p}" for p in chunk))

        lines.append("")
        lines.append("  → TIP: The state JSON files (*_state.json) contain the complete")
        lines.append("         raw data — open them to see every listing, filter option,")
        lines.append("         and configuration value the page loaded.")
        lines.append("  → TIP: For scraping, parse window.__INITIAL_STATE__ (or equiv.)")
        lines.append("         directly from the HTML — no API calls needed.")


    # ── Group by tag ──────────────────────────────────────────────────────────
    by_tag: dict[str, list] = defaultdict(list)
    for e in candidate_entries:
        for tag in e["tags"]:
            by_tag[tag].append(e)

    h1("API CALLS BY CATEGORY")
    for tag, entries in sorted(by_tag.items()):
        if tag == "tracker":
            continue  # printed separately below
        h2(tag.upper())
        seen = set()
        for e in entries:
            base = urllib.parse.urlparse(e["url"])
            key  = base.scheme + "://" + base.netloc + base.path
            if key in seen:
                continue
            seen.add(key)
            li(f"[{e['status']}] {e['method']} {key}")
            if e["query_params"]:
                kv("query params:", str(e["query_params"])[:120])
            if e["request_body"]:
                kv("request body:", str(e["request_body"])[:120])
            if e["body_shape"]:
                kv("response shape:", str(e["body_shape"])[:120])

    # Trackers get their own collapsed section so they don't pollute the main view
    tracker_entries = by_tag.get("tracker", [])
    if tracker_entries:
        h2("TRACKERS / ANALYTICS (filtered out of main analysis)")
        seen = set()
        for e in tracker_entries:
            host = urllib.parse.urlparse(e["url"]).hostname or ""
            if host not in seen:
                seen.add(host)
                li(host)

    # ── All query parameters ever seen ───────────────────────────────────────
    h1("ALL QUERY PARAMETERS OBSERVED (site calls only)")
    all_params: dict[str, set] = defaultdict(set)
    param_origins: dict[str, list] = defaultdict(list)
    for e in candidate_entries:
        if "tracker" in e.get("tags", []):
            continue
        for k, v in (e["query_params"] or {}).items():
            vs = v if isinstance(v, list) else [v]
            for val in vs:
                all_params[k].add(str(val)[:60])
            param_origins[k].append(urllib.parse.urlparse(e["url"]).path[:60])

    if all_params:
        for param, values in sorted(all_params.items()):
            origins_str = ", ".join(set(param_origins[param]))[:60]
            vals_str    = " | ".join(sorted(values)[:5])
            if len(values) > 5:
                vals_str += f" … (+{len(values)-5} more)"
            lines.append(f"  {param:<30} = {vals_str}")
            lines.append(f"  {'':30}   (on: {origins_str})")
    else:
        lines.append("  (none observed)")

    # ── GraphQL queries ───────────────────────────────────────────────────────
    graphql = [e for e in candidate_entries if "graphql" in e["tags"]]
    if graphql:
        h1("GRAPHQL OPERATIONS")
        for e in graphql:
            li(e["url"])
            if isinstance(e.get("request_body"), dict):
                op   = e["request_body"].get("operationName", "?")
                qstr = str(e["request_body"].get("query", ""))[:200]
                kv("operation:", op)
                kv("query (truncated):", qstr)

    # ── Repeated calls (pagination / infinite scroll) ─────────────────────────
    repeated = [e for e in candidate_entries if e.get("repeated")]
    if repeated:
        h1("REPEATED CALLS (pagination / infinite scroll)")
        seen = set()
        for e in repeated:
            url = e["url"][:100]
            if url not in seen:
                seen.add(url)
                li(url)

    # ── Auth / token patterns ─────────────────────────────────────────────────
    auth_calls = [e for e in candidate_entries if "auth" in e["tags"]]
    if auth_calls:
        h1("AUTH / TOKEN CALLS")
        for e in auth_calls:
            li(f"{e['method']} {e['url'][:100]}")

    # ── Recommended next steps ────────────────────────────────────────────────
    h1("RECOMMENDATIONS")
    all_urls = [e["url"] for e in candidate_entries]

    # Only look at params from non-tracker calls
    site_entries   = [e for e in candidate_entries if "tracker" not in e.get("tags", [])]
    site_params    = defaultdict(set)
    for e in site_entries:
        for k, v in (e["query_params"] or {}).items():
            site_params[k].add(str(v)[:60])

    # /papi/ is Njuškalo's internal API prefix — generalise to any /papi/-style path
    internal_apis = [e for e in site_entries if "internal-api" in e.get("tags", [])]
    if internal_apis:
        li(f"Found {len(internal_apis)} internal /papi/ API calls — these are the real data endpoints:")
        seen_paths = set()
        for e in internal_apis:
            path = urllib.parse.urlparse(e["url"]).path
            if path not in seen_paths:
                seen_paths.add(path)
                li(f"  → {e['method']} {path}")

    if any("/api/" in u for u in all_urls):
        li("Found /api/ endpoints — try calling them directly with curl/httpx.")

    versioned = [u for u in all_urls if re.search(r"/v\d+/", u)
                 and not any(t in u for t in ("tiktok", "google", "facebook"))]
    if versioned:
        li(f"Versioned REST found ({versioned[0][:80]}) — explore sibling endpoints.")

    if graphql:
        li("GraphQL found — send an introspection query: {__schema{types{name}}} to list all available types.")

    # Pagination: only params on site's own domain, not ep.* GA event params
    pagination_params = {k for k in site_params
                         if re.search(r"^(page|offset|limit|cursor|per_page|pageSize|from)$", k, re.I)}
    if pagination_params:
        li(f"Pagination params: {pagination_params} — increment to fetch more results.")

    # Filters: site params that look like actual search filters (bracket notation = Njuškalo style)
    filter_params = {k for k in site_params
                     if re.search(r"categor|sort|filter|geo\[|price\[|area\[|rooms\[|type\[|floor\[|date", k, re.I)}
    if filter_params:
        li(f"Filter/search params on site API:")
        for fp in sorted(filter_params):
            vals = " | ".join(sorted(site_params[fp])[:4])
            li(f"  {fp} = {vals}")

    lines.append("\n" + "═" * W)
    lines.append("TIP: Run again with more SEARCH_URLS to discover additional")
    lines.append("     parameters. Each filter you click in-browser generates a")
    lines.append("     new API call with different parameter combinations.")
    lines.append("═" * W + "\n")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    all_entries       = []
    candidate_entries = []
    all_page_states   = []

    # Auto-derive site name from hostname if not set in config
    site_name = SITE_NAME
    if not site_name:
        hostname  = urllib.parse.urlparse(SEARCH_URLS[0]["url"]).hostname or "site"
        hostname  = re.sub(r"^www\.", "", hostname)
        site_name = re.sub(r"[^\w]", "_", hostname)
    print(f"Site name: {site_name}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            slow_mo=80,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            viewport=None,
            locale="hr-HR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # Inject session cookie if provided
        if SESSION_COOKIE:
            domain = urllib.parse.urlparse(SEARCH_URLS[0]["url"]).hostname
            for part in SESSION_COOKIE.split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, value = part.partition("=")
                    context.add_cookies([{
                        "name":   name.strip(),
                        "value":  value.strip(),
                        "domain": domain,
                        "path":   "/",
                    }])

        page = context.new_page()

        # Warm up on the homepage first (loads auth cookies, CDN caches, etc.)
        homepage = urllib.parse.urlparse(SEARCH_URLS[0]["url"])
        warmup_url = f"{homepage.scheme}://{homepage.netloc}"
        print(f"Warming up on {warmup_url} …")
        try:
            page.goto(warmup_url, wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            pass
        time.sleep(2)

        for search in SEARCH_URLS:
            state = capture_page(page, search, all_entries, candidate_entries, site_name)
            if state:
                all_page_states.append(state)
            time.sleep(2)

        browser.close()

    # ── Write outputs ──────────────────────────────────────────────────────────
    out_all   = OUTPUT_DIR / f"{site_name}_network_log.json"
    out_cands = OUTPUT_DIR / f"{site_name}_api_candidates.json"
    out_rep   = OUTPUT_DIR / f"{site_name}_api_report.txt"

    out_all.write_text(
        json.dumps(all_entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out_cands.write_text(
        json.dumps(candidate_entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = build_report(candidate_entries, site_name, all_page_states)
    out_rep.write_text(report, encoding="utf-8")

    print(f"\n{'═'*65}")
    print(f"  All requests  → {out_all}   ({len(all_entries)} entries)")
    print(f"  Candidates    → {out_cands}  ({len(candidate_entries)} entries)")
    print(f"  Report        → {out_rep}")
    if SAVE_HTML:
        for search in SEARCH_URLS:
            safe_label = re.sub(r"[^\w\-]", "_", search["label"]).strip("_").lower()
            print(f"  HTML          → {OUTPUT_DIR / f'{site_name}_{safe_label}.html'}")
            state_f = OUTPUT_DIR / f"{site_name}_{safe_label}_state.json"
            if state_f.exists():
                print(f"  State JSON    → {state_f}")
    print(f"{'═'*65}")
    print(report)


if __name__ == "__main__":
    main()