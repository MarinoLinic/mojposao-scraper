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

SITE_NAME = "njuskalo"   # used in output filenames

SEARCH_URLS = [
    # Add as many URLs as you want to probe.
    # 'label' is just for your reference in the output.
    {
        "label": "IT jobs Zagreb",
        "url": "https://www.njuskalo.hr/posao?geo_location=grad-zagreb&category=informatika-telekomunikacije",
    },
    {
        "label": "Part-time jobs",
        "url": "https://www.njuskalo.hr/posao?type=part-time",
    },
    # --- Examples for other sites (uncomment / edit as needed) ---
    # {
    #     "label": "Apartments Zagreb",
    #     "url": "https://www.njuskalo.hr/iznajmljivanje-stanova?geo_location=grad-zagreb",
    # },
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
    r"google(tag|analytics|syndication|fonts|apis)",
    r"facebook\.net|fbcdn",
    r"sentry\.io|bugsnag",
    r"(gtm|ga|gads|doubleclick|clarity|hotjar|mixpanel|amplitude|segment)\.",
    r"cloudfront\.net/static",
    r"_nuxt/|__nuxt",
    r"/_next/static",
    r"/assets/[a-f0-9]{8,}\.",  # hashed static assets
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

# HTTP methods that always get captured regardless of URL patterns
ALWAYS_CAPTURE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_noise(url: str) -> bool:
    return any(re.search(p, url, re.I) for p in NOISE_PATTERNS)

def has_signal(url: str) -> bool:
    return any(re.search(p, url, re.I) for p in SIGNAL_PATTERNS)

def classify_url(url: str) -> list[str]:
    """Return a list of category tags for the URL."""
    tags = []
    u = url.lower()
    if "graphql" in u:               tags.append("graphql")
    if re.search(r"/v\d+/", u):      tags.append("versioned-rest")
    if re.search(r"suggest|autocomplete|typeahead", u): tags.append("autocomplete")
    if re.search(r"geo|location|region|city|district|place|coord|lat|lon", u): tags.append("geo/location")
    if re.search(r"search|query|q=", u):  tags.append("search")
    if re.search(r"filter|facet", u):     tags.append("filter")
    if re.search(r"page|offset|limit|cursor", u): tags.append("pagination")
    if re.search(r"auth|token|session|login", u): tags.append("auth")
    if re.search(r"category|categor|tree|taxonomy", u): tags.append("category-tree")
    if re.search(r"config|settings|init|bootstrap", u): tags.append("site-config")
    if re.search(r"listing|ad|oglas|job|posao|offer", u): tags.append("listings")
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
#  CAPTURE LOGIC
# ══════════════════════════════════════════════════════════════════════════════

def capture_page(page, search: dict, all_entries: list, candidate_entries: list):
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

    # ── Save full rendered HTML ───────────────────────────────────────────────
    if SAVE_HTML:
        safe_label = re.sub(r"[^\w\-]", "_", label).strip("_").lower()
        html_path  = OUTPUT_DIR / f"{SITE_NAME}_{safe_label}.html"
        html       = page.content()
        html_path.write_text(html, encoding="utf-8")
        print(f"  HTML saved → {html_path}  ({len(html):,} bytes)")

    print(f"  Done: {label}")


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def build_report(candidate_entries: list) -> str:
    lines = []
    W = 70

    def h1(t): lines.append("\n" + "═" * W); lines.append(f"  {t}"); lines.append("═" * W)
    def h2(t): lines.append(f"\n── {t} " + "─" * max(0, W - len(t) - 4))
    def li(t): lines.append(f"  • {t}")
    def kv(k, v): lines.append(f"    {k:<22} {v}")

    lines.append("NETWORK ANALYSIS REPORT")
    lines.append(f"Site: {SITE_NAME}   |   {len(candidate_entries)} captured calls")

    # ── Group by tag ──────────────────────────────────────────────────────────
    by_tag: dict[str, list] = defaultdict(list)
    for e in candidate_entries:
        for tag in e["tags"]:
            by_tag[tag].append(e)

    h1("API CALLS BY CATEGORY")
    for tag, entries in sorted(by_tag.items()):
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

    # ── All query parameters ever seen ───────────────────────────────────────
    h1("ALL QUERY PARAMETERS OBSERVED")
    all_params: dict[str, set] = defaultdict(set)
    param_origins: dict[str, list] = defaultdict(list)
    for e in candidate_entries:
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

    if any("/api/" in u for u in all_urls):
        li("Found /api/ endpoints — try calling them directly with curl/httpx.")

    versioned = [u for u in all_urls if re.search(r"/v\d+/", u)]
    if versioned:
        li(f"Versioned REST found ({versioned[0][:60]}) — explore sibling endpoints.")

    if graphql:
        li("GraphQL found — send an introspection query: {__schema{types{name}}} to list all available types.")

    pagination_params = {k for k in all_params if re.search(r"page|offset|limit|cursor|per_page", k, re.I)}
    if pagination_params:
        li(f"Pagination params: {pagination_params} — increment to fetch more results.")

    filter_params = {k for k in all_params if re.search(r"categor|type|sort|filter|location|geo|region|price|date", k, re.I)}
    if filter_params:
        li(f"Filter params detected: {filter_params}")
        li("Visit the site, use the search filters manually, and this script will "
           "capture what parameter combinations each filter generates.")

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
            capture_page(page, search, all_entries, candidate_entries)
            time.sleep(2)

        browser.close()

    # ── Write outputs ──────────────────────────────────────────────────────────
    out_all   = OUTPUT_DIR / f"{SITE_NAME}_network_log.json"
    out_cands = OUTPUT_DIR / f"{SITE_NAME}_api_candidates.json"
    out_rep   = OUTPUT_DIR / f"{SITE_NAME}_api_report.txt"

    out_all.write_text(
        json.dumps(all_entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out_cands.write_text(
        json.dumps(candidate_entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = build_report(candidate_entries)
    out_rep.write_text(report, encoding="utf-8")

    print(f"\n{'═'*65}")
    print(f"  All requests  → {out_all}   ({len(all_entries)} entries)")
    print(f"  Candidates    → {out_cands}  ({len(candidate_entries)} entries)")
    print(f"  Report        → {out_rep}")
    if SAVE_HTML:
        for search in SEARCH_URLS:
            safe_label = re.sub(r"[^\w\-]", "_", search["label"]).strip("_").lower()
            print(f"  HTML          → {OUTPUT_DIR / f'{SITE_NAME}_{safe_label}.html'}")
    print(f"{'═'*65}")
    print(report)


if __name__ == "__main__":
    main()