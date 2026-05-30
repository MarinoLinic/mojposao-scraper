# Njuškalo.hr — Complete Scraping & API Reference

> **Captured:** 2026-05-28 | **Base URL:** `https://www.njuskalo.hr` | **Currency:** EUR (€) | **Language:** Croatian (HR)

---

## Table of Contents

1. [Site Overview & Statistics](#1-site-overview--statistics)
2. [Architecture: How the Site Works](#2-architecture-how-the-site-works)
3. [The `__INITIAL_STATE__` Pattern — Primary Data Source](#3-the-__initial_state__-pattern--primary-data-source)
4. [Page Layout & HTML Skeleton](#4-page-layout--html-skeleton)
5. [HTML Structure: Listing Cards in Detail](#5-html-structure-listing-cards-in-detail)
6. [CSS/BeautifulSoup Scraping — Full Parser](#6-cssbeautifulsoup-scraping--full-parser)
7. [Internal `/papi/` API Endpoints](#7-internal-papi-api-endpoints)
8. [Listing Pages — URL Structure & Parameters](#8-listing-pages--url-structure--parameters)
9. [Filter Reference: Real Estate (For Sale)](#9-filter-reference-real-estate-for-sale)
10. [Filter Reference: Real Estate (Rental)](#10-filter-reference-real-estate-rental)
11. [Filter Reference: Cars & Vehicles](#11-filter-reference-cars--vehicles)
12. [Filter Reference: Blago / General Marketplace](#12-filter-reference-blago--general-marketplace)
13. [Location / Geo System](#13-location--geo-system)
14. [Category Tree](#14-category-tree)
15. [Listing Data Schema](#15-listing-data-schema)
16. [Image URL System](#16-image-url-system)
17. [Pagination](#17-pagination)
18. [Homepage & Marketplace State Structures](#18-homepage--marketplace-state-structures)
19. [Scraping Strategy & Complete Code Templates](#19-scraping-strategy--complete-code-templates)
20. [Complete URL Parameter Quick Reference](#20-complete-url-parameter-quick-reference)

---

## 1. Site Overview & Statistics

Njuškalo.hr is Croatia's largest general classifieds site (comparable to OLX or Craigslist). Key scale figures as of capture date:

| Section | Listings | Pages (25/page) |
|---|---|---|
| Auto Moto Nautika | 1,209,378 | ~48,375 |
| Nekretnine (Real Estate) | 183,722 | ~7,349 |
| Apartments for rent (Zagreb + Zagrebačka) | 5,902 | 237 |
| Apartments for sale (Zagreb filtered) | 174 | 7 |
| Cars for sale (Zagreb) | 14,689 | 588 |
| Pronađeno Blago | 187,971 | 7,519 |

**Top navigation sections (from `main.mainNavigationCategories`):**

| ID | Title | URL |
|---|---|---|
| `2` | Auto Moto Nautika | `/auto-moto` |
| `1` | Nekretnine | `/nekretnine` |
| `marketplace` | Marketplace | `/marketplace` |
| `njupop` | Katalozi | `https://katalozi.njuskalo.hr` |

---

## 2. Architecture: How the Site Works

### Vue.js SSR SPA
Njuškalo is a **Vue.js Single Page Application rendered server-side**. The server returns complete HTML including all listing data already embedded as a JSON blob (`window.__INITIAL_STATE__`). After the browser loads, Vue hydrates and takes over navigation via XHR calls to `/papi/` endpoints.

**For scraping this means:**
- Plain `GET` requests to listing URLs return complete data — no JavaScript execution needed
- The `/papi/` endpoints are not needed at all for basic scraping; they are only called when the user interacts with the page (changes filters, navigates categories)
- All listing data, pagination info, and filter state is available in the raw HTML response

### Request Flow

```
Scraper → GET https://www.njuskalo.hr/prodaja-stanova?{filters}
            └─► Server returns HTML with:
                  1. Rendered listing cards (CSS-parseable)
                  2. <script>window.__INITIAL_STATE__={...}</script>
                       └─► Contains IDENTICAL data in structured JSON
```

### Required Headers
No authentication, cookies, or special headers needed for public listing pages. Recommended minimal headers:

```http
GET /prodaja-stanova?sort=new HTTP/1.1
Host: www.njuskalo.hr
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: hr-HR,hr;q=0.9,en;q=0.7
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36
```

---

## 3. The `__INITIAL_STATE__` Pattern — Primary Data Source

### Extraction from HTML

The state is embedded in a `<script>` tag near the bottom of the `<body>`:

```html
<script>window.__INITIAL_STATE__={"main":{...},"browseListingsStore":{...}}</script>
```

**Python extraction:**

```python
import re
import json

def extract_initial_state(html: str) -> dict:
    """Extract and parse window.__INITIAL_STATE__ from page HTML."""
    match = re.search(
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>',
        html,
        re.DOTALL
    )
    if not match:
        raise ValueError("__INITIAL_STATE__ not found in HTML")
    return json.loads(match.group(1))

# Usage
state = extract_initial_state(html)
page_data = state['browseListingsStore']['pageData']
listings   = page_data['regularListings']   # list of dicts
```

> **Note:** The JSON blob is large (50–200KB per page) but always valid JSON. The `re.DOTALL` flag is essential because the JSON spans many lines.

### Top-Level State Structure

```
window.__INITIAL_STATE__
├── main                               # App-wide state (same on every page)
│   ├── user                           # null if not logged in
│   ├── featureFlags                   # A/B flags, feature toggles
│   ├── mainNavigationCategories       # Top 4 nav links
│   ├── serverTime                     # ISO timestamp of server render
│   └── banners / trackers / siteNotice
│
└── browseListingsStore                # Present on all listing/search pages
    ├── pageData                       # All listings + pagination + filter config
    └── stateTokens                    # Internal state tokens for SPA
```

**For the homepage** (`/`): key is `homePage` instead of `browseListingsStore`  
**For the marketplace** (`/marketplace`): key is `homeMarketplacePage`

### `browseListingsStore.pageData` — All Keys

```python
pd = state['browseListingsStore']['pageData']

# --- Pagination ---
pd['listingsCount']        # int   total matching results, e.g. 174
pd['totalPageCount']       # int   total pages at 25/page, e.g. 7

# --- Category identity ---
pd['categoryId']           # int   e.g. 9580 (prodaja-stanova)
pd['rootSlug']             # str   e.g. "prodaja-stanova"
pd['leafSlug']             # str   sub-category slug if at leaf level
pd['resultsType']          # str   e.g. "standard"
pd['displayType']          # str   e.g. "list"
pd['isLeaf']               # bool
pd['isFiltered']           # bool  true if any filters are active
pd['isFilteredWithAuxFields']  # bool
pd['hasMapView']           # bool  true if map tab available

# --- Listing data (5 buckets) ---
pd['promotedListings']     # list  paid VauVau promoted ads (shown at top)
pd['userPromotedListings'] # list  user-level promoted ads
pd['regularListings']      # list  main paginated results (~25 per page)
pd['latestListings']       # list  newest listings (sidebar strip, title-only)
pd['superVauListings']     # list  top-tier banner ads (usually empty on search pages)

# --- SEO ---
pd['meta']                 # dict  title, description, keywords, og* fields
pd['breadcrumbs']          # list  [{caption, route, active}, ...]
pd['canonicalUrl']         # str   canonical URL for this page
pd['structuredData']       # dict  JSON-LD schema.org data

# --- Filter state (mirrors URL params) ---
pd['fields']               # dict  current active filter values
pd['fieldsMapper']         # dict  mapping from field names to URL params
pd['urlParametersOrder']   # list  canonical param ordering (76/75/72/20 items)
pd['slugAffectingFields']  # list  fields that change the URL slug

# --- Filter UI configuration ---
pd['filtersLayout']        # dict  complete filter form config with all choices
pd['sortLayout']           # dict  sort selector config with all choices
pd['categoryFilterAttribute']  # str

# --- Other ---
pd['popularTags']          # list  trending search tags
pd['featuredStores']       # list  featured agency/store cards
pd['categories']           # list  sub-category navigation links
pd['comparedListings']     # list  items in compare basket
pd['isCompareAvailable']   # bool
pd['bannerZones']          # list  DFP ad zone names used on this page
pd['noResultsContent']     # dict/null  shown when no results
```

---

## 4. Page Layout & HTML Skeleton

Understanding the page skeleton helps you find the right containers quickly.

```
<html>
  <head>
    <!-- CSS from static.njuskalo.hr -->
    <!-- meta tags, title, canonical -->
  </head>
  <body>
    <header>...</header>
    <main role="main">
      <div class="wrap-content-primary">

        <!-- LEFT COLUMN: filters + listing list -->
        <div class="content-main">
          <!-- Filter form (renders active filters) -->
          <div class="ContentHeader cf ContentHeader--alpha ...">
            <form ...>  <!-- filter inputs -->
            </form>
            <!-- Sort selector, result count, map toggle -->
          </div>

          <!-- ① Featured Stores section (agencies) -->
          <section class="EntityList EntityList--FeaturedStore ...">
            <h2 class="EntityList-groupTitle">Istaknute Njuškalo trgovine</h2>
            <ul class="EntityList-items">
              <li class="EntityList-item ... EntityList-item--FeaturedStore">
                <!-- agency logo + sub-listing cards -->
              </li>
            </ul>
          </section>

          <!-- ② VauVau (promoted) listings section -->
          <section class="EntityList EntityList--VauVau ...">
            <h2 class="EntityList-groupTitle">Vau Vau Njuškalo oglasi</h2>
            <ul class="EntityList-items">
              <li class="EntityList-item EntityList-item--n1 EntityList-item--VauVau">
                <article class="entity-body cf">...</article>
              </li>
              <!-- ... up to 6 promoted listings -->
            </ul>
          </section>

          <!-- ③ Regular listings section (main results) -->
          <section class="EntityList EntityList--Regular ...">
            <h2 class="EntityList-groupTitle">Njuškalo oglasi</h2>
            <ul class="EntityList-items">
              <li class="EntityList-item EntityList-item--n1 EntityList-item--Regular">
                <article class="entity-body cf">...</article>
              </li>
              <!-- banner slots interspersed (class EntityList-item--banner) -->
              <!-- up to 25 regular listings per page -->
            </ul>
          </section>

          <!-- Pagination nav -->
          <div class="PaginationContainer PaginationContainer--bottom">...</div>
        </div>

        <!-- RIGHT COLUMN: sidebar -->
        <div class="content-supplementary">
          <!-- Latest listings strip -->
          <div class="EntityList EntityList--Latest ...">
            <h2 class="EntityListBlockTitle">Posljednji oglasi</h2>
            <ul class="EntityList-items">
              <li class="EntityList-item EntityList-item--n1 EntityList-item--Latest">
                <!-- title-only, no price/image -->
              </li>
              <!-- 6 latest listings -->
            </ul>
          </div>
          <!-- Ad slots, saved search widgets -->
        </div>

      </div>
    </main>

    <!-- INITIAL STATE (bottom of body, before </body>) -->
    <script>window.__INITIAL_STATE__={...}</script>
    <script src="https://static.njuskalo.hr/dist/..."></script>
  </body>
</html>
```

### Page-Level CSS Classes Reference

| Class | Description |
|---|---|
| `.content-main` | Left column (filters + listings) |
| `.content-supplementary` | Right sidebar |
| `.ContentHeader` | Filter form + sort controls at top of listing column |
| `.EntityList` | A section of listings (one per type: FeaturedStore, VauVau, Regular) |
| `.EntityList-groupTitle` | Section heading (`<h2>`) |
| `.EntityList-items` | `<ul>` containing listing `<li>` elements |
| `.PaginationContainer` | Pagination nav (appears at top and bottom) |

### `EntityList` Section Class Modifiers

Each `<section class="EntityList ...">` has additional modifier classes:

| Modifier | Description |
|---|---|
| `EntityList--FeaturedStore` | Agency/shop featured blocks (3 on sample page) |
| `EntityList--VauVau` | Promoted paid listings (6 on sample page) |
| `EntityList--Regular` | Standard paginated listings (25 on sample page) |
| `EntityList--Latest` | Latest listings sidebar (6, title-only, in `.content-supplementary`) |
| `EntityList--Standard` | Layout variant for list view |
| `EntityList--Small` | Compact layout variant (used for Latest) |
| `EntityList--itemCount_N` | Count of items in this section (e.g. `EntityList--itemCount_25`) |
| `EntityList--ListItemVauVauAd` | Item render type for VauVau |
| `EntityList--ListItemRegularAd` | Item render type for regular ads |
| `EntityList--ListItemLatestAd` | Item render type for latest ads |
| `EntityList--ListItemFeaturedStore` | Item render type for featured stores |

---

## 5. HTML Structure: Listing Cards in Detail

### 5.1 `EntityList-item` `<li>` Class Combinations

Every listing item is a `<li class="EntityList-item ...">`. The classes carry important metadata:

| Class Pattern | Meaning |
|---|---|
| `EntityList-item--n{N}` | Position in list (1-based index) |
| `EntityList-item--VauVau` | Paid promoted listing (from `promotedListings` bucket) |
| `EntityList-item--Regular` | Standard listing |
| `EntityList-item--Regular EntityList-item--VauVau` | Both flags: a promoted listing mixed into regular section |
| `EntityList-item--Latest` | Newest listing (title-only, no price/image in HTML) |
| `EntityList-item--FeaturedStore` | Agency card with sub-listings |
| `EntityList-item--banner` | Ad banner placeholder (no listing data; always has class `hidden`) |

**Observed on a typical apartments-for-sale page:**
- 3× `FeaturedStore` (agencies)
- 7× `VauVau` (6 pure promoted + 1 Regular+VauVau)
- 25× `Regular` (of which some also have `VauVau`)
- 6× `Latest` (sidebar, title-only)
- 8× `banner` (ad slots, all `hidden`)

### 5.2 Standard Listing Card (VauVau / Regular) — Annotated HTML

```html
<li class="EntityList-item EntityList-item--n1 EntityList-item--VauVau">
  <!--[-->
  <article class="entity-body cf">

    <!-- ① TITLE + URL -->
    <h3 class="entity-title">
      <a href="/nekretnine/zagreb-crnomerec-keglic-4-soban-stan-nkp-70-m2-oglas-50659088"
         class="link"
         name="50659088"                    <!-- listing ID is here as `name` attr -->
         data-href="/nekretnine/..."         <!-- also here (Vue SPA routing) -->
         data-faux-anchor="true">
        <!--[-->
        <span>Zagreb, Črnomerec, Keglić, 4 soban stan NKP 70 m2</span>
        <!--]-->
      </a>
    </h3>

    <!-- ② THUMBNAIL IMAGE -->
    <div class="entity-thumbnail">
      <a href="/nekretnine/..." class="link" data-href="/nekretnine/..." data-faux-anchor="true">
        <!--[--><!--[-->
        <img class="img entity-thumbnail-img"
             loading="lazy"
             src="https://www.njuskalo.hr/image-200x150/nekretnine/zagreb-crnomerec-keglic-4-soban-stan-nkp-70-m2-slika-278369492.jpg"
             alt=""
             data-v-8803c1f9="">
        <!--]--><!--]-->
      </a>
    </div>

    <!-- ③ DESCRIPTION / KEY FACTS (abstracts) -->
    <!----><div class="entity-description">
      <!----><!--[--><!--[-->
      <!----> <!--[-->Stan u stambenoj zgradi, 12. kat<!--]--><br><!--]-->
      <!--[--><span class="entity-description-itemCaption">Lokacija:</span>
              <!--[-->Črnomerec, Črnomerec<!--]--><br><!--]-->
      <!--]--><!--]-->
    </div>

    <!-- ④ PUBLICATION DATE -->
    <div class="entity-pub-date">
      <span class="label">Objavljen:</span>
      <time class="date date--full"
            datetime="2026-05-28T11:48:28.000Z"   <!-- ISO 8601 timestamp -->
            pubdate="pubdate">
        28.05.2026.                                 <!-- HR format DD.MM.YYYY. -->
      </time>
    </div>

    <!-- (video call option label, if applicable) -->
    <!--[--><!--]-->

    <!-- ⑤ USER TOOLS (save button) -->
    <!----><div class="entity-tools">
      <ul class="tool-items">
        <li class="tool-item">
          <!--[-->
          <button class="icon-item tool tool--SaveAd js-veza-save_ad"
                  type="button"
                  title="Spremi oglas">
            <span class="icon icon--action icon--xs icon--save-item">Spremi oglas</span>
          </button>
          <!--]-->
        </li>
        <!---->
      </ul>
    </div>

    <!-- ⑥ FEATURE BADGES (map, ground plan, video, virtual tour, etc.) -->
    <div class="entity-features">
      <ul class="feature-items cf">
        <!----><li class="feature-item">
          <button type="button"
                  class="icon-item feature feature--Map"
                  title="Ovaj oglas je pozicioniran na karti"
                  data-href="/nekretnine/...-oglas-50659088?tab=map"
                  data-faux-anchor="true"
                  role="link">
            <!--[--><span class="icon icon--action icon--s icon--map">Prikaži na mapi</span><!--]-->
          </button>
        </li>
        <!-- Other possible feature badges (all optional):
             feature--GroundPlan  → "Tlocrt" (ground plan attached)
             feature--Video       → "Video" (video attached)
             feature--VirtualTour → "Virtualna šetnja"
             feature--HKSCertificate → HKS certificate
        -->
      </ul>
    </div>

    <!-- ⑦ PRICE -->
    <!----><div class="entity-prices">
      <ul class="price-items cf">
        <!--[-->
        <li class="price-item">
          <strong class="price price--hrk">315.000 €</strong>
                  <!-- note: class is "price--hrk" even though currency is EUR (legacy naming) -->
        </li>
        <!--]-->
      </ul>
    </div>

  </article>
  <!--]-->
</li>
```

### 5.3 Regular (Non-Promoted) Listing Card Differences

A pure `EntityList-item--Regular` listing is identical except:
- The `<li>` `data-href` attribute on the title `<a>` is **absent** (no `data-href` or `data-faux-anchor` on plain regular items — just a plain `href`)

```html
<!-- Regular (non-promoted) title link — no data-href, no data-faux-anchor -->
<h3 class="entity-title">
  <a href="/nekretnine/brezovica-novogradnja-cetverosoban-stan-86m2-oglas-48378445"
     class="link"
     name="48378445">
    <span>Dreamville Brezovica NOVOGRADNJA četverosoban stan 86 m²</span>
  </a>
</h3>
```

### 5.4 Latest (Sidebar) Listing Card — Title Only

These are in the right sidebar, class `EntityList-item--Latest`. They contain **only the title link** — no image, no price, no description:

```html
<li class="EntityList-item EntityList-item--n1 EntityList-item--Latest">
  <!--[-->
  <article class="entity-body cf">
    <h3 class="entity-title">
      <a href="/numizmatika-novcanice/north-korea-sjeverna-koreja-1988-10-chon-unc-oglas-50695121"
         class="link"
         name="50695121"
         data-href="/numizmatika-novcanice/north-korea-sjeverna-koreja-1988-10-chon-unc-oglas-50695121"
         data-faux-anchor="true">
        <!--[--><span>NORTH KOREA / SJEVERNA KOREJA (1988) 10 Chon UNC</span><!--]-->
      </a>
    </h3>
    <!-- everything else is empty comment blocks -->
  </article>
  <!--]-->
</li>
```

### 5.5 Featured Store (Agency) Card

These are agency listings. The agency has a logo and a list of sub-items (individual listings):

```html
<li class="EntityList-item EntityList-item--n1 is-withSubitems EntityList-item--FeaturedStore">
  <article class="entity-body cf">

    <!-- Agency logo -->
    <div class="entity-thumbnail entity-thumbnail--4by3">
      <a href="/agencija/roelrealestate" class="link" data-href="/agencija/roelrealestate" data-faux-anchor="true">
        <img class="img entity-thumbnail-img"
             src="https://www.njuskalo.hr/logo-140x140/roelrealestate-logo2-2806376.jpg?quality=100"
             alt="">
      </a>
    </div>

    <!-- Sub-listings -->
    <div class="entity-subitems-list">
      <ul class="entity-subitems">
        <!--[--><!--[-->
        <li class="entity-subitem">
          <h3 class="entity-subitem-title">
            <a href="/nekretnine/dvosobni-stan-zagreb-pescenica-65.57-m2-oglas-50072028" class="link" ...>
              <span>Dvosobni stan, Zagreb, Pešćenica, 65,57 m2</span>
            </a>
          </h3>
          <div class="entity-subitem-features">
            <ul class="feature-items cf">
              <li class="feature-item">
                <button class="icon-item feature feature--Map" ...>...</button>
              </li>
              <li class="feature-item">
                <button class="icon-item feature feature--GroundPlan" ...>...</button>
              </li>
            </ul>
          </div>
        </li>
        <!-- more entity-subitem -->
        <!--]--><!--]-->
      </ul>
    </div>

  </article>
</li>
```

### 5.6 Banner Placeholder Items

These `<li>` elements are ad containers — always have class `hidden` and contain no listing data:

```html
<li class="EntityList-item EntityList-item--banner EntityList-bannerContainer
           BannerAlignment BannerAlignment--center hidden"
    data-v-f49b575f="">
  <div class="BannerAlignment-inner">
    <div id="dfp-zone-container-..."></div>
  </div>
</li>
```

Banner items appear between regular listings. They are always `hidden` in SSR HTML (loaded dynamically by JS). **Skip them in any HTML scraper.**

### 5.7 Feature Badge Classes (`feature--*`)

The `.entity-features` div contains zero or more badge buttons. The `feature--*` class indicates the badge type:

| Class | `title` attribute text | Corresponding state field |
|---|---|---|
| `feature--Map` | "Ovaj oglas je pozicioniran na karti" | `hasMap: true` |
| `feature--GroundPlan` | "Uz ovaj oglas priložen je tlocrt" | `hasGroundPlan: true` |
| `feature--Video` | "Video" | `hasVideo: true` |
| `feature--VirtualTour` | "Virtualna šetnja" | `hasVirtualTour: true` |
| `feature--HKSCertificate` | "HKS certifikat" | `hasHKSCertificate: true` |

The `data-href` on each badge button links directly to the relevant tab of the detail page, e.g. `?tab=map`, `?tab=ground-plan`, `?tab=video`.

### 5.8 Pagination HTML

The pagination appears both above and below the listing list:

```html
<div class="PaginationContainer PaginationContainer--top" data-v-f49b575f="">
  <nav class="Pagination">
    <ul class="Pagination-items cf">

      <!-- Current page (active, no href) -->
      <li class="Pagination-item Pagination-item--active">
        <button type="button"
                class="Pagination-link is-active"
                data-href="/prodaja-stanova?geo[locationIds]=...&page=1">
          <strong><span class="label--s">Stranica</span> 1</strong>
        </button>
      </li>

      <!-- Other pages (use data-href, not href) -->
      <li class="Pagination-item">
        <button type="button"
                class="Pagination-link"
                data-href="/prodaja-stanova?geo[locationIds]=...&page=2">
          2
        </button>
      </li>

      <!-- Ellipsis for large page ranges -->
      <li class="Pagination-item Pagination-item--ellipsis">
        <span>…</span>
      </li>

      <!-- Last page -->
      <li class="Pagination-item">
        <button ... data-href="...&page=7">7</button>
      </li>

    </ul>
  </nav>
</div>
```

> **Important:** Page links use `data-href` (not `href`) because this is a Vue SPA. Do **not** try to follow `href` attributes for pagination. Build page URLs manually using `?page=N`.

---

## 6. CSS/BeautifulSoup Scraping — Full Parser

Use this when you want HTML-based scraping as a fallback or cross-check to the `__INITIAL_STATE__` approach.

```python
from bs4 import BeautifulSoup
import re

def parse_listing_page_html(html: str) -> dict:
    """
    Parse a Njuškalo listing page from raw HTML.
    Returns dict with sections, listings, and pagination info.
    """
    soup = BeautifulSoup(html, 'html.parser')

    result = {
        'promoted_listings': [],
        'regular_listings': [],
        'latest_listings': [],
        'featured_stores': [],
        'pagination': {},
    }

    # ── Parse all EntityList sections ─────────────────────────────────
    for section in soup.select('section.EntityList'):
        classes = section.get('class', [])

        if 'EntityList--FeaturedStore' in classes:
            result['featured_stores'].extend(_parse_featured_stores(section))

        elif 'EntityList--VauVau' in classes and 'EntityList--Regular' not in classes:
            # Pure VauVau section (promoted)
            for li in section.select('li.EntityList-item'):
                li_classes = li.get('class', [])
                if 'EntityList-item--banner' in li_classes:
                    continue
                card = _parse_listing_card(li)
                if card:
                    card['listing_type'] = 'promoted'
                    result['promoted_listings'].append(card)

        elif 'EntityList--Regular' in classes:
            # Regular listings (may include some VauVau items too)
            for li in section.select('li.EntityList-item'):
                li_classes = li.get('class', [])
                if 'EntityList-item--banner' in li_classes:
                    continue
                card = _parse_listing_card(li)
                if card:
                    is_vau = 'EntityList-item--VauVau' in li_classes
                    card['listing_type'] = 'promoted' if is_vau else 'regular'
                    result['regular_listings'].append(card)

    # ── Parse Latest listings (sidebar) ───────────────────────────────
    for div in soup.select('div.EntityList.EntityList--Latest'):
        for li in div.select('li.EntityList-item--Latest'):
            card = _parse_latest_card(li)
            if card:
                result['latest_listings'].append(card)

    # ── Parse pagination ───────────────────────────────────────────────
    result['pagination'] = _parse_pagination(soup)

    return result


def _parse_listing_card(li) -> dict | None:
    """Parse a standard listing card (VauVau or Regular) from a <li> element."""
    article = li.find('article', class_='entity-body')
    if not article:
        return None

    card = {}

    # --- ID and URL from title link ---
    title_a = article.select_one('h3.entity-title a')
    if not title_a:
        return None

    href = title_a.get('href') or title_a.get('data-href', '')
    card['url']   = 'https://www.njuskalo.hr' + href if href else ''
    card['title'] = title_a.get_text(strip=True)
    card['id']    = title_a.get('name')  # listing ID as string

    # Extract ID from URL as fallback
    if not card['id'] and href:
        m = re.search(r'-oglas-(\d+)$', href)
        if m:
            card['id'] = m.group(1)

    # --- Category slug from URL ---
    if href:
        parts = href.strip('/').split('/')
        card['category_slug'] = parts[0] if parts else ''
        # title_slug is parts[1] minus the "-oglas-{id}" suffix
        if len(parts) > 1:
            card['title_slug'] = re.sub(r'-oglas-\d+$', '', parts[1])

    # --- Thumbnail image ---
    img = article.select_one('.entity-thumbnail img.entity-thumbnail-img')
    card['image'] = img.get('src', '') if img else ''

    # --- Description / abstracts ---
    desc = article.select_one('.entity-description')
    if desc:
        # Get all text pieces, respecting caption spans
        abstracts = []
        for br_block in desc.children:
            pass  # simplified: just grab text
        card['description_text'] = desc.get_text(' ', strip=True)
        # Parse individual caption:value pairs
        card['abstracts'] = _parse_abstracts(desc)

    # --- Publication date ---
    time_el = article.select_one('time.date')
    if time_el:
        card['created_at']           = time_el.get('datetime', '')
        card['created_at_formatted'] = time_el.get_text(strip=True)

    # --- Price ---
    price_el = article.select_one('.price')
    if price_el:
        card['price_formatted'] = price_el.get_text(strip=True)
        card['price_eur']       = parse_price(card['price_formatted'])

    # --- Feature badges ---
    card['has_map']          = bool(article.select_one('.feature--Map'))
    card['has_ground_plan']  = bool(article.select_one('.feature--GroundPlan'))
    card['has_video']        = bool(article.select_one('.feature--Video'))
    card['has_virtual_tour'] = bool(article.select_one('.feature--VirtualTour'))
    card['has_hks_cert']     = bool(article.select_one('.feature--HKSCertificate'))

    # --- Listing type from li classes ---
    li_classes = li.get('class', [])
    card['is_promoted'] = 'EntityList-item--VauVau' in li_classes
    card['position']    = _extract_position(li_classes)

    return card


def _parse_abstracts(desc_div) -> list:
    """
    Parse the entity-description div into a list of {caption, value} dicts.
    Handles the Vue comment-node format (<!--[-->, <!---->, etc.).
    """
    abstracts = []
    html = str(desc_div)
    # Strip Vue comment nodes
    html_clean = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    soup = BeautifulSoup(html_clean, 'html.parser')

    current_caption = None
    # Walk through text nodes and spans
    for element in soup.div.children if soup.div else []:
        if hasattr(element, 'name'):
            if element.name == 'span' and 'entity-description-itemCaption' in element.get('class', []):
                current_caption = element.get_text(strip=True).rstrip(':')
            elif element.name == 'br':
                current_caption = None
        else:
            text = str(element).strip()
            if text and text not in ('', ' '):
                abstracts.append({'caption': current_caption, 'value': text})
                current_caption = None
    return abstracts


def _parse_latest_card(li) -> dict | None:
    """Parse a Latest (sidebar) listing — title and URL only."""
    title_a = li.select_one('h3.entity-title a')
    if not title_a:
        return None
    href = title_a.get('href') or title_a.get('data-href', '')
    card_id = title_a.get('name')
    if not card_id and href:
        m = re.search(r'-oglas-(\d+)$', href)
        if m:
            card_id = m.group(1)
    return {
        'id':    card_id,
        'url':   'https://www.njuskalo.hr' + href if href else '',
        'title': title_a.get_text(strip=True),
        'listing_type': 'latest',
    }


def _parse_featured_stores(section) -> list:
    """Parse FeaturedStore section — returns list of agency dicts with sub-listings."""
    stores = []
    for li in section.select('li.EntityList-item--FeaturedStore'):
        store = {}
        logo_a = li.select_one('.entity-thumbnail a')
        if logo_a:
            store['agency_url'] = 'https://www.njuskalo.hr' + logo_a.get('href', '')
        logo_img = li.select_one('.entity-thumbnail img')
        if logo_img:
            store['agency_logo'] = logo_img.get('src', '')

        sub_listings = []
        for sub in li.select('li.entity-subitem'):
            sub_a = sub.select_one('.entity-subitem-title a')
            if sub_a:
                sub_href = sub_a.get('href') or sub_a.get('data-href', '')
                sub_id   = sub_a.get('name')
                if not sub_id and sub_href:
                    m = re.search(r'-oglas-(\d+)$', sub_href)
                    if m:
                        sub_id = m.group(1)
                sub_listings.append({
                    'id':    sub_id,
                    'url':   'https://www.njuskalo.hr' + sub_href if sub_href else '',
                    'title': sub_a.get_text(strip=True),
                    'has_map':         bool(sub.select_one('.feature--Map')),
                    'has_ground_plan': bool(sub.select_one('.feature--GroundPlan')),
                })
        store['sub_listings'] = sub_listings
        stores.append(store)
    return stores


def _parse_pagination(soup) -> dict:
    """Extract pagination info from the page."""
    result = {'current_page': 1, 'total_pages': None, 'page_urls': []}

    nav = soup.select_one('.PaginationContainer .Pagination')
    if not nav:
        return result

    for item in nav.select('li.Pagination-item'):
        classes = item.get('class', [])
        btn = item.find('button')
        if not btn:
            continue

        data_href = btn.get('data-href', '')
        page_text = btn.get_text(strip=True)
        m = re.search(r'\d+', page_text)
        page_num = int(m.group()) if m else None

        if 'Pagination-item--active' in classes:
            result['current_page'] = page_num
        elif 'Pagination-item--ellipsis' not in classes and page_num:
            result['page_urls'].append({
                'page': page_num,
                'data_href': 'https://www.njuskalo.hr' + data_href if data_href.startswith('/') else data_href,
            })
            if result['total_pages'] is None or page_num > result['total_pages']:
                result['total_pages'] = page_num

    return result


def _extract_position(classes: list) -> int | None:
    """Extract position number from EntityList-item--nN class."""
    for cls in classes:
        m = re.match(r'EntityList-item--n(\d+)$', cls)
        if m:
            return int(m.group(1))
    return None


def parse_price(price_str: str) -> float | None:
    """
    Parse Croatian price format to float EUR.
    Examples: "315.000 €" → 315000.0, "1.800 €" → 1800.0,
              "45,00 €" → 45.0, "40 €" → 40.0, "1 €" → 1.0
    """
    if not price_str:
        return None
    digits = re.sub(r'[^\d,.]', '', price_str.strip())
    if not digits:
        return None
    if ',' in digits:
        # Has decimal: comma is decimal separator, period is thousands
        digits = digits.replace('.', '').replace(',', '.')
    else:
        # No decimal: period is thousands separator
        digits = digits.replace('.', '')
    try:
        return float(digits)
    except ValueError:
        return None
```

### CSS Selectors Quick Reference

| What to find | Selector |
|---|---|
| All listing sections | `section.EntityList` |
| VauVau (promoted) section | `section.EntityList.EntityList--VauVau` |
| Regular listings section | `section.EntityList.EntityList--Regular` |
| Latest (sidebar) section | `div.EntityList.EntityList--Latest` |
| All non-banner listing `<li>`s | `li.EntityList-item:not(.EntityList-item--banner)` |
| Promoted listing `<li>`s | `li.EntityList-item.EntityList-item--VauVau` |
| Regular listing `<li>`s | `li.EntityList-item.EntityList-item--Regular` |
| Listing article | `article.entity-body` |
| Title link | `h3.entity-title a` |
| Listing ID | `h3.entity-title a[name]` → `.get('name')` |
| Thumbnail image | `.entity-thumbnail img.entity-thumbnail-img` |
| Description/abstracts | `.entity-description` |
| Caption label | `span.entity-description-itemCaption` |
| Publication date | `time.date` → `.get('datetime')` for ISO, `.text` for HR format |
| Price | `strong.price` or `.price--hrk` |
| Map badge | `.feature--Map` |
| Ground plan badge | `.feature--GroundPlan` |
| Video badge | `.feature--Video` |
| Virtual tour badge | `.feature--VirtualTour` |
| Pagination nav | `.PaginationContainer .Pagination` |
| Active page button | `.Pagination-item--active button` |
| Page buttons | `.Pagination-item button[data-href]` |
| `__INITIAL_STATE__` script | `script` containing `window.__INITIAL_STATE__` |

---

## 7. Internal `/papi/` API Endpoints

These are XHR endpoints the Vue frontend calls after initial page load. They return clean JSON and require no authentication.

> **You don't need these for basic scraping** — the `__INITIAL_STATE__` already contains all data. Use these only when you need to enumerate all locations, categories, or vehicle brands programmatically.

### 7.1 Locations Hierarchy

```
GET /papi/pages/browse-listings/locations-hierarchy
```

| Param | Values | Notes |
|---|---|---|
| `level` | `0`, `1`, `2` | Hierarchy depth |
| `parentIds` | comma-separated IDs | Required for level 1 and 2 |

**Level 0** — All Croatian counties (21 entries, returns 24 with some sub-grouping):

```
GET /papi/pages/browse-listings/locations-hierarchy?level=0
```

Response shape:
```json
[
  { "id": 1153, "label": "Grad Zagreb", "value": 1153,
    "route": {"slugs": ["zagreb"], "query": {}}, "parentId": null },
  ...
]
```

**Level 1** — Districts within one or more counties:

```
GET /papi/pages/browse-listings/locations-hierarchy?level=1&parentIds=1153
GET /papi/pages/browse-listings/locations-hierarchy?level=1&parentIds=1153,1170
```

Response shape (grouped by county):
```json
[
  { "id": 1153, "label": "Grad Zagreb",
    "choices": [
      { "id": 1247, "label": "Brezovica", "value": 1247,
        "route": {"slugs": ["brezovica"], "query": {}}, "parentId": 1153 },
      { "id": 1248, "label": "Črnomerec", "value": 1248,
        "route": {"slugs": ["crnomerec"], "query": {}}, "parentId": 1153 },
      ...
    ]
  }
]
```

**Level 2** — Sub-districts (neighbourhoods) within districts:

```
GET /papi/pages/browse-listings/locations-hierarchy?level=2&parentIds=1247,1248,1249,1250,1251,1252,1253,1254,1255,1256,1257,1258,1259,1260,1261,1262,1263,1264
```

Response shape (grouped by district):
```json
[
  { "id": 1247, "label": "Brezovica",
    "choices": [
      { "id": 2595, "label": "Brezovica", "route": {"slugs": ["brezovica-brezovica"]}, "parentId": 1247 },
      { "id": 2827, "label": "Brebernica", "route": {"slugs": ["brezovica-brebernica"]}, "parentId": 1247 },
      ...
    ]
  },
  { "id": 1248, "label": "Črnomerec",
    "choices": [
      { "id": 2596, "label": "Bijenik", "route": {"slugs": ["crnomerec-bijenik"]}, "parentId": 1248 },
      { "id": 2597, "label": "Črnomerec", "route": {"slugs": ["crnomerec-crnomerec"]}, "parentId": 1248 },
      ...
    ]
  }
]
```

### 7.2 Category Hierarchy

```
GET /papi/pages/browse-listings/category-hierarchy
```

| Param | Values | Notes |
|---|---|---|
| `level` | `0`, `1`, `2` | Hierarchy depth |
| `parentIds` | comma-separated IDs | Required for level > 0 |

**Level 0** — All top-level categories (20 entries)  
**Level 1, parentIds=2** — Auto Moto sub-categories (7 entries)  
**Level 2, parentIds=13688** — Car condition sub-categories (2 entries: used/new)

Response shape (same as locations):
```json
[
  { "id": 13688, "label": "Osobni automobili", "value": 13688,
    "route": {"slugs": ["auti"], "query": {}}, "parentId": 2 },
  ...
]
```

### 7.3 Vehicles Hierarchy

```
GET /papi/pages/browse-listings/vehicles-hierarchy
```

| Param | Values |
|---|---|
| `level` | `0` (makes), `1` (models for a brand) |
| `parentIds` | Brand ID (for level 1) |

**Level 0** — All 108 car brands  
**Level 1** — Models for a brand: `?level=1&parentIds=10962` (Audi models)

### 7.4 Banner Targeting (skip for scraping)

```
POST /papi/pages/browse-listings/banner-targeting
Content-Type: application/json
```

Request body fields observed:
- `site`: `"www.njuskalo.hr"`
- `url`: full current page URL
- `mainsection`: `"nekretnine"` | `"auto-moto"` | `"blago"`
- `category`: e.g. `"prodaja-stanova"`, `"auti"`, `"iznajmljivanje-stanova"`
- `cont_type`: always `"kategorija"`
- `location`: e.g. `"grad-zagreb"`, `"grad-zagreb,zagrebacka"` (optional)
- `min_price`: `"null"` or price string e.g. `"185kE"`
- `max_price`: `"null"` or price string
- `body_type`: `"null"` (cars only)

---

## 8. Listing Pages — URL Structure & Parameters

### URL Format

```
https://www.njuskalo.hr/{category-slug}?{filters}
```

### Detail Page URL Format

```
https://www.njuskalo.hr/{categorySlug}/{titleSlug}-oglas-{id}
```

Example:
```
https://www.njuskalo.hr/nekretnine/zagreb-crnomerec-keglic-4-soban-stan-nkp-70-m2-oglas-50659088
```

Build from listing data:
```python
def listing_url(listing: dict) -> str:
    return (f"https://www.njuskalo.hr/"
            f"{listing['categorySlug']}/"
            f"{listing['titleSlug']}-oglas-{listing['id']}")
```

### Key Category Slugs

| Slug | Description | Category ID |
|---|---|---|
| `prodaja-stanova` | Apartments for sale | 9580 |
| `iznajmljivanje-stanova` | Apartments for rent | varies |
| `nekretnine` | All real estate | 1 |
| `auti` | All cars | 13688 |
| `rabljeni-auti` | Used cars | 7 |
| `novi-auti` | New cars | 13689 |
| `blago` | General marketplace treasure | 9798 |
| `auto-moto` | All vehicles | 2 |
| `gospodarska-vozila` | Commercial vehicles | 1149 |
| `oldtimeri` | Classic cars | 9 |
| `motori` | Motorcycles | 1148 |
| `kamperi-kamp-prikolice` | Campers & caravans | 12140 |
| `rezervni-dijelovi` | Spare parts & accessories | 9838 |
| `karambolirani-auti` | Crashed/salvage cars | 13506 |

### Universal Sort Parameter

Applies to all categories:

| `sort=` | Croatian label | Description |
|---|---|---|
| `new` | Najnoviji | Newest first (default) |
| `old` | Najstariji | Oldest first |
| `cheap` | S nižom cijenom | Price ascending |
| `expensive` | S višom cijenom | Price descending |
| `distance` | Po udaljenosti | Nearest first (requires `geo[lat/lng]`) |

---

## 9. Filter Reference: Real Estate (For Sale)

**URL:** `https://www.njuskalo.hr/prodaja-stanova?{params}`  
**Total valid URL parameters:** 76  
**Category ID:** 9580

### All Parameters by Category

#### Location
```
geo[locationIds]=1153              # Comma-separated county/district/sub-district IDs
geo[lat]=45.8150                   # Latitude for radius search
geo[lng]=15.9819                   # Longitude for radius search
geo[radius]=20                     # Radius in km
geo[address]=Zagreb                # Address string
# Legacy aliases (also work):
locationId=1153
locationIds=1153,1170
```

#### Price
```
price[min]=50000                   # EUR
price[max]=360000                  # EUR
```

#### Area
```
livingArea[min]=50                 # m²
livingArea[max]=100                # m²
```

#### Number of Rooms — `numberOfRooms` — type: `DiscreteSelectRange`

| Value | Label (HR) |
|---|---|
| `studio-apartment` | Garsonijera |
| `one-room` | 1-sobni |
| `two-rooms` | 2-sobni |
| `three-rooms` | 3-sobni |
| `four-rooms` | 4-sobni |
| `five-rooms` | 5+ |

Usage: `numberOfRooms[min]=two-rooms&numberOfRooms[max]=four-rooms`

#### Building Type — `flatBuildingType` — type: `Select`

| Value | Label |
|---|---|
| `flat-in-house` | U kući |
| `flat-in-residential-building` | U stambenoj zgradi |

#### Number of Floors — `flatFloorCount` — type: `Select`

| Value | Label |
|---|---|
| `single-floor` | Jednoetažni |
| `two-floor` | Dvoetažni |
| `multi-floor` | Višeetažni |

#### Balcony/Terrace — `balconyInfo` — type: `Select`

| Value | Label |
|---|---|
| `allthree` | Balkon ili lođa ili terasa |
| `balcony` | Balkon |
| `loggie` | Lođa (Loggia) |
| `terace` | Terasa |
| `nothing` | Ništa navedeno |

#### Building Features — `buildingInfo` — type: `MultipleCheckboxValueOne`

| Parameter | Label |
|---|---|
| `buildingInfo[new-building]=1` | Novogradnja |
| `buildingInfo[lift]=1` | Lift |
| `buildingInfo[invalid-can]=1` | Pristup za osobe s invaliditetom |
| `buildingInfo[city-gas]=1` | Gradski plin |

#### Furnishing & Condition — `furnishLevelAndCondition` — type: `MultipleCheckboxValueOne`

| Parameter | Label |
|---|---|
| `furnishLevelAndCondition[furnished]=1` | Potpuno namješten |
| `furnishLevelAndCondition[partially-furnished]=1` | Djelomično namješten |
| `furnishLevelAndCondition[unfurnished]=1` | Nenamješten |
| `furnishLevelAndCondition[unfinished-for-renovation]=1` | Roh-bau/Za renoviranje |

#### Heating System — `heatingSource` — type: `Select`

| Value | Label |
|---|---|
| `no-heating` | Nema sustav grijanja |
| `city-heating` | Gradska toplana |
| `gas-floor-heating` | Etažno plinsko centralno |
| `electricity-floor-heating` | Etažno centralno na struju |
| `common-boiler-room` | Zajednička kotlovnica |
| `fuel-oil-heating` | Peć na lož ulje |
| `gas-heating` | Peć na plin |
| `wood-heating` | Peć na drva |
| `briquettes-pellets-heating` | Peć na brikete/pelete |
| `solid-fuel-heating` | Peć na kruta goriva |
| `electric-heaters-and-radiators` | Grijalice i radijatori na struju |
| `heating-air-conditioning-and-ventilation-system` | Sustav grijanja, klimatizacije i ventilacije |
| `air-source-heat-pump` | Dizalica topline |

#### Energy Certificate — `subjectEnergyCertificate` — type: `DiscreteSelectRange`

| Value | Label |
|---|---|
| `a-plus` | A+ |
| `a` | A |
| `b` | B |
| `c` | C |
| `d` | D |
| `e` | E |
| `f` | F |
| `g` | G |

Usage: `subjectEnergyCertificate[min]=a&subjectEnergyCertificate[max]=c`

#### Floor Position — `buildingFloorPosition` — type: `DiscreteSelectRange`

| Value | Label |
|---|---|
| `basement` | Suteren |
| `ground-floor` | Prizemlje |
| `high-ground` | Visoko prizemlje |
| `1` – `24` | 1. – 24. |
| `25` | 25+ |
| `attic` | Potkrovlje |
| `high-attic` | Visoko potkrovlje |
| `penthouse` | Penthouse |

Usage: `buildingFloorPosition[min]=1&buildingFloorPosition[max]=5`

#### Total Building Floors — `buildingFloorCount` — type: `DiscreteSelectRange`

Values: `ground-floor`, `high-ground`, `1`–`24`, `25` (=25+)

#### Other Areas — `otherAreas` — type: `MultipleCheckboxValueOne`

| Parameter | Label |
|---|---|
| `otherAreas[garden]=1` | Dvorište/vrt |
| `otherAreas[basement]=1` | Podrum |
| `otherAreas[supa]=1` | Spremište/šupa |
| `otherAreas[barbecue]=1` | Roštilj |

#### Functionalities — `functionalities` — type: `MultipleCheckboxValueOne`

| Parameter | Label |
|---|---|
| `functionalities[bathtub]=1` | Kada |
| `functionalities[shower-cabin]=1` | Tuš kabina |
| `functionalities[floor-heating]=1` | Podno grijanje |
| `functionalities[fireplace]=1` | Kamin |

#### Year of Construction / Renovation — type: `YearRange`
```
yearOfConstruction[min]=2000
yearOfConstruction[max]=2020
yearOfRenovation[min]=2010
yearOfRenovation[max]=2024
```

#### Parking Spots — `numberOfParkingSpots` — type: `DiscreteSelectRange`

Values: `none`, `1`, `2`, `3`, `4`, `5`, `6`, `7` (=7+)

#### Parking Type — `parkingSpotType` — type: `MultipleCheckboxValueOne`

| Parameter | Label |
|---|---|
| `parkingSpotType[parking-garage]=1` | Garaža |
| `parkingSpotType[garage-spot]=1` | Garažno parkirno mjesto |
| `parkingSpotType[parking-outdoor-covered]=1` | Vanjsko natkriveno mjesto |
| `parkingSpotType[parking-garage-outdoor-notcovered]=1` | Vanjsko ne-natkriveno mjesto |
| `parkingSpotType[parking-public-free]=1` | Besplatni javni parking |
| `parkingSpotType[parking-public-not-free]=1` | Naplatni javni parking |

#### Swap Option — `switchOption` — type: `Select`

| Value | Label |
|---|---|
| `yes-flat-switch` | Moguća zamjena za drugu nekretninu |
| `no-flat-switch` | Nije moguća zamjena za drugu nekretninu |

#### Boolean Checkboxes
```
adsWithImages=1                    # Only listings with images
virtualTour=1                      # Only listings with virtual tour
videoCallOption=1                  # Video viewing available
includeOtherCategories=1           # Include luxury real estate
```

#### Hidden / Internal
```
sort=new                           # Sort order
page=1                             # Page number
product=...                        # Internal product parameter
categoryIds=9580                   # Category ID (usually in slug)
categoryId=9580
```

---

## 10. Filter Reference: Real Estate (Rental)

**URL:** `https://www.njuskalo.hr/iznajmljivanje-stanova?{params}`  
**Total valid URL parameters:** 75  
**Captured data:** 5,902 listings across 237 pages (Zagreb + Zagrebačka)

Rental shares almost all filters with for-sale (§9), with these **differences and additions**:

#### Present in Rental, Absent in For-Sale
```
petsAllowed=1                      # Kućni ljubimci dozvoljeni
airConditioning=1                  # Samo stanovi s klima uređajem
availableFromDate=1                # Odmah dostupno (available immediately)
```

#### `yearlyAvailability` — type: `Select`

| Value | Label |
|---|---|
| `all-year` | Dostupno cijele godine |
| `out-off-tourist-season` | Dostupno samo van turističke sezone |
| `during-tourist-season` | Dostupno samo unutar turističke sezone |

#### Rental-Specific `functionalities` values

| Parameter | Label |
|---|---|
| `functionalities[antitheft-doors]=1` | Protuprovalna vrata |
| `functionalities[dishwasher]=1` | Perilica posuđa |

> Note: Rental does **not** have `bathtub`, `shower-cabin`, `floor-heating`, or `fireplace` in `functionalities`; it replaces them with `antitheft-doors` and `dishwasher`.

#### Absent in Rental (present in For-Sale only)
- `switchOption` (no swap option for rentals)
- `functionalities[bathtub]`, `functionalities[shower-cabin]`, `functionalities[floor-heating]`, `functionalities[fireplace]`
- `otherAreas[barbecue]` (barbecue not present in rental's `otherAreas`)

---

## 11. Filter Reference: Cars & Vehicles

**URL:** `https://www.njuskalo.hr/auti?{params}` (or `rabljeni-auti`, `novi-auti`)  
**Total valid URL parameters:** 72  
**Captured data:** 14,689 listings across 588 pages (Zagreb)

#### Vehicle Selection
```
categoryId=13688                   # Osobni automobili (required for cars)
vehicleIds=10962                   # Single brand ID (Audi)
vehicleIds=10962,11005             # Multiple brands (Audi + BMW)
modelId=12345                      # Specific model ID
```

#### Condition — `condition` — type: `MultipleCheckboxValueOne`

| Parameter | Label |
|---|---|
| `condition[new]=1` | novo |
| `condition[test]=1` | testno |
| `condition[used]=1` | rabljeno |

#### Year of Manufacture — `yearManufactured` — type: `SelectRange`

Values: `1971` through `2026` (individual year strings).  
Usage: `yearManufactured[min]=2015&yearManufactured[max]=2022`

#### Price
```
price[min]=5000
price[max]=30000
onlyFullPrice=1                    # Only vehicles with final/firm price
```

#### Mileage — `mileage` — type: `IntegerRange`
```
mileage[min]=0
mileage[max]=100000               # km
```

#### Fuel Type — `fuelTypeId` — type: `Select`

| Value | Label |
|---|---|
| `600` | Benzin |
| `602` | Diesel |
| `604` | Hibrid |
| `231236` | Plug-in hibrid |
| `1226` | Električni |

#### Transmission — `transmissionTypeId` — type: `MultipleCheckbox`

| Parameter | Label |
|---|---|
| `transmissionTypeId[610]=1` | Mehanički mjenjač |
| `transmissionTypeId[611]=1` | Automatski |
| `transmissionTypeId[612]=1` | Automatski sekvencijski |
| `transmissionTypeId[613]=1` | Sekvencijski mjenjač |

#### Body Type — `bodyTypeId` — type: `Select`

| Value | Label |
|---|---|
| `21` | limuzina |
| `22` | karavan |
| `23` | monovolumen |
| `24` | coupe |
| `25` | kabriolet |
| `380` | terensko vozilo / SUV / pick up |
| `630` | kombibus |
| `631` | hatchback |

#### Engine

| Parameter | Type | Description |
|---|---|---|
| `motorPower[min]` / `[max]` | IntegerRange | kW |
| `motorSize[min]` / `[max]` | IntegerRange | ccm |
| `fuelConsumption[min]` / `[max]` | FloatRange | l/100km |
| `fuelHasLpg=0` or `=1` | Select | LPG: 0=No, 1=Yes |

#### Drive Type — `driveTypeId` — type: `Select`

| Value | Label |
|---|---|
| `35` | prednji (FWD) |
| `36` | stražnji (RWD) |
| `37` | 4 x 4 (AWD) |

#### Gearbox — `gearNumberId` — type: `Select`

| Value | Label |
|---|---|
| `620` | 4 stupnja |
| `621` | 5 stupnjeva |
| `622` | 6 stupnjeva |
| `7608` | 7 stupnjeva |

#### Air Conditioning — `airConditionTypeId` — type: `Select`

| Value | Label |
|---|---|
| `111` | obavezno ima |
| `85` | ručna |
| `86` | automatska |
| `87` | dvojna |

#### Number of Doors — `doorCountId` — type: `Select`

| Value | Label |
|---|---|
| `26` | 2 |
| `27` | 3 |
| `28` | 4 |
| `29` | 5 |
| `1165` | 6 |

#### Number of Seats — `seatCountId` — type: `Select`

| Value | Label |
|---|---|
| `2619` | 1 |
| `2620` | 2 |
| `2621` | 3 |
| `2622` | 4 |
| `2623` | 5 |
| `2624` | 6 |
| `2625` | 7 |
| `2626` | 8 |
| `2627` | 9 i više |

#### Registration Expiry — `registrationExpiryTs` — type: `Select`
Values are Unix timestamps corresponding to end-of-month dates:

| Value | Label |
|---|---|
| `1777586400` | 05/2026 |
| `1780264800` | 06/2026 |
| `1782856800` | 07/2026 |
| `1785535200` | 08/2026 |
| `1788213600` | 09/2026 |
| `1790805600` | 10/2026 |
| `1793487600` | 11/2026 |
| `1796079600` | 12/2026 |
| `1798758000` | 01/2027 |
| `1801436400` | 02/2027 |
| `1803855600` | 03/2027 |
| `1806530400` | 04/2027 |
| `1809122400` | 05/2027 |

#### Owner Count — `ownerCountId` — type: `Select`

| Value | Label |
|---|---|
| `110` | prvi (1st owner) |
| `111` | drugi (2nd owner) |
| `112` | treći i više (3rd+) |

#### Colour — `colorId` — type: `Select`

| Value | Label (HR) | Colour |
|---|---|---|
| `326` | bež | Beige |
| `33` | bijela | White |
| `34` | crna | Black |
| `31` | crvena | Red |
| `327` | bordo crvena | Bordeaux |
| `339` | ljubičasta | Purple |
| `334` | narančasta | Orange |
| `328` | plava | Blue |
| `329` | svijetlo plava | Light Blue |
| `330` | tamno plava | Dark Blue |
| `331` | siva | Grey |
| `332` | svijetlo siva | Light Grey |
| `333` | tamno siva | Dark Grey |
| `30` | smeđa | Brown |
| `336` | srebrna | Silver |
| `32` | zelena | Green |
| `337` | svijetlo zelena | Light Green |
| `338` | tamno zelena | Dark Green |
| `340` | zlatna | Gold |
| `335` | žuta | Yellow |

#### Additional Equipment — `additionalEquipment` — type: `MultipleCheckbox`

| Parameter | Label |
|---|---|
| `additionalEquipment[47]=1` | Ksenonska svjetla |
| `additionalEquipment[48]=1` | Bi-ksenonska svjetla |
| `additionalEquipment[2659]=1` | LED svjetla |
| `additionalEquipment[344]=1` | Kuka za vuču |
| `additionalEquipment[347]=1` | Krovni prozor |

#### Comfort Features — `comfortFeatures` — type: `MultipleCheckbox`

| Parameter | Label |
|---|---|
| `comfortFeatures[76]=1` | Parkirni senzori |
| `comfortFeatures[2668]=1` | Stražnja parkirna kamera |
| `comfortFeatures[77]=1` | Tempomat |
| `comfortFeatures[79]=1` | Kožna sjedala |
| `comfortFeatures[2669]=1` | Grijanje sjedala |
| `comfortFeatures[338063]=1` | Android Auto |
| `comfortFeatures[338064]=1` | Apple CarPlay |

#### Seller Type — `accountPurpose` — type: `Select`

| Value | Label |
|---|---|
| `business` | Poslovne osobe (dealer) |
| `private` | Privatne osobe (private seller) |

#### Payment Options — `paymentOptions` — type: `Select`

| Value | Label |
|---|---|
| `12` | gotovina (cash) |
| `14` | kredit (credit) |
| `15` | leasing |
| `92` | preuzimanje leasinga (lease takeover) |
| `341` | obročno bankovnim karticama (installments) |
| `342` | zamjena (trade) |
| `343` | staro za novo (trade-in) |

#### Warranty / Other
```
hasG1Warranty=1                    # Automobili s jamstvom — G1 klub
warranty=1                         # Vozila s jamstvom (any warranty)
videoCallOption=1                  # Razgledavanje putem video poziva
adsWithImages=1                    # Samo oglasi sa slikom
sort=cheap                         # Sort order
page=1                             # Page number
```

---

## 12. Filter Reference: Blago / General Marketplace

**URL:** `https://www.njuskalo.hr/blago?{params}`  
**Total valid URL parameters:** 20  
**Category ID:** 9798  
**Scale:** 187,971 listings across 7,519 pages

#### All Parameters

```
# Location
geo[locationIds]=1153
geo[lat]=45.815
geo[lng]=15.982
geo[radius]=20                     # default is 20km for Blago
geo[address]=Zagreb
# Legacy:
locationId=1153
locationIds=1153

# Price
price[min]=5
price[max]=500

# Condition — MultipleCheckboxValueOne
condition[new]=1                   # novo
condition[used]=1                  # rabljeno
condition[defective]=1             # oštećeno / neispravno

# Booleans
adsWithImages=1                    # Samo oglasi sa slikom
webshopLink=1                      # Samo oglasi webshopova
isOnlinePaymentEnabled=1           # Samo PayProtect oglasi (escrow)

# Standard
sort=new
page=1
```

---

## 13. Location / Geo System

### Location Hierarchy (3 levels)

```
Level 0: Županije (Counties)   — 21 areas, IDs 1150–1170
Level 1: Districts/Kvartovi    — e.g. 18 districts in Grad Zagreb
Level 2: Sub-districts         — neighbourhoods within districts
```

### Complete County List (Level 0)

| ID | Label | URL Slug |
|---|---|---|
| 1150 | Bjelovarsko-bilogorska | `bjelovarsko-bilogorska` |
| 1151 | Brodsko-posavska | `brodsko-posavska` |
| 1152 | Dubrovačko-neretvanska | `dubrovacko-neretvanska` |
| 1154 | Istarska | `istra` |
| 1155 | Karlovačka | `karlovacka` |
| 1156 | Koprivničko-križevačka | `koprivnicko-krizevacka` |
| 1157 | Krapinsko-zagorska | `krapinsko-zagorska` |
| 1158 | Ličko-senjska | `licko-senjska` |
| 1159 | Međimurska | `medimurje` |
| 1160 | Osječko-baranjska | `osjecko-baranjska` |
| 1161 | Požeško-slavonska | `pozesko-slavonska` |
| 1162 | Primorsko-goranska | `primorsko-goranska` |
| 1163 | Sisačko-moslavačka | `sisacko-moslavacka` |
| 1164 | Splitsko-dalmatinska | `splitsko-dalmatinska` |
| 1165 | Šibensko-kninska | `sibensko-kninska` |
| 1166 | Varaždinska | `varazdinska` |
| 1167 | Virovitičko-podravska | `viroviticko-podravska` |
| 1168 | Vukovarsko-srijemska | `vukovarsko-srijemska` |
| 1169 | Zadarska | `zadarska` |
| **1153** | **Grad Zagreb** | `zagreb` |
| **1170** | **Zagrebačka** | `zagrebacka` |

### Grad Zagreb Districts (Level 1, parentId=1153)

| ID | Label |
|---|---|
| 1247 | Brezovica |
| 1248 | Črnomerec |
| 1249 | Donja Dubrava |
| 1250 | Donji Grad |
| 1251 | Gornja Dubrava |
| 1252 | Gornji Grad - Medveščak |
| 1253 | Maksimir |
| 1254 | Novi Zagreb - istok |
| 1255 | Novi Zagreb - zapad |
| 1256 | Pešćenica - Žitnjak |
| 1257 | Podsljeme |
| 1258 | Podsused - Vrapče |
| 1259 | Sesvete |
| 1260 | Stenjevec |
| 1261 | Trešnjevka - jug |
| 1262 | Trešnjevka - sjever |
| 1263 | Trnje |
| 1264 | (additional district) |

### Sample Sub-Districts (Level 2)

**Črnomerec (1248):** Bijenik (2596), Črnomerec (2597), Fraterščica (2598), Gornje Selo (2599), Gornje Vrapče (2600), Gornji Lukšić (2601), Jelenovac (2602), Krvarić (2603), Kustošija (2604), Lukšić (2605), Mikulići (2606), Sveti Duh (2607), Šestinski dol (2608), Vrhovec (2609), Završje (2610)

**Donja Dubrava (1249):** Čulinec (2611), Donja Dubrava (2612), Dubrava (2613), Krčevine (2614), Resnički gaj (2615), Retkovec (2616), Trnava (2617)

### Two Geo Search Modes

**1. ID-based (recommended):**
```
geo[locationIds]=1153                    # All of Grad Zagreb (county level)
geo[locationIds]=1247,1248,1249          # Specific districts only
geo[locationIds]=2597,2598               # Specific neighbourhoods
```

**2. Radius-based:**
```
geo[lat]=45.8150&geo[lng]=15.9819&geo[radius]=20&geo[address]=Zagreb
```

You can mix: `geo[locationIds]=1153` selects the whole county; individual district IDs allow district-level filtering. The `/papi/pages/browse-listings/locations-hierarchy` endpoint is the authoritative source for all IDs.

---

## 14. Category Tree

### Top-Level Categories (Level 0 from `/papi/…/category-hierarchy`)

| ID | Label | Slug |
|---|---|---|
| 2 | Auto Moto | (use `/auto-moto`) |
| 1 | Nekretnine | (use `/nekretnine`) |
| 12004 | Nautika | `nautika` |
| 16163 | Turistički smještaj | `turisticki-smjestaj` |
| 9726 | Sve za dom | `sve-za-dom` |
| 12599 | Hrana i piće | `hrana-pice` |
| 9788 | Kućni ljubimci | `kucni-ljubimci` |
| 3 | Informatička oprema | `informatika` |
| 9643 | Mobiteli | `mobiteli` |
| 9654 | Audio, video i foto | `audio-video-foto` |
| 9696 | Glazbala | `glazbala` |
| 9749 | Literatura | `knjige` |
| 9737 | Sportska oprema | `sportska-oprema` |
| 9798 | Pronađeno blago | `blago` |
| 9807 | Dječji svijet | `djecji-svijet` |
| 9761 | Strojevi i alati | `strojevi-alati` |
| 12378 | Od glave do pete | (no slug) |
| 12551 | Poslovi | `posao` |
| 12111 | Usluge | `usluge` |
| 9823 | Ostalo | `ostalo` |

### Auto Moto Sub-Categories (Level 1, parentIds=2)

| ID | Label | Slug |
|---|---|---|
| 13688 | Osobni automobili | `auti` |
| 1149 | Gospodarska vozila | `gospodarska-vozila` |
| 9 | Oldtimeri | `oldtimeri` |
| 1148 | Motocikli / Motori | `motori` |
| 12140 | Kamperi i kamp prikolice | `kamperi-kamp-prikolice` |
| 9838 | Rezervni dijelovi i oprema | `rezervni-dijelovi` |
| 13506 | Karambolirani automobili | `karambolirani-auti` |

### Car Condition Sub-Categories (Level 2, parentIds=13688)

| ID | Label | Slug |
|---|---|---|
| 7 | Rabljeni automobili | `rabljeni-auti` |
| 13689 | Novi automobili | `novi-auti` |

### Vehicle Brands (Level 0 from `/papi/…/vehicles-hierarchy`) — 108 total

Selected brands with IDs:

| ID | Brand | Slug |
|---|---|---|
| 15449 | Abarth | `abarth` |
| 10923 | Alfa Romeo | `alfa-romeo` |
| 10962 | Audi | `audi` |
| 16010 | BYD | `byd` |
| 11005 | BMW | `bmw` |
| 11079 | Citroën | `citroen` |
| 15419 | Cupra | `cupra` |
| 11117 | Dacia | `dacia` |
| 11135 | Fiat | `fiat` |
| 11147 | Ford | `ford` |
| 11180 | Honda | `honda` |
| 11189 | Hyundai | `hyundai` |
| 11210 | Jeep | `jeep` |
| 11214 | Kia | `kia` |
| 11234 | Land Rover | `land-rover` |
| 11246 | Mazda | `mazda` |
| 11262 | Mercedes-Benz | `mercedes-benz` |
| 11288 | Nissan | `nissan` |
| 11296 | Opel | `opel` |
| 11314 | Peugeot | `peugeot` |
| 11321 | Porsche | `porsche` |
| 11335 | Renault | `renault` |
| 11342 | Seat | `seat` |
| 11349 | Škoda | `skoda` |
| 11373 | Toyota | `toyota` |
| 11386 | Volkswagen | `volkswagen` |
| 11392 | Volvo | `volvo` |

---

## 15. Listing Data Schema

### Full Listing Object Schema (regularListings / promotedListings)

All fields present on every standard listing across categories:

```python
{
    # ── Identity ────────────────────────────────────────────────────────
    "id":           50659088,                   # int — unique listing ID
    "title":        "Zagreb, Črnomerec...",     # str — full display title
    "titleSlug":    "zagreb-crnomerec-...",     # str — URL slug (without -oglas-{id})
    "categorySlug": "nekretnine",               # str — category for URL construction

    # ── Timestamps ──────────────────────────────────────────────────────
    "createdAt":          "2026-05-28T11:48:28.000Z",  # str — ISO 8601
    "createdAtFormatted": "28.05.2026.",               # str — HR display format

    # ── Price ───────────────────────────────────────────────────────────
    "priceFormatted":   "315.000 €",    # str — formatted price
    "isPriceOnRequest": False,           # bool — "Cijena na upit"
    "hidePrice":        False,           # bool — seller chose to hide price

    # ── Media ───────────────────────────────────────────────────────────
    "image": "https://www.njuskalo.hr/image-200x150/nekretnine/...-slika-278369492.jpg",

    # ── Location ────────────────────────────────────────────────────────
    "location": "Črnomerec, Črnomerec",  # str — "District, Neighbourhood"

    # ── Key Facts (shown as bullets on listing card) ─────────────────────
    "abstracts": [
        {"caption": None,       "value": "Stan u stambenoj zgradi, 12. kat"},
        {"caption": None,       "value": "Stambena površina: 70 m2"},
        {"caption": "Lokacija", "value": "Črnomerec, Črnomerec"}
    ],
    # For cars: [{"caption": None, "value": "Rabljeno vozilo, 245000 km"},
    #            {"caption": None, "value": "Godište automobila: 2017."},
    #            {"caption": None, "value": "Benzin, 2.0, 147 kW / 200 KS"}]
    # For blago: [{"caption": "Lokacija", "value": "Varaždin, Centar"}]

    # ── Condition (goods/vehicles) ───────────────────────────────────────
    "condition": "",           # str — "rabljeno", "novo", "oštećeno", or ""
    "itemSize":  None,         # str or null

    # ── Feature flags ────────────────────────────────────────────────────
    "isPromoted":              True,   # bool — paid VauVau promotion
    "isNewCar":                False,  # bool — new car listing
    "hasCarWarranty":          False,  # bool — dealer warranty
    "hasG1Warranty":           False,  # bool — G1 club warranty
    "hasVirtualTour":          False,  # bool — 360° virtual tour
    "isOnlinePaymentEnabled":  False,  # bool — PayProtect escrow available
    "hasVideo":                False,  # bool — video attached
    "hasMap":                  True,   # bool — GPS location set
    "hasGroundPlan":           False,  # bool — floor plan attached (real estate)
    "hasHKSCertificate":       False,  # bool — HKS vehicle certificate
    "isLuxuryRealEstate":      False,  # bool — luxury category listing
    "isOwnerResidentialSeller": False, # bool — private/owner listing (not agency)

    # ── User interaction (always False without login) ────────────────────
    "isSaveAvailable":  True,   # bool — can be saved to favourites
    "isCompareAvailable": False, # bool — can be added to compare (True for cars)
    "isSaved":    False,        # bool — saved in current session
    "isCompared": False,        # bool — in compare basket (cars only field)
}
```

### Homepage / Marketplace Reduced Schema

Pages that show listing cards without full search context:

```python
{
    "id":               44376929,
    "title":            "Auto Revuenon 55mm f/1.7 m42",
    "categorySlug":     "objektivi",
    "titleSlug":        "pentacon-auto-multi-coating-50mm-f-1.8-m42",
    "priceFormatted":   "45,00 €",
    "image":            "https://www.njuskalo.hr/image-360x360c/objektivi/...",
    "isPriceOnRequest": False,
    "hidePrice":        False,
    "isSaved":          False,
    # NOTE: no abstracts, createdAt, location, or feature flags
}
```

### `abstracts` Field Parsing

The `abstracts` array holds the bullet-point facts shown on each card. Rules:
- When `caption` is `None`: the `value` is shown alone (e.g. "Stan u stambenoj zgradi, 12. kat")
- When `caption` is a string: shown as `{caption}: {value}` (e.g. "Lokacija: Črnomerec, Črnomerec")
- Number of abstracts varies: real estate typically has 3, cars typically have 3–4, Blago often has just 1

### Price Parsing (Croatian Format)

```python
import re

def parse_price(price_str: str) -> float | None:
    """
    Parse Croatian-format price strings to float EUR.

    Format rules:
    - Period (.) is the thousands separator: "315.000" → 315000
    - Comma (,) is the decimal separator:    "45,00"   → 45.0
    - Currency symbol € is stripped

    Examples:
        "315.000 €"    → 315000.0
        "1.800 €"      → 1800.0
        "45,00 €"      → 45.0
        "1.800,00 €"   → 1800.0
        "40 €"         → 40.0
        "1 €"          → 1.0
        "315.000,00 €" → 315000.0  (homepage format, both separators)
    """
    if not price_str:
        return None
    digits = re.sub(r'[^\d,.]', '', price_str.strip())
    if not digits:
        return None
    if ',' in digits and '.' in digits:
        # Both separators: "1.800,00" → remove periods, replace comma
        digits = digits.replace('.', '').replace(',', '.')
    elif ',' in digits:
        # Only comma: decimal separator "45,00" → replace comma
        digits = digits.replace(',', '.')
    else:
        # Only periods (if any): thousands separator "315.000" → remove
        digits = digits.replace('.', '')
    try:
        return float(digits)
    except ValueError:
        return None
```

> **Note:** The homepage state uses `"315.000,00 €"` (with both separators) while the listing page state uses `"315.000 €"`. The parser above handles both.

---

## 16. Image URL System

### URL Pattern

```
https://www.njuskalo.hr/image-{SIZE}/{categorySlug}/{slug}-slika-{imageId}.{ext}
```

Components:
- `{SIZE}`: size descriptor (see table below)
- `{categorySlug}`: same as listing's `categorySlug` field
- `{slug}`: title slug of the listing (same as `titleSlug`)
- `{imageId}`: numeric image ID (different from listing ID)
- `{ext}`: always `.jpg`

### Size Descriptors

| Size String | Dimensions | Aspect | Typical Use |
|---|---|---|---|
| `image-200x150` | 200×150px | 4:3 | Listing card thumbnail (in `__INITIAL_STATE__`) |
| `image-360x360c` | 360×360px | 1:1 (cropped) | Homepage / Marketplace cards |
| `image-w1000` | ~1000px wide | original ratio | Large/detail view |
| `logo-140x140` | 140×140px | 1:1 | Agency logos in FeaturedStore |

### Transforming Image Sizes

The size segment is always the first path segment after the domain:

```python
import re

def transform_image_size(image_url: str, new_size: str = 'image-w1000') -> str:
    """
    Transform a Njuškalo image URL to a different size.

    Args:
        image_url: e.g. "https://www.njuskalo.hr/image-200x150/nekretnine/...-slika-278369492.jpg"
        new_size:  e.g. "image-w1000", "image-360x360c", "image-200x150"

    Returns:
        Transformed URL with new size segment
    """
    return re.sub(
        r'(https://www\.njuskalo\.hr/)image-[^/]+/',
        rf'\g<1>{new_size}/',
        image_url
    )

# Examples:
thumbnail = "https://www.njuskalo.hr/image-200x150/nekretnine/zagreb-crnomerec-...-slika-278369492.jpg"
large     = transform_image_size(thumbnail, 'image-w1000')
square    = transform_image_size(thumbnail, 'image-360x360c')
```

---

## 17. Pagination

### Reading from `__INITIAL_STATE__`

```python
state    = extract_initial_state(html)
page_data = state['browseListingsStore']['pageData']

total    = page_data['listingsCount']    # int — total matching listings
pages    = page_data['totalPageCount']   # int — total pages
current  = page_data['fields']['page']   # int — current page number (1-based)
per_page = 25                            # always 25
```

### Building Page URLs

```python
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

def set_page(url: str, page: int) -> str:
    """Return URL with ?page=N set (or removed for page 1)."""
    parsed  = urlparse(url)
    params  = parse_qs(parsed.query, keep_blank_values=True)
    if page > 1:
        params['page'] = [str(page)]
    elif 'page' in params:
        del params['page']
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))
```

### Category Scale Reference

| Category / Filter | Listings | Pages |
|---|---|---|
| Apartments for sale (Zagreb, filtered) | 174 | 7 |
| Apartments for rent (Zagreb + Zagrebačka) | 5,902 | 237 |
| Cars for sale (Zagreb) | 14,689 | 588 |
| Pronađeno blago (all Croatia) | 187,971 | 7,519 |
| Auto Moto Nautika (all Croatia) | 1,209,378 | ~48,375 |
| Nekretnine (all Croatia) | 183,722 | ~7,349 |

---

## 18. Homepage & Marketplace State Structures

### Homepage (`/`)

State key: `homePage`

```python
state = extract_initial_state(html)
hp = state['homePage']['pageData']

# Category listing counts
for cat in hp['categories']:
    print(cat['id'], cat['title'], cat['entitiesCountFormatted'], cat['url'])
# → "2  Auto Moto Nautika  1.209.378  /auto-moto"
# → "1  Nekretnine  183.722  /nekretnine"

# Featured super-promoted listings
for listing in hp['superVauListings']:
    print(listing['id'], listing['title'], listing['url'])

# Personalised recommendations (empty when not logged in)
for listing in hp['recommendedListings']:
    print(listing['id'], listing['title'], listing['priceFormatted'])
    # Schema: id, title, categorySlug, titleSlug, priceFormatted, image,
    #         isPriceOnRequest, hidePrice

# Trending searches
for item in hp['popularContent']:
    print(item['title'], item['url'])

# Popular brands
for brand in hp['popularBrands']['brands']:
    print(brand['id'], brand['title'], brand['url'])

# Catalogs / leaflets
for cat in hp['catalogs']:
    print(cat['title'], cat['url'])
```

### Marketplace Page (`/marketplace`)

State key: `homeMarketplacePage`

```python
state = extract_initial_state(html)
mp = state['homeMarketplacePage']['pageData']

# Keys: meta, categoryMeta, categories, superVauListings,
#       horizontalSuperVauListings, recommendedListings,
#       currentlyActualContent, offeristaWidget, trends,
#       popularContent, popularBrands, catalogs, bannerZones

for listing in mp['recommendedListings']:
    # Schema: id, title, categorySlug, titleSlug, priceFormatted,
    #         image, isPriceOnRequest, hidePrice, isSaved
    print(listing['id'], listing['priceFormatted'], listing['title'])
```

---

## 19. Scraping Strategy & Complete Code Templates

### Method Comparison

| Method | Pros | Cons | Best for |
|---|---|---|---|
| `__INITIAL_STATE__` JSON | Clean structured data, no HTML parsing, fast | State size (50–200KB/page) | All listing scraping |
| BeautifulSoup HTML | Fallback, schema-change detection | HTML noise from Vue comments | Cross-validation |
| `/papi/` API endpoints | Clean JSON for reference data | Only needed for enumerating locations/categories | One-time setup |

### Complete All-in-One Scraper

```python
import re
import json
import time
import requests
from typing import Generator

BASE_URL = "https://www.njuskalo.hr"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "hr-HR,hr;q=0.9,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
}


# ── Core extraction ───────────────────────────────────────────────────────────

def extract_initial_state(html: str) -> dict:
    match = re.search(
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>',
        html, re.DOTALL
    )
    if not match:
        raise ValueError("__INITIAL_STATE__ not found in page")
    return json.loads(match.group(1))


def get_page_data(url: str, session: requests.Session) -> dict:
    resp = fetch_with_retry(url, session)
    state = extract_initial_state(resp.text)
    return state['browseListingsStore']['pageData']


def fetch_with_retry(
    url: str,
    session: requests.Session,
    max_retries: int = 3,
    base_delay: float = 2.0
) -> requests.Response:
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 429:
                wait = base_delay * (2 ** attempt)
                print(f"  Rate limited, waiting {wait:.0f}s…")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait = base_delay * (2 ** attempt)
            print(f"  Request error ({e}), retry in {wait:.0f}s…")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {max_retries} retries: {url}")


# ── Listing collection ────────────────────────────────────────────────────────

def get_all_listings_from_page(page_data: dict, include_promoted: bool = True) -> list:
    """Collect all unique listings from a single page's pageData."""
    buckets = ['regularListings', 'latestListings']
    if include_promoted:
        buckets = ['promotedListings', 'userPromotedListings'] + buckets
    seen = set()
    result = []
    for bucket in buckets:
        for item in page_data.get(bucket, []):
            if item['id'] not in seen:
                seen.add(item['id'])
                item['_bucket'] = bucket
                result.append(item)
    return result


def iter_all_listings(
    base_url: str,
    delay: float = 1.5,
    include_promoted: bool = True,
    max_pages: int | None = None,
) -> Generator[dict, None, None]:
    """
    Yield every listing across all pages for a given search URL.

    Args:
        base_url:        Listing search URL (with filters, without &page=N)
        delay:           Seconds to wait between page requests
        include_promoted: Whether to include VauVau promoted listings
        max_pages:       Stop after this many pages (None = all pages)
    """
    session = requests.Session()
    seen_ids: set = set()

    page_data = get_page_data(base_url, session)
    total_pages = page_data['totalPageCount']
    total_count = page_data['listingsCount']

    if max_pages:
        total_pages = min(total_pages, max_pages)

    print(f"Total: {total_count} listings, {total_pages} pages "
          f"({'capped' if max_pages else 'all'})")

    for page in range(1, total_pages + 1):
        if page > 1:
            time.sleep(delay)
            url = set_page(base_url, page)
            try:
                page_data = get_page_data(url, session)
            except Exception as e:
                print(f"  Page {page} failed: {e}, skipping")
                continue

        listings = get_all_listings_from_page(page_data, include_promoted)
        new_count = 0
        for listing in listings:
            if listing['id'] not in seen_ids:
                seen_ids.add(listing['id'])
                listing['_page'] = page
                yield listing
                new_count += 1

        print(f"  Page {page}/{total_pages}: {new_count} new listings "
              f"(total unique: {len(seen_ids)})")


def set_page(url: str, page: int) -> str:
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if page > 1:
        params['page'] = [str(page)]
    elif 'page' in params:
        del params['page']
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


# ── Pre-built search URLs ─────────────────────────────────────────────────────

SEARCHES = {
    # Apartments for sale, Zagreb, 4+ rooms, max 360k, with lift, with images
    'apartments_for_sale_zagreb': (
        "https://www.njuskalo.hr/prodaja-stanova"
        "?geo[locationIds]=1247,1248,1249,1250,1252,1253,1254,1255,"
        "1256,1257,1258,1259,1260,1261,1262,1263,1264,1251"
        "&price[max]=360000"
        "&numberOfRooms[min]=four-rooms"
        "&buildingInfo[lift]=1"
        "&adsWithImages=1"
        "&sort=new"
    ),

    # Apartments for rent, all Zagreb + Zagrebačka, oldest first
    'apartments_for_rent_zagreb': (
        "https://www.njuskalo.hr/iznajmljivanje-stanova"
        "?geo[locationIds]=1153,1170"
        "&sort=old"
    ),

    # Used cars in Zagreb, cheapest first
    'used_cars_zagreb': (
        "https://www.njuskalo.hr/auti"
        "?geo[locationIds]=1153"
        "&condition[used]=1"
        "&adsWithImages=1"
        "&sort=cheap"
    ),

    # All Blago marketplace
    'blago_all': "https://www.njuskalo.hr/blago?sort=new",
}


# ── Example usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import csv

    url = SEARCHES['apartments_for_sale_zagreb']
    rows = []

    for listing in iter_all_listings(url, delay=1.5, include_promoted=False):
        rows.append({
            'id':               listing['id'],
            'title':            listing['title'],
            'price':            listing['priceFormatted'],
            'location':         listing.get('location', ''),
            'created_at':       listing.get('createdAt', ''),
            'url':              f"https://www.njuskalo.hr/{listing['categorySlug']}/{listing['titleSlug']}-oglas-{listing['id']}",
            'has_map':          listing.get('hasMap', False),
            'is_promoted':      listing.get('isPromoted', False),
            'bucket':           listing.get('_bucket', ''),
            'page':             listing.get('_page', 1),
        })

    with open('listings.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} listings to listings.csv")
```

### Key Scraping Considerations

**Stability of `sort=old` for large scrapes:**  
When paginating through thousands of pages, new listings appear while you scrape. Using `sort=old` (oldest first) keeps early pages stable since new listings are appended to the end. Always deduplicate by `id`.

**Deduplication:**  
A listing may appear in multiple buckets (e.g., in both `promotedListings` and `regularListings`). Always deduplicate by `id` across a full scrape.

**`data-faux-anchor` links:**  
Links in Vue-rendered HTML often have both `href` (for plain HTTP) and `data-href` (for Vue router). Use `href` — it is always present and works for direct HTTP requests.

**Vue comment nodes (`<!--[-->`, `<!--]-->`, `<!---->`):**  
The rendered HTML contains many Vue SSR marker comments. Strip them with `re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)` before parsing abstracts or description text.

**Schema validation guard:**
```python
REQUIRED_LISTING_KEYS = {'id', 'title', 'priceFormatted', 'categorySlug', 'titleSlug'}

def validate_listing_schema(page_data: dict) -> None:
    listings = page_data.get('regularListings', [])
    if listings:
        missing = REQUIRED_LISTING_KEYS - set(listings[0].keys())
        if missing:
            raise ValueError(f"Listing schema changed! Missing: {missing}")
```

---

## 20. Complete URL Parameter Quick Reference

### Real Estate For Sale — 76 Parameters
```
# Category
categoryIds, categoryId

# Location (prefer geo[] form)
geo[lat], geo[lng], geo[radius], geo[locationIds], geo[address], geo
locationId, locationIds  ← legacy aliases

# Price
price[min], price[max], price

# Area
livingArea[min], livingArea[max], livingArea

# Rooms
numberOfRooms[min], numberOfRooms[max], numberOfRooms
  values: studio-apartment | one-room | two-rooms | three-rooms | four-rooms | five-rooms

# Building type
flatBuildingType        values: flat-in-house | flat-in-residential-building

# Floor count (of apartment)
flatFloorCount          values: single-floor | two-floor | multi-floor

# Balcony
balconyInfo             values: allthree | balcony | loggie | terace | nothing

# Building features (multi, use [value]=1)
buildingInfo[new-building], buildingInfo[lift], buildingInfo[invalid-can], buildingInfo[city-gas]
buildingInfo ← (legacy single)

# Furnishing (multi, use [value]=1)
furnishLevelAndCondition[furnished], furnishLevelAndCondition[partially-furnished]
furnishLevelAndCondition[unfurnished], furnishLevelAndCondition[unfinished-for-renovation]
furnishLevelAndCondition ← (legacy single)

# Heating
heatingSource           values: see §9

# Energy certificate
subjectEnergyCertificate[min], subjectEnergyCertificate[max], subjectEnergyCertificate
  values: a-plus | a | b | c | d | e | f | g

# Floor position
buildingFloorPosition[min], buildingFloorPosition[max], buildingFloorPosition
  values: basement | ground-floor | high-ground | 1-25 | attic | high-attic | penthouse

# Building total floors
buildingFloorCount[min], buildingFloorCount[max], buildingFloorCount
  values: ground-floor | high-ground | 1-25

# Other areas (multi, use [value]=1)
otherAreas[garden], otherAreas[basement], otherAreas[supa], otherAreas[barbecue]
otherAreas ← (legacy single)

# Functionalities (multi, use [value]=1)
functionalities[bathtub], functionalities[shower-cabin]
functionalities[floor-heating], functionalities[fireplace]
functionalities ← (legacy single)

# Year
yearOfConstruction[min], yearOfConstruction[max], yearOfConstruction
yearOfRenovation[min], yearOfRenovation[max], yearOfRenovation

# Parking
numberOfParkingSpots[min], numberOfParkingSpots[max], numberOfParkingSpots
  values: none | 1 | 2 | 3 | 4 | 5 | 6 | 7 (=7+)
parkingSpotType[parking-garage], parkingSpotType[garage-spot]
parkingSpotType[parking-outdoor-covered], parkingSpotType[parking-garage-outdoor-notcovered]
parkingSpotType[parking-public-free], parkingSpotType[parking-public-not-free]
parkingSpotType ← (legacy single)

# Misc
switchOption            values: yes-flat-switch | no-flat-switch
videoCallOption         =1
virtualTour             =1
adsWithImages           =1
includeOtherCategories  =1
product                 (internal)
sort                    values: new | old | cheap | expensive | distance
page
```

### Real Estate Rental — 75 Parameters
All of above (except `switchOption`, `otherAreas[barbecue]`) plus:
```
petsAllowed             =1
airConditioning         =1
availableFromDate       =1
yearlyAvailability      values: all-year | out-off-tourist-season | during-tourist-season

# Different functionalities set:
functionalities[antitheft-doors], functionalities[dishwasher]
```

### Cars — 72 Parameters
```
# Vehicle
categoryId              (13688 for cars)
vehicleIds              brand/model IDs, comma-separated
modelId                 specific model ID

# Condition
condition[new], condition[test], condition[used]
condition ← (legacy single)

# Location
geo[lat], geo[lng], geo[radius], geo[locationIds], geo[autoComplete], geo
locationId, locationIds

# Price
price[min], price[max], price
onlyFullPrice           =1

# Year
yearManufactured[min], yearManufactured[max], yearManufactured
  values: 1971–2026 (year strings)

# Mileage
mileage[min], mileage[max], mileage

# Engine
fuelTypeId              values: 600 | 602 | 604 | 231236 | 1226
motorSize[min], motorSize[max], motorSize        (ccm)
motorPower[min], motorPower[max], motorPower     (kW)
fuelConsumption[min], fuelConsumption[max], fuelConsumption (l/100km)
fuelHasLpg              values: 0 | 1
driveTypeId             values: 35 | 36 | 37

# Gearbox/transmission
transmissionTypeId[610], transmissionTypeId[611]
transmissionTypeId[612], transmissionTypeId[613]
transmissionTypeId ← (legacy single)
gearNumberId            values: 620 | 621 | 622 | 7608

# Body
bodyTypeId              values: 21 | 22 | 23 | 24 | 25 | 380 | 630 | 631
doorCountId             values: 26 | 27 | 28 | 29 | 1165
seatCountId             values: 2619–2627
colorId                 values: 30–340 (20 colours, see §11)

# A/C
airConditionTypeId      values: 111 | 85 | 86 | 87

# Registration
registrationExpiryTs    values: unix timestamps (see §11)

# Owner
ownerCountId            values: 110 | 111 | 112

# Equipment (multi)
additionalEquipment[47], additionalEquipment[48], additionalEquipment[2659]
additionalEquipment[344], additionalEquipment[347]
additionalEquipment ← (legacy single)

# Comfort (multi)
comfortFeatures[76], comfortFeatures[2668], comfortFeatures[77]
comfortFeatures[79], comfortFeatures[2669]
comfortFeatures[338063], comfortFeatures[338064]
comfortFeatures ← (legacy single)

# Warranty
hasG1Warranty           =1
warranty                =1

# Seller
accountPurpose          values: business | private
paymentOptions          values: 12 | 14 | 15 | 92 | 341 | 342 | 343

# Misc
videoCallOption         =1
adsWithImages           =1
sort                    values: new | old | cheap | expensive | distance
page
```

### Blago — 20 Parameters
```
geo[lat], geo[lng], geo[radius], geo[locationIds], geo[autoComplete], geo
locationId, locationIds
price[min], price[max], price
condition[new], condition[used], condition[defective], condition
adsWithImages           =1
webshopLink             =1
isOnlinePaymentEnabled  =1
sort                    values: new | old | cheap | expensive
page
```

---

*End of reference. Generated from network captures, `__INITIAL_STATE__` JSON analysis, and full HTML inspection of njuskalo.hr on 2026-05-28. File covers 19 captured network calls across 5 page types: apartments for sale, apartments for rent, cars for sale, marketplace, blago.*

---

## 21. Additional Findings from Homepage, Marketplace & Blago HTML

### 21.1 Application Metadata

These fields are in `main` on every page and are useful for cache-busting detection:

```python
state['main']['applicationVersion']
# → "32df26981387f6fa4a9e00f31c7d8bc4a90b5801"  (git commit hash)
# If this changes between scrapes, the site was deployed — re-check schema

state['main']['serverTime']
# → 1779971553937  (Unix timestamp in milliseconds)
# Use to detect clock drift or stale cached responses
```

### 21.2 Keyword Search — `/search/` Endpoint

The main search bar posts to:

```
GET /search/?keywords={term}
```

HTML form:
```html
<form id="search-main" action="/search/" method="get" role="search" class="SearchBox SearchBox--alpha">
  <input id="keywords" name="keywords" type="search" autocomplete="off">
  <button id="submitButton" type="submit">Pretraži</button>
</form>
```

Search results pages at `/search/?keywords=...` use the same `__INITIAL_STATE__` / `browseListingsStore` pattern as category pages. The keyword filter is a free-text parameter on top of all other filters, e.g.:

```
GET /search/?keywords=iphone&condition[used]=1&sort=cheap
GET /search/?keywords=payprotect&isOnlinePaymentEnabled=1&sort=new
```

There is also a `{search_term}` template URL observed in the HTML:
```
/search/?keywords={search_term}
```

### 21.3 Search by Image (Feature Flag Enabled)

The feature flags confirm image search is live:
```python
featureFlags['isSearchByImageEnabled']       # True
featureFlags['isSearchByImageWebPromoEnabled'] # True
```

No endpoint URL was visible in the SSR HTML (it's loaded dynamically by Vue). The feature likely posts to a `/papi/` or `/search/` endpoint with a multipart image upload. Monitor XHR traffic on the `/search/` page for the actual endpoint.

### 21.4 Autocomplete / Autosuggest

The search input uses an `Autosuggest` Vue component with `role="combobox"`. The autocomplete endpoint is not visible in SSR HTML — it fires via XHR as the user types. Likely endpoint pattern (not confirmed from captures): `/papi/search/suggest?q={term}`.

### 21.5 Feature Flags — Complete List

All feature flags from `main.featureFlags` (consistent across all pages):

| Flag | Value | Notes |
|---|---|---|
| `isEscrowActive` | `true` | PayProtect escrow is live |
| `isSearchByImageEnabled` | `true` | Image search active |
| `isSearchByImageWebPromoEnabled` | `true` | Image search promoted |
| `isRecommenderForAutoMotoFeatureEnabled` | `true` | Personalised car recommendations |
| `isRecommenderForHomepageFeatureEnabled` | `true` | Personalised homepage recs |
| `isRecommenderForMarketplaceFeatureEnabled` | `true` | Personalised marketplace recs |
| `isRecommenderForRealEstateFeatureEnabled` | `true` | Personalised real estate recs |
| `isReadRecentUserQueryFeatureEnabled` | `true` | Recent search history stored |
| `isCategoryRecommenderFeatureEnabled` | `true` | Category recommendations |
| `isCategorySuggestFeatureEnabled` | `true` | Category suggestions in search |
| `isAdaptiveSearchFiltersFeatureEnabled` | `true` | Filters adapt to search context |
| `isTagWidgetFeatureEnabled` | `true` | Tag-based search widgets |
| `isTrendingCategoriesRecommenderFeatureEnabled` | `true` | Trending category widgets |
| `isPopularCarModelsFeatureEnabled` | `true` | Popular car model shortcuts |
| `isNjupopCataloguesFeatureEnabled` | `true` | Katalozi (retail catalogues) active |
| `liveChatEnabled` | `true` | Live chat support active |
| `hotJarEnabled` | `true` | HotJar user session recording |
| `microsoftClarityEnabled` | `true` | Microsoft Clarity analytics |
| `googleTagManagerEnabled` | `true` | GTM active |
| `isRecaptchaFeatureEnabled` | `true` | reCAPTCHA on forms |
| `shieldSquareEnabled` | `true` | Bot protection active |
| `defractalEnabled` | `true` | Defractal analytics |
| `dotmetricsEnabled` | `true` | Dotmetrics analytics |
| `isXitiEnabled` | `true` | Xiti/AT Internet analytics |
| `midasEnabled` | `true` | Midas ad system |
| `isAdsenseFeatureEnabled` | `true` | Google AdSense active |
| `isDemandManagerFeatureEnabled` | `true` | Header bidding/demand manager |
| `isBannerLazyLoadFeatureEnabled` | `true` | Banners lazy-loaded |
| `areNewDsaCategoriesEnabled` | `true` | EU Digital Services Act categories |
| `isDidomiFeatureEnabled` | `true` | Didomi consent management |
| `isMobileManifestAndroidActive` | `true` | Android PWA manifest |
| `isMobileManifestIOSActive` | `true` | iOS PWA manifest |
| `isCustomerSuccessToolFeatureEnabled` | `true` | CRM/customer success tool |

**Flags that are `false` (features OFF):**

| Flag | Notes |
|---|---|
| `isABTestForHomepageEnabled` | No A/B test running on homepage |
| `isAdMetricsFeatureEnabled` | Ad metrics not shown |
| `isAnalyticsFeatureEnabled` | Internal analytics disabled |
| `isPlatformStatisticsFeatureEnabled` | Platform stats off |
| `isOfferistaWidgetEnabled` | Offerista widget inactive |
| `isPushupSchedulingFeatureEnabled` | Pushup scheduling off |
| `isQuickSearchWidgetAutoMotoEnabled` | Quick search widget off |
| `isQuickSearchWidgetRealestateEnabled` | Quick search widget off |
| `isShowNotificationEnabled` | Push notifications off |
| `isCookieSwitchToSearchEnabled` | Cookie-based search switch off |
| `vavenEnabled` | Vaven (?) off |

> **Scraping implication:** `shieldSquareEnabled: true` means ShieldSquare bot protection is active. `isRecaptchaFeatureEnabled: true` means reCAPTCHA is on forms (but not on listing pages). Rotate User-Agents and respect rate limits.

### 21.6 Homepage-Specific State (`homePage.pageData`)

New keys found in the real homepage HTML vs the previously analysed state JSON:

#### `headlineSlides` — Hero carousel banners
```python
for slide in hp['headlineSlides']:
    # Keys: id, url, image, imageSmall, imageDescription, openInNewTab
    print(slide['url'])      # destination URL (often blog.njuskalo.hr or internal)
    print(slide['image'])    # full-width image: /slika-original-{id}.jpg
    print(slide['imageSmall'])  # mobile version: /slika-original-{id}.jpg
```

Image URLs use the `slika-original-{imageId}.jpg` pattern (no size descriptor):
```
https://www.njuskalo.hr/slika-original-278154577.jpg
```

#### `recentUserQueries` — Session-based recent searches
When a user is logged in or has session cookies, this array contains their recent searches. Each entry has a full reconstructible URL:

```python
{
    "id": "01KSQ94FF526QEYA6EC35X3E5G",  # ULID
    "type": "categories",                 # always "categories" for search
    "title": "Prodaja stanova",           # human-readable label
    "url": "/prodaja-stanova?geo%5BlocationIds%5D=...",  # URL-encoded full URL
    "parameters": [                       # human-readable active filter values
        "Brezovica", "Črnomerec", "Donja Dubrava", ...  # location names
    ],
    "listings": [...]                     # preview listings for this saved search
}
```

> Useful for monitoring: if you're scraping with an account, recent queries tell you what the session knows about itself.

#### `recommendedCategories` — Personalised category recommendations
Each entry is a category with 10 pre-loaded listings:

```python
{
    "id": "44a8c727210a6264356f559679efd72a",
    "title": "BMW serija 5",
    "url": "/rabljeni-auti/bmw-serija-5",
    "categories": ["Rabljeni automobili"],
    "listings": [
        {"id": 49550805, "title": "...", "priceFormatted": "19.490,00 €",
         "image": "...", "categorySlug": "auti", "titleSlug": "..."},
        ...  # 10 listings per recommended category
    ]
}
```

#### `superVauListings` on Homepage — Extended Schema
The homepage superVau has a `shortDescription` field and uses `image-360x360c` sizing (unlike listing page superVau which uses custom `/3d/super_vau/` paths for agency ads):

```python
{
    "id": 50228804,              # int listing ID (not a hash)
    "categorySlug": "auti",
    "titleSlug": "mercedes-benz-gla-200-cdi-automatik",
    "title": "Mercedes-Benz GLA 200 CDI automatik...",
    "shortDescription": "Mercedes-Benz GLA 200 CDI, automatik –…",
    "image": "https://www.njuskalo.hr/image-360x360c/auti/...",
    "zoneId": 1,
    "url": "/auti/mercedes-benz-gla-200-cdi-automatik-oglas-50228804",
    "isPriceOnRequest": False,
    "priceFormatted": "...",
    "hidePrice": False
}
```

#### `popularBrands` — Complete List (14 entries)
Editorially curated brand shortcut links:

| ID | Brand | URL |
|---|---|---|
| 1 | Nike Air Force | `/od-glave-do-pete/air-force/` |
| 2 | Huawei | `/od-glave-do-pete/huawei-gt5/` |
| 3 | Xbox | `/informatika/xbox-360/?page=5` |
| 4 | Harley Benton | `/glazbala/harley-benton/` |
| 5 | Samsung | `/mobiteli/samsung-galaxy-s25-fe/` |
| 6 | Xiaomi | `/sportska-oprema/romobil-xiaomi-4/` |
| 7 | Parkside | `/strojevi-alati/parkside-pila/` |
| 8 | Massimo Dutti | `/od-glave-do-pete/massimo-dutti/` |
| 9 | Hisense | `/sve-za-dom/hisense-mikrovalna/` |
| 10 | Lenovo | `/informatika/lenovo-thinkpad-yoga/` |
| 11 | Fendt | `/strojevi-alati/fendt-vario/` |
| 59 | Linde | `/strojevi-alati/linde-h16/` |
| 60 | Gravel | `/sportska-oprema/gravel-bicikl/` |
| 61 | Michael Kors | `/od-glave-do-pete/michael-kors-torbe/` |

> Note: Brand URLs are keyword search URLs within a category — they're curated editorial links, not filter-based IDs.

#### `catalogs` — Retail Catalogues (Njupop subsystem)
17 active weekly catalogues from Croatian retailers. Uses a separate subdomain:

```python
{
    "id": "44c04ff360bb6572d520960edd022c2d54083fbb",  # SHA1 hash
    "title": "Eurospin katalog Pametna kupnja 27.05. - 02.06.2026.",
    "url": "https://katalozi.njuskalo.hr/katalog/eurospin-katalog-pametna-kupnja-2705-02062026-22220",
    "image": "https://images-katalozi.njuskalo.hr/data/image/160x160/51331/catalogue-eurospin-...-page-0-256650323.jpg"
}
```

Subdomain structure:
- **Catalogue pages:** `https://katalozi.njuskalo.hr/katalog/{slug}-{id}`
- **Catalogue images:** `https://images-katalozi.njuskalo.hr/data/image/{WxH}/{storeId}/catalogue-{slug}-page-{N}-{imageId}.jpg`

Image URL pattern for catalogues: `/data/image/{width}x{height}/{storeId}/catalogue-{slug}-page-{pageNum}-{imageId}.jpg`

Retailers seen: Eurospin, SPAR/INTERSPAR, Plodine, Lidl, Diskont Stanić, Vacom, KiK, Studenac, NTL, Boso, Izolirka, Lesnina, dm, Smit Commerce, Pet Centar, ZOOCITY.

### 21.7 Marketplace-Specific State (`homeMarketplacePage.pageData`)

#### `superVauListings` on Marketplace — Agency/Business Ad Schema
Unlike listing-page superVau (which has numeric IDs), marketplace superVau uses **SHA1 hash IDs** for agency/company ads and links to `/tvrtka/` pages:

```python
{
    "id": "eddeb25860d3ebf16ad1a925f0e6b81205aa4956",  # SHA1, not a listing ID
    "title": "Ideal Plus d.o.o.<br>https://www.idealplus.hr<br>...",  # raw HTML in title!
    "shortDescription": "",
    "image": "https://www.njuskalo.hr/3d/super_vau/SVT_Ideal-Plus.jpg",  # /3d/super_vau/ path
    "zoneId": 789,
    "url": "/tvrtka/ideal-plus%20",   # /tvrtka/{company-slug}
    "hidePrice": false,
    "richDescription": true           # optional flag indicating HTML in title
}
```

> **Important:** `title` may contain raw `<br>` HTML tags when `richDescription: true`. Strip HTML before displaying.

#### `horizontalSuperVauListings` — Standard Listings in a "Horizontal" Carousel
These have the same schema as regular listings but use `zoneId: 790` and link to `/tvrtka/` pages:

```python
{
    "id": 46523396,                           # int listing ID
    "categorySlug": "transportni-stambeni-kontejneri",
    "titleSlug": "akcija-kontejner-vikendica-antracit-varmus",
    "title": "AKCIJA! Kontejner vikendica antracit - Varmus Modular",
    "image": "https://www.njuskalo.hr/image-360x360c/...",
    "zoneId": 790,
    "url": "/transportni-stambeni-kontejneri/...-oglas-46523396",
    "hidePrice": false
}
```

#### `currentlyActualContent` — Editorial "Currently Relevant" Content Cards
9 curated seasonal/topical category cards. Each is essentially a category shortcut with a marketing headline:

```python
{
    "id": 165,
    "title": "Od starih do novih vrata preseli s nama!",
    "description": "Selidba nije laka. Pronađi pouzdanu uslugu na Njuškalu...",
    "image": "https://www.njuskalo.hr/slika-200x150-273228370.jpg",
    "routeType": "category",          # always "category" in observed data
    "rootSlug": "transporti-selidbe", # category slug
    "queryParams": {},                # additional filter params (empty here)
    "url": "/transporti-selidbe",
    "iconId": "transporti-selidbe"
}
```

Image URL pattern: `/slika-{WxH}-{imageId}.jpg` (e.g. `slika-200x150-273228370.jpg`)

#### `trends` — Trend Collections with Pre-loaded Listings
A curated trend/collection with 10 pre-loaded listings:

```python
{
    "id": 66,
    "title": "Payprotect oglasi",
    "url": "https://www.njuskalo.hr/search/?keywords=payprotect&isOnlinePaymentEnabled=1&sort=new",
    "image": "https://www.njuskalo.hr/slika-original-216602517.jpg",
    "listings": [
        {"id": 44376929, "title": "...", "priceFormatted": "45,00 €",
         "image": "...", "categorySlug": "objektivi", "titleSlug": "..."},
        ...  # 10 listings
    ]
}
```

### 21.8 Business/Agency Profile URL Patterns

Two URL patterns for business profiles, observed from featured store and superVau links:

```
/shop/{shopSlug}         # e.g. /shop/zalagaonicaeu1   (marketplace shops)
/tvrtka/{companySlug}    # e.g. /tvrtka/ideal-plus     (company pages)
/agencija/{agencySlug}   # e.g. /agencija/roelrealestate  (real estate agencies)
```

`featuredStore` in `__INITIAL_STATE__` uses `/shop/` URLs. The schema:

```python
{
    "id": "2027500",           # str, not int
    "image": "https://www.njuskalo.hr/logo-140x140/{slug}-logo2-{id}.jpg?quality=100",
    "url": "/shop/zalagaonicaeu1",
    "subListings": [
        {
            "id": 29636093,
            "title": "Starinska blanja...",
            "url": "/stare-stvari/starinska-blanja-oglas-29636093",
            "hasVideo": False,
            "hasMap": True,
            "hasGroundPlan": False
        },
        ...  # multiple sub-listings
    ]
}
```

> Note: `featuredStore.subListings` uses a reduced schema — only `id`, `title`, `url`, `hasVideo`, `hasMap`, `hasGroundPlan`. No price, image, or timestamps.

### 21.9 Blago Sub-Categories — Complete List with Counts

```python
# From browseListingsStore.pageData.categories[0]
# (note: wrapped in an outer array — access as categories[0])
```

| ID | Title | Count | URL |
|---|---|---|---|
| 9800 | Antikviteti | 12,949 | `/antikviteti` |
| 9750 | Antikvarne knjige | 19,210 | `/antikvarne-knjige` |
| 9802 | Starine | 26,928 | `/stare-stvari` |
| 9804 | Replike | 897 | `/replike` |
| 9805 | Militarija | 12,356 | `/militarija` |
| 9801 | Umjetničke slike | 19,540 | `/slike` |
| 13106 | Skulpture | 2,165 | `/skulpture` |
| 13123 | Suveniri | 5,773 | `/suveniri` |
| 12799 | Razglednice i fotografije | 13,696 | `/razglednice-fotografije` |
| 13107 | Posteri i plakati | 3,257 | `/posteri-plakati` |
| 13185 | Sličice i albumi | 6,474 | `/slicice-albumi` |
| 13485 | Telefonske kartice | 1,963 | `/telefonske-kartice` |
| 12800 | Gobleni i tapiserije | 1,339 | `/gobleni` |
| 9799 | Filatelija | 10,743 | `/filatelija` |
| 12802 | Značke | 5,022 | `/znacke` |
| **9803** | **Numizmatika** | **45,323** | `/numizmatika` |
| → 12901 | ↳ Kovanice | 31,213 | `/numizmatika-kovanice` |
| → 12902 | ↳ Novčanice | 13,162 | `/numizmatika-novcanice` |
| → 12903 | ↳ Ostalo za numizmatiku | 948 | `/numizmatika-ostalo` |
| 13056 | Materijal i oprema za umjetnost | 295 | `/umjetnost-materijal` |
| → 13057 | ↳ Decoupage | 25 | `/decoupage-materijal` |
| → 13058 | ↳ Slikarstvo | 84 | `/slikarski-pribor` |
| → 13059 | ↳ Ostali materijal | 186 | `/umjetnost-oprema` |

> **Gotcha:** `pageData.categories` is a list containing one element which is itself a list of category dicts: `categories[0][i]`. Access as `pageData['categories'][0]`, not `pageData['categories']`.

### 21.10 `popularTags` — Tag-Based Search URLs

The `browseListingsStore.pageData.popularTags` array (25 entries on Blago) provides curated search tags. Each is a keyword URL within the category:

```python
{
    "id": "1397",
    "title": "lovački psi",
    "url": "/blago/lovacki-psi/"   # URL pattern: /{category}/{keyword-slug}/
}
```

This reveals an undocumented URL pattern: **keyword-within-category search** via slug:

```
https://www.njuskalo.hr/{categorySlug}/{keywordSlug}/
```

Examples observed:
- `/blago/mlinac-za-kavu/`
- `/blago/coca-cola/`
- `/blago/stari-radio/`

These are distinct from the `/search/?keywords=` pattern — they appear to be SEO-friendly pre-indexed keyword pages within a category.

### 21.11 `submitFreeListingCallToAction` — Free Listing Insertion Point

The `pageData` contains a hint about where the site injects a "post your listing for free" CTA card within the results:

```python
{
    "position": [3],      # inject after position 3 in the listing list
    "page": 1,            # only on page 1
    "url": "/predaja-oglasa?current_category_id=9798"  # pre-fills the category
}
```

When scraping, skip `<li>` items at this position that contain the CTA rather than a listing.

### 21.12 Complete Image URL Pattern Summary

All observed image URL patterns across the site:

| Pattern | Example | Used for |
|---|---|---|
| `/image-200x150/{catSlug}/{slug}-slika-{id}.jpg` | `.../nekretnine/zagreb-...-slika-278369492.jpg` | Listing card thumbnails |
| `/image-360x360c/{catSlug}/{slug}-slika-{id}.jpg` | `.../auti/mercedes-...-slika-275294107.jpg` | Square listing thumbnails (homepage/marketplace) |
| `/image-w1000/{catSlug}/{slug}-slika-{id}.jpg` | (same pattern, size swap) | Large detail images |
| `/slika-original-{id}.jpg` | `.../slika-original-278154577.jpg` | Full-size hero/banner images |
| `/slika-{WxH}-{id}.jpg` | `.../slika-200x150-273228370.jpg` | Editorial content images (fixed size, no category) |
| `/logo-140x140/{shopSlug}-logo2-{storeId}.jpg?quality=100` | `.../logo-140x140/zalagaonica_eu-logo2-2027500.jpg` | Shop/agency logos |
| `/3d/super_vau/{filename}.jpg` | `.../3d/super_vau/SVT_Ideal-Plus.jpg` | SuperVau agency banner images |
| `images-katalozi.njuskalo.hr/data/image/{WxH}/{storeId}/catalogue-{slug}-page-{N}-{id}.jpg` | (katalozi subdomain) | Retail catalogue page images |

### 21.13 Site Sections Not Previously Documented

| URL | Description |
|---|---|
| `/search/?keywords={term}` | Full-text keyword search across all categories |
| `/search/?keywords={term}&{filters}` | Keyword + filter combination search |
| `/predaja-oglasa` | Post a new listing (submission form) |
| `/predaja-oglasa?current_category_id={id}` | Post listing pre-filled to category |
| `/prijava/` | Login page |
| `/registracija/` | Registration page |
| `/registracija/?context=` | Registration with context |
| `/sitemap/` | HTML sitemap |
| `/android-manifest` | PWA Android manifest |
| `/shop/{slug}` | Marketplace seller/shop profile |
| `/tvrtka/{slug}` | Company profile page |
| `/agencija/{slug}` | Real estate agency profile |
| `/info/disclaimer` | Legal disclaimer |
| `/help/kontakt-i-pomoc-tid1` | Contact & help |
| `/help/o-nama/politika-privatnosti/politika-privatnosti-cid359` | Privacy policy |
| `/help/oglasavanje-tid3` | Advertising info |
| `/help/nacini-placanja-tid5` | Payment methods |
| `https://blog.njuskalo.hr/` | Blog (separate subdomain) |
| `https://katalozi.njuskalo.hr/` | Retail catalogues (separate subdomain) |
| `https://images-katalozi.njuskalo.hr/` | Catalogue images CDN |

### 21.14 `listHeader` — Category Description with Embedded HTML

Some categories include a `listHeader` with an embedded HTML string for their description/banner:

```python
pd['listHeader'] = {
    "title": "Pronađeno blago",
    "description": "Antikviteti, starine, umjetnine... <div class=\"coupons__container\"> <a href=\"https://www.njuskalo.hr/blago?isOnlinePaymentEnabled=1&utm_source=...\"> <img src=\"https://www.njuskalo.hr/slika-original-253161649.jpg\" /> </a></div> ..."
}
```

> The `description` field can contain raw HTML including `<img>` and `<a>` tags. Strip HTML before using as plain text.

---

## 22. Individual Listing Detail Pages

This section covers scraping a single listing page, e.g.:
```
GET https://www.njuskalo.hr/nekretnine/zagreb-novogradnja-blato-4soban-stan-oglas-47225243
```

### 22.1 Architecture Difference: Legacy SSR (Not Vue)

**Critical:** The individual listing detail page uses a **completely different rendering architecture** from search/listing pages. It is **not a Vue SPA** — it is a classic server-rendered PHP page with a jQuery/legacy `app.boot` component system. There is **no `window.__INITIAL_STATE__`** on listing detail pages.

Instead, data is distributed across:
1. Multiple `app.boot.push({name, values})` inline script blocks
2. A `schema.org` JSON-LD `<script type="application/ld+json">` block
3. Rendered HTML with well-structured CSS class names (`ClassifiedDetail*`)
4. Two XHR calls to the `ccapi/v4/` REST API (called after page load)

### 22.2 The `app.boot` Component System

The page bootstraps itself by calling `app.boot.push({name, values})` for each component. Each push contains a component name and its data payload. These are inline `<script>` tags in the HTML and are parseable without JavaScript execution.

**Pattern:**
```html
<script>app.boot.push({"name": "ComponentName", "values": {...}})</script>
```

**Key components and their data:**

```python
import re, json

def extract_boot_configs(html: str) -> dict:
    """Extract all app.boot.push configs keyed by component name."""
    configs = {}
    for m in re.finditer(r'app\.boot\.push\((\{.*?\})\)\s*;?\s*$', html, re.MULTILINE | re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            name = obj.get('name')
            if name:
                configs[name] = obj.get('values', {})
        except json.JSONDecodeError:
            pass
    return configs

configs = extract_boot_configs(html)
```

**Component payloads documented:**

#### `ClassifiedDetailGallery`
```python
{
    "adId":    47225243,         # int — listing ID
    "adTitle": "NOVI ZAGREB...", # str — listing title
    "ownerId": 2958239,          # int — owner/seller user ID
    "isSandboxMode": False,
    "isUnavailable": False       # True if listing is sold/expired
}
```

#### `ClassifiedDetailSummary`
```python
{
    "ownerId":      2958239,
    "adId":         47225243,
    "adTitle":      "NOVI ZAGREB - NOVOGRADNJA BLATO - 4SOBAN STAN! (prodaja)",
    "adShareUrl":   "https://www.njuskalo.hr/nekretnine/...-oglas-47225243",
    "adHeadImageUrl": "https://www.njuskalo.hr/image-140x140/nekretnine/...-slika-267868991.jpg",
    "isUnavailable": False,
    "isComparable":  False,
    "isSaveable":    True,
    "isSandboxMode": False,
    "loginUrl":      "https://www.njuskalo.hr/prijava/?returnUrl=...",
    "categoryId":    9580,
    "adDomesticPrice":        284493,       # float — price in EUR (no formatting)
    "hasPriceRangeDomestic":  False,        # True for price range listings
    "priceRangeDomestic":     None,         # dict if hasPriceRangeDomestic=True
    "roundPrice":             False,
    "adWholesalePrice":       False,        # True if wholesale/VAT price shown
    "escrowFaqUrl":           "https://www.njuskalo.hr/help/.../njuskalo-payprotect-sid34",
    "compareAdsUrl":          "https://www.njuskalo.hr/compare-ads/",
    "isAdInJobsVertical":     False,
    # Xiti (Piano Analytics) tracking action names:
    "xitiTrackingFragments": {
        "action_buy_now":       "ClickOnBuyNow",
        "action_learn_more_escrow": "ClickOnMorePayProtect",
        "action_send_offer":    "ClickOnSendOffer",
        "action_buy_now_modal": "ClickOnBuyNowModal",
        "action_bidding_modal": "ClickOnBiddingModal"
    },
    "creditPageIds": [28],      # list — associated credit page IDs (mortgage ads)
    "trackingDetails": {"savedAdContext": "new_detailview"}
}
```

> **Key scraping value:** `adDomesticPrice` gives the raw numeric price (e.g. `284493`) without string parsing. More reliable than parsing `priceFormatted`.

#### `ClassifiedDetailMap`
```python
{
    "el":       ".ClassifiedDetailMap",
    "id":       47225243,
    "adShareUrl": "...",
    "adTitle":    "...",
    "mapData": {
        "center": [15.9200478, 45.7652477],  # [lng, lat]
        "defaultMarker": {
            "lat": 45.7652477,
            "lng": 15.9200478,
            "approximate": False,    # True if location is approximate (privacy mode)
            "data": {
                "title":  "...",
                "url":    "...",
                "image":  "https://www.njuskalo.hr/image-w185/nekretnine/...",
                "price":  "284.493 €"
            },
            "circle": {
                "radius": 500,       # privacy blur radius in metres (when approximate=True)
                "paint": {...}       # Mapbox GL paint config
            }
        }
    }
}
```

> **Note:** Coordinates are `[lng, lat]` order (GeoJSON/Mapbox convention), **not** `[lat, lng]`. The `approximate` flag indicates the owner chose not to show the exact address — the marker is placed within a 500m radius circle.

#### `ContactSellerModal`
```python
{
    "classifiedId":     47225243,
    "ownerUsername":    "rinanekretnine",   # str — seller's username/slug
    "userRating":       0,                  # float — seller rating
    "numberOfRatings":  0,                  # int
    "privacyPolicyUrl": "https://www.njuskalo.hr/help/..."
}
```

#### `GTMTracking`
```python
{
    "adId":               47225243,
    "categoryIds":        [1, 9580],                          # [parent, leaf] category IDs
    "adStatus":           "active",                           # "active" | "sold" | "expired"
    "adOwnerType":        "store",                            # "store" | "user" (private)
    "isAdPaidToBePromoted": True,                             # bool — paid VauVau listing
    "isEscrowEnabledForAd": False,                            # bool — PayProtect available
    "categoryNames":      ["Nekretnine", "Prodaja stanova", "Grad Zagreb", "Novi Zagreb - Zapad"]
}
```

> **Key scraping value:** `adStatus` tells you if the listing is still active, sold, or expired — without parsing page content. `adOwnerType` distinguishes agencies (`"store"`) from private sellers (`"user"`). `categoryNames` gives the full breadcrumb category path.

#### `ClassifiedDetailSimilarAds`
```python
{
    "adId":         47225243,
    "placement":    "bottom",
    "pageLimit":    12       # how many similar ads to load via ccapi
}
```

#### `ClassifiedDetailRecommendedAds`
```python
{
    "adId":         47225243,
    "placement":    "bottom",
    "pageLimit":    12
}
```

#### `MainSearchBox`
```python
{
    "hasAutosuggest":              True,
    "searchRoute":                 "https://www.njuskalo.hr/search/",
    "minKeywordsLengthNecessary":  True
}
```
This confirms the autosuggest search endpoint is `https://www.njuskalo.hr/search/`.

#### `SavedSearchCreate`
```python
{
    "searchContext":        "store",          # context for the saved search
    "defaultSuggestedTitle": "Rina Nekretnine d.o.o.",  # pre-filled alert title
    "searchParameters":     {"userId": "2958239"},       # search by seller ID
    "mobileAppIosAppStoreUrl": "https://apps.apple.com/app/apple-store/id492744536",
    "mobileAppAndroidStoreUrl": "https://play.google.com/store/apps/details?id=hr.njuskalo.app"
}
```
> Reveals the **iOS App Store ID** (`id492744536`) and **Android package name** (`hr.njuskalo.app`).

### 22.3 The `defractalPage` Analytics Object

Contains a clean, flat data structure about the listing useful for categorisation:

```javascript
window.defractalPage = {
    type:        'DPO',              // always 'DPO' on listing pages
    id:          '47225243',         // listing ID as string
    price:       '284493',           // price as string (EUR, no formatting)
    channel:     'nekretnine',       // top-level category slug
    classA:      'prodaja-stanova',  // leaf category slug
    classB:      '',                 // sub-filter (e.g. brand for cars)
    classC:      '',
    classD:      'zagreb',           // location slug
};
```

**Parse it:**
```python
m = re.search(
    r'window\.defractalPage\s*=\s*\{([^}]+)\}',
    html
)
if m:
    # Parse the JS object (unquoted keys) into Python dict
    fields = {}
    for line in m.group(1).split(','):
        kv = line.strip()
        km = re.match(r"(\w+)\s*:\s*'([^']*)'", kv)
        if km:
            fields[km.group(1)] = km.group(2)
    # fields = {'type': 'DPO', 'id': '47225243', 'price': '284493',
    #           'channel': 'nekretnine', 'classA': 'prodaja-stanova',
    #           'classB': '', 'classC': '', 'classD': 'zagreb'}
```

### 22.4 The `dataLayer` Virtual Pageview

```javascript
window.dataLayer = [{"NjuskaloVirtualPageview": "/nekretnine/prodaja-stanova/zagreb/oglas-47225243-b2c-active"}]
```

The virtual pageview path encodes: `/{topCategory}/{leafCategory}/{location}/oglas-{id}-{b2c|c2c}-{status}`

- `b2c` = business-to-consumer (store/agency seller)
- `c2c` = consumer-to-consumer (private seller)
- `active` / `sold` / `expired` = listing status

Parse it:
```python
m = re.search(r'"NjuskaloVirtualPageview"\s*:\s*"([^"]+)"', html)
if m:
    path = m.group(1)
    # "/nekretnine/prodaja-stanova/zagreb/oglas-47225243-b2c-active"
    parts = path.split('/')
    # parts[-1] = "oglas-47225243-b2c-active"
    last = parts[-1]  # "oglas-{id}-{type}-{status}"
    _, listing_id, seller_type, status = last.rsplit('-', 3)
    # listing_id='47225243', seller_type='b2c', status='active'
```

### 22.5 The `schema.org` JSON-LD Block

Every listing page has a `<script type="application/ld+json">` block containing schema.org structured data — this is the cleanest way to extract core listing data:

```python
import json, re

def extract_schema_org(html: str) -> dict | None:
    """Extract the schema.org JSON-LD block from a listing page."""
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        html, re.DOTALL
    )
    if m:
        return json.loads(m.group(1))
    return None

schema = extract_schema_org(html)
# Returns:
{
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "Product",
            "name": "NOVI ZAGREB - NOVOGRADNJA BLATO - 4SOBAN STAN! (prodaja)",
            "description": "NOVOGRADNJA BLATO – S3 - 4-soban stan 86.21m2...",
            "image": "https://www.njuskalo.hr/image-xlsize/nekretnine/...-slika-267868991.jpg",
            "sku": 47225243,               # int — listing ID
            "offers": {
                "@type": "Offer",
                "availability": "https://schema.org/InStock",  # InStock | OutOfStock (sold)
                "url":  "https://www.njuskalo.hr/nekretnine/...-oglas-47225243",
                "price": 284493,           # float — price in EUR
                "priceCurrency": "EUR"
            }
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Oglasnik", "item": "https://www.njuskalo.hr/"},
                {"@type": "ListItem", "position": 2, "name": "Nekretnine", "item": ".../nekretnine"},
                {"@type": "ListItem", "position": 3, "name": "Prodaja stanova", "item": ".../prodaja-stanova"},
                {"@type": "ListItem", "position": 4, "name": "Grad Zagreb", "item": ".../prodaja-stanova/zagreb"},
                {"@type": "ListItem", "position": 5, "name": "Novi Zagreb - Zapad", "item": ".../prodaja-stanova/novi-zagreb-zapad"}
            ]
        }
    ]
}
```

> **Key scraping value:**
> - `offers.price` — raw numeric price, no parsing needed
> - `offers.availability` — `InStock` = active, `OutOfStock` = sold/expired
> - `sku` — listing ID as int
> - The `BreadcrumbList` gives the full geographic hierarchy of the listing's location (up to 5 levels)
> - `image` uses the `image-xlsize` size variant (new — not seen elsewhere)

### 22.6 HTML Structure of the Listing Detail Page

The listing page uses a completely different set of CSS classes from the search pages:

```
<main class="ClassifiedDetail">
  ├── ClassifiedDetailGallery          # photo carousel
  ├── ClassifiedDetailSummary          # title + price + CTA buttons
  │   ├── ClassifiedDetailSummary-title
  │   ├── ClassifiedDetailSummary-priceDomestic  # "284.493 €"
  │   ├── ClassifiedDetailSummary-priceLabel     # "Cijena"
  │   └── ClassifiedDetailSummary-adCode         # listing reference code
  ├── ClassifiedDetailHighlightedAttributes  # key facts chips (area, rooms, badge)
  ├── ClassifiedDetailBasicDetails       # full key-value attribute table
  ├── ClassifiedDetailPropertyGroups    # grouped feature lists
  ├── ClassifiedDetailAdditionalInformation  # extra info block
  ├── ClassifiedDetailDescription       # full text description
  ├── ClassifiedDetailMap               # map embed
  ├── ClassifiedDetailOwnerDetails      # seller info (both positions)
  ├── ClassifiedDetailSystemDetails     # listing metadata (date, views, expiry)
  ├── ClassifiedDetailCredits           # mortgage/credit partner ads
  ├── ClassifiedDetailSimilarAds        # similar listings carousel
  ├── ClassifiedDetailRecommendedAds    # recommended listings carousel
  └── ClassifiedDetailSavedSearch       # "save this search" form
```

#### Parsing the Key Facts Table (`ClassifiedDetailBasicDetails`)

The `dl.ClassifiedDetailBasicDetails-list` contains `dt`/`dd` pairs with all structured attributes:

```python
from bs4 import BeautifulSoup

def parse_basic_details(html: str) -> dict:
    """Parse the key facts table from a listing detail page."""
    soup = BeautifulSoup(html, 'html.parser')
    basic = soup.find('div', class_='ClassifiedDetailBasicDetails')
    if not basic:
        return {}
    result = {}
    dl = basic.find('dl', class_='ClassifiedDetailBasicDetails-list')
    if dl:
        terms = dl.find_all('dt', class_='ClassifiedDetailBasicDetails-listTerm')
        defs  = dl.find_all('dd', class_='ClassifiedDetailBasicDetails-listDefinition')
        for term, defn in zip(terms, defs):
            key = term.get_text(strip=True)
            val = defn.get_text(strip=True)
            result[key] = val
    return result

# Example output for this apartment:
{
    "Lokacija":          "Grad Zagreb, Novi Zagreb - Zapad, Blato",
    "Tip stana":         "U stambenoj zgradi",
    "Broj etaža":        "Jednoetažni",
    "Broj soba":         "4-sobni",
    "Kat":               "Prizemlje",
    "Ukupni broj katova": "2",
    "Stambena površina": "86,21 m²",
    "Broj parkirnih mjesta": "1",
    "Balkon/Lođa/Terasa": "Lođa (Loggia)",
    "Šifra objekta":     "2016",        # developer's unit reference code
}
```

#### Parsing the Property Groups (`ClassifiedDetailPropertyGroups`)

Grouped feature lists (multi-value attributes):

```python
def parse_property_groups(html: str) -> dict:
    """Parse grouped feature lists from a listing detail page."""
    soup = BeautifulSoup(html, 'html.parser')
    groups_div = soup.find('div', class_='ClassifiedDetailPropertyGroups--standard')
    if not groups_div:
        return {}
    result = {}
    for group in groups_div.find_all('section', class_='ClassifiedDetailPropertyGroups-group'):
        title_el = group.find('h3', class_='ClassifiedDetailPropertyGroups-groupTitle')
        title = title_el.get_text(strip=True) if title_el else 'Unknown'
        items = [li.get_text(strip=True)
                 for li in group.find_all('li', class_='ClassifiedDetailPropertyGroups-groupListItem')]
        result[title] = items
    return result

# Example output:
{
    "Grijanje":                            ["Klima uređaj: Da"],
    "Podaci o objektu":                    ["Novogradnja", "Lift", "Gradski vodovod", "Gradska kanalizacija"],
    "Vrsta parkinga":                      ["Vanjsko ne-natkriveno mjesto"],
    "Funkcionalnosti i ostale karakteristike": ["Zasebni ulaz u objekt", "Protuprovalna vrata", "Podno grijanje"],
    "Kupaonica i WC":                      ["Broj kupaonica s WC-om: 1", "Broj WC-a: 1"],
    "Ostali objekti i površine":           ["Dvorište/vrt", "Podrum"],
}
```

#### Parsing the System Details (`ClassifiedDetailSystemDetails`)

```python
def parse_system_details(html: str) -> dict:
    """Parse listing metadata (publish date, views, expiry)."""
    soup = BeautifulSoup(html, 'html.parser')
    dl = soup.find('dl', class_='ClassifiedDetailSystemDetails-list')
    if not dl:
        return {}
    result = {}
    for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
        result[dt.get_text(strip=True)] = dd.get_text(strip=True)
    return result

# Example output:
{
    "Oglas objavljen": "07.05.2026. u 11:33",   # published date+time
    "Do isteka još":   "do prodaje",             # expiry: "do prodaje"=until sold, or a date
    "Oglas prikazan":  "8998 puta",              # view count
}
```

> **"Do isteka još"** values: `"do prodaje"` = permanent (until sold), otherwise a date string like `"15.06.2026."`. This reveals the listing tier.

#### Parsing the Gallery Images

All listing images are accessible from `data-*` attributes on `<li>` elements in the gallery:

```python
def parse_gallery_images(html: str) -> list:
    """Extract all gallery images with all available size URLs."""
    soup = BeautifulSoup(html, 'html.parser')
    images = []
    gallery = soup.find('ul', class_='ClassifiedDetailGallery-sliderList')
    if not gallery:
        return images
    for li in gallery.find_all('li', class_='ClassifiedDetailGallery-sliderListItem--image'):
        image_id = li.get('data-id')
        large_url = li.get('data-large-image-url')  # image-xlsize
        thumb_url = li.get('data-thumb-image-url')   # image-80x60
        img = li.find('img')
        main_url = (img.get('src') or img.get('data-src')) if img else None  # image-w920x690
        images.append({
            'id':         image_id,
            'index':      int(li.get('data-index', 0)),
            'width':      int(li.get('data-large-image-width', 0)),
            'height':     int(li.get('data-large-image-height', 0)),
            'url_large':  large_url,   # image-xlsize (up to 1600px wide)
            'url_main':   main_url,    # image-w920x690
            'url_thumb':  thumb_url,   # image-80x60
            # Derive other sizes:
            # image-200x150: replace size in large_url
            # image-360x360c: replace size in large_url
            # image-w185: used in map popup
            # image-140x140: used in adHeadImageUrl
        })
    return images

# Example for first image:
{
    "id":        "267868991",
    "index":     0,
    "width":     1600,
    "height":    900,
    "url_large": "https://www.njuskalo.hr/image-xlsize/nekretnine/zagreb-novogradnja-blato-4soban-stan-slika-267868991.jpg",
    "url_main":  "https://www.njuskalo.hr/image-w920x690/nekretnine/...-slika-267868991.jpg",
    "url_thumb": "https://www.njuskalo.hr/image-80x60/nekretnine/...-slika-267868991.jpg",
}
```

### 22.7 New Image Size Variants Discovered on Listing Pages

| Size String | Dimensions | Source |
|---|---|---|
| `image-xlsize` | Up to 1600×900px | `data-large-image-url` on gallery item; schema.org `image` |
| `image-w920x690` | 920×690px | Gallery main slide `<img src>` |
| `image-80x60` | 80×60px | Gallery thumbnail `data-thumb-image-url` |
| `image-140x140` | 140×140px | `adHeadImageUrl` in ClassifiedDetailSummary |
| `image-w185` | 185px wide | Map popup image |

All follow the same URL pattern — just swap the size segment.

### 22.8 The `ccapi/v4/` REST API — A True JSON API

This is the most significant discovery from the listing page. The site exposes a **versioned JSON:API** at `/ccapi/v4/`. It requires a **Bearer token** obtained via OAuth2.

#### Authentication

```
POST https://www.njuskalo.hr/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=njuskalo_js_app
&client_secret=1412aa6f3a6194adefceb8e547d5e6aa
```

**Response:**
```json
{
    "token_type":   "Bearer",
    "expires_in":   21600,
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ..."
}
```

- `expires_in`: **21600 seconds = 6 hours**. Cache the token and refresh after expiry.
- `client_id` and `client_secret` are hardcoded in the page JS — these are the public JavaScript app credentials, not user credentials.

**Python token fetcher:**
```python
import requests

OAUTH_URL    = "https://www.njuskalo.hr/oauth2/token"
CLIENT_ID    = "njuskalo_js_app"
CLIENT_SECRET = "1412aa6f3a6194adefceb8e547d5e6aa"

def get_bearer_token() -> str:
    resp = requests.post(OAUTH_URL, data={
        "grant_type":    "client_credentials",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]
```

#### Endpoint 1: Similar Listings

```
GET /ccapi/v4/similar-classifieds
```

Parameters:
| Param | Example | Description |
|---|---|---|
| `filter[classifiedId]` | `47225243` | Listing ID to find similars for |
| `page[limit]` | `12` | Max results to return |
| `include` | `image.variation_360x360c,image.variations` | Sideloaded relationships |

**Full example:**
```
GET https://www.njuskalo.hr/ccapi/v4/similar-classifieds?filter[classifiedId]=47225243&page[limit]=12&include=image.variation_360x360c,image.variations
Authorization: Bearer eyJ...
```

**Response (JSON:API format):**
```json
{
    "jsonapi": {"version": "1.0"},
    "meta": {
        "total":      12,
        "totalCount": 12,
        "requestId":  "a6851cb2-214b-4691-945a-3afed94e2d87"
    },
    "links": {"self": "..."},
    "data": [
        {
            "type": "similar-classifieds",
            "id":   "48372323",
            "attributes": {
                "label":            "Stan: Zagreb (Blato), 81.32 m2, novogradnja",
                "url":              "nekretnine/stan-zagreb-blato-79.98-m2-novogradnja-oglas-48372323",
                "currencyISO":      "EUR",
                "price":            304950,      # float, raw EUR price
                "hidePrice":        false,
                "isPriceOnRequest": false
            },
            "relationships": {
                "image": {"data": {"type": "image", "id": "260398141"}}
            }
        }
    ],
    "included": [
        {
            "type": "imageVariation",
            "id":   "260398141-variation-360x360c",
            "attributes": {
                "variationName": "360x360c",
                "url":    "https://www.njuskalo.hr/scripts/get_image_variation.php?image_id=260398141&var_suff=360x360c",
                "width":  360,
                "height": 360,
                "sizeType": "thumbnail big"
            }
        },
        {
            "type": "image",
            "id":   "260398141",
            "attributes": {"order": null},
            "relationships": {
                "variations": {"data": [{"type": "imageVariation", "id": "260398141-variation-360x360c"}]}
            }
        }
    ]
}
```

> Note: The `url` attribute is a **relative path** without the leading slash and without the domain. Prepend `https://www.njuskalo.hr/` to get the full URL.

**Resolving images from the JSON:API response:**
```python
def resolve_similar_ads(response: dict) -> list:
    """Resolve similar-classified listings with image URLs."""
    # Build image URL lookup from included
    image_urls = {}
    for inc in response.get('included', []):
        if inc['type'] == 'imageVariation':
            image_id = inc['id'].split('-variation-')[0]
            image_urls[image_id] = inc['attributes']['url']

    results = []
    for item in response.get('data', []):
        attrs = item['attributes']
        image_id = item.get('relationships', {}).get('image', {}).get('data', {}).get('id')
        results.append({
            'id':               item['id'],
            'title':            attrs['label'],
            'url':              'https://www.njuskalo.hr/' + attrs['url'],
            'price':            attrs['price'],
            'currency':         attrs.get('currencyISO', 'EUR'),
            'hide_price':       attrs['hidePrice'],
            'price_on_request': attrs['isPriceOnRequest'],
            'image_url':        image_urls.get(image_id, ''),
        })
    return results
```

> **Note on image URLs in `ccapi/v4/`:** The `included` image variation URLs use a **different pattern** — `/scripts/get_image_variation.php?image_id={id}&var_suff=360x360c` — rather than the direct `/image-360x360c/...` path pattern seen elsewhere. Both resolve to the same image.

#### Endpoint 2: Recommended Ads

```
GET /ccapi/v4/ad-detail-view/recommended-ads
```

Parameters:
| Param | Example | Description |
|---|---|---|
| `filter[adId]` | `47225243` | Listing ID to get recommendations for |
| `page[limit]` | `12` (default) | Max results |
| `page[offset]` | `0` (default) | Pagination offset |

**Response (JSON:API format, slightly different from similar-classifieds):**
```json
{
    "jsonapi": {"version": "1.0"},
    "meta": {"total": 12},
    "links": {
        "self":  "...?filter[adId]=47225243&page[limit]=12&page[offset]=0",
        "first": "...",
        "last":  "...",
        "prev":  null,
        "next":  null
    },
    "data": [
        {
            "type": "recommended-ads",
            "id":   "47305875",
            "attributes": {
                "title":            "ZAGREB - BLATO - NOVOGRADNJA - STAN SA TRI SPAVAĆE SOBE!",
                "url":              "https://www.njuskalo.hr/nekretnine/...-oglas-47305875",  # FULL URL here!
                "formattedPrice":   "272.118,00 €",
                "price":            272118,
                "isPriceOnRequest": false,
                "isAdSaved":        false,
                "hidePrice":        false
            },
            "relationships": {
                "adImage": {"data": {"type": "recommended-ads-images", "id": "267868848"}}
            }
        }
    ],
    "included": [
        {
            "type": "recommended-ads-images",
            "id":   "267868848",
            "attributes": {
                "url": "https://www.njuskalo.hr/image-360x360c/nekretnine/...-slika-267868848.jpg"
            }
        }
    ]
}
```

Key differences from `similar-classifieds`:
- `url` is a **full absolute URL** (not a relative path)
- Has `formattedPrice` (formatted string) in addition to raw `price`
- Has `isAdSaved` flag
- Image type is `recommended-ads-images` (not `imageVariation`)
- Image `url` uses the **standard `/image-360x360c/` path** (not the PHP script)
- Supports **pagination** via `page[limit]` and `page[offset]` with `links.next`

### 22.9 The `get_credit_page_logo.php` Script

A legacy PHP endpoint that serves mortgage/credit partner logo images:
```
GET /scripts/get_credit_page_logo.php?image_id={imageId}
```
This appears in the `ClassifiedDetailCredits` section which shows mortgage/credit partner ads (Kompare.hr). Not useful for scraping listings, but worth knowing to distinguish it from listing image requests.

### 22.10 Complete Listing Detail Scraper

```python
import re, json, time, requests
from bs4 import BeautifulSoup

# ── Token management ─────────────────────────────────────────────────

_token_cache = {"token": None, "expires_at": 0}

def get_bearer_token() -> str:
    """Get a cached Bearer token, refreshing if expired."""
    if time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    resp = requests.post(
        "https://www.njuskalo.hr/oauth2/token",
        data={"grant_type": "client_credentials",
              "client_id": "njuskalo_js_app",
              "client_secret": "1412aa6f3a6194adefceb8e547d5e6aa"}
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"]
    return _token_cache["token"]

# ── Listing page parsers ──────────────────────────────────────────────

def scrape_listing_detail(listing_id: int, category_slug: str, title_slug: str) -> dict:
    """Scrape a full listing detail page."""
    url = f"https://www.njuskalo.hr/{category_slug}/{title_slug}-oglas-{listing_id}"
    resp = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    resp.raise_for_status()
    html = resp.text

    result = {"id": listing_id, "url": url}

    # 1. schema.org (price, availability, breadcrumbs)
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if m:
        schema = json.loads(m.group(1))
        for node in schema.get('@graph', []):
            if node['@type'] == 'Product':
                result['title']         = node.get('name')
                result['description']   = node.get('description')
                result['image_xl']      = node.get('image')
                result['price']         = node['offers']['price']
                result['currency']      = node['offers']['priceCurrency']
                result['is_available']  = 'InStock' in node['offers'].get('availability', '')
            elif node['@type'] == 'BreadcrumbList':
                result['breadcrumbs'] = [
                    {'name': i['name'], 'url': i.get('item')}
                    for i in node['itemListElement']
                ]

    # 2. GTMTracking (status, owner type)
    for m in re.finditer(r'app\.boot\.push\((\{.*?\})\)\s*;?$', html, re.MULTILINE | re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            if obj.get('name') == 'GTMTracking':
                v = obj['values']
                result['status']            = v.get('adStatus')
                result['owner_type']        = v.get('adOwnerType')
                result['is_promoted']       = v.get('isAdPaidToBePromoted')
                result['is_escrow_enabled'] = v.get('isEscrowEnabledForAd')
                result['category_ids']      = v.get('categoryIds')
                result['category_names']    = v.get('categoryNames')
            elif obj.get('name') == 'ClassifiedDetailSummary':
                v = obj['values']
                result['price_raw']     = v.get('adDomesticPrice')
                result['owner_id']      = v.get('ownerId')
                result['ad_id']         = v.get('adId')
            elif obj.get('name') == 'ClassifiedDetailMap':
                md = obj['values'].get('mapData', {}).get('defaultMarker', {})
                result['lat']         = md.get('lat')
                result['lng']         = md.get('lng')
                result['approximate'] = md.get('approximate')
            elif obj.get('name') == 'ContactSellerModal':
                v = obj['values']
                result['owner_username'] = v.get('ownerUsername')
                result['owner_rating']   = v.get('userRating')
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. HTML parsing
    soup = BeautifulSoup(html, 'html.parser')

    # Basic details (key-value table)
    result['basic_details'] = {}
    dl = soup.find('dl', class_='ClassifiedDetailBasicDetails-list')
    if dl:
        for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
            result['basic_details'][dt.get_text(strip=True)] = dd.get_text(strip=True)

    # Property groups (feature lists)
    result['property_groups'] = {}
    groups_div = soup.find('div', class_='ClassifiedDetailPropertyGroups--standard')
    if groups_div:
        for group in groups_div.find_all('section', class_='ClassifiedDetailPropertyGroups-group'):
            title_el = group.find('h3')
            title = title_el.get_text(strip=True) if title_el else '?'
            items = [li.get_text(strip=True)
                     for li in group.find_all('li', class_='ClassifiedDetailPropertyGroups-groupListItem')]
            result['property_groups'][title] = items

    # System details (views, publish date)
    sys_dl = soup.find('dl', class_='ClassifiedDetailSystemDetails-list')
    result['system_details'] = {}
    if sys_dl:
        for dt, dd in zip(sys_dl.find_all('dt'), sys_dl.find_all('dd')):
            result['system_details'][dt.get_text(strip=True)] = dd.get_text(strip=True)

    # Full description text
    desc_div = soup.find('div', class_='ClassifiedDetailDescription-text')
    if desc_div:
        result['description_full'] = desc_div.get_text('\n', strip=True)

    # Gallery images
    result['images'] = []
    gallery = soup.find('ul', class_='ClassifiedDetailGallery-sliderList')
    if gallery:
        for li in gallery.find_all('li', class_='ClassifiedDetailGallery-sliderListItem--image'):
            img_el = li.find('img')
            result['images'].append({
                'id':        li.get('data-id'),
                'index':     int(li.get('data-index', 0)),
                'width':     int(li.get('data-large-image-width', 0)),
                'height':    int(li.get('data-large-image-height', 0)),
                'url_xlsize': li.get('data-large-image-url'),
                'url_w920':   (img_el.get('src') or img_el.get('data-src')) if img_el else None,
                'url_80x60':  li.get('data-thumb-image-url'),
            })

    # Owner details
    owner_div = soup.find('div', class_='ClassifiedDetailOwnerDetails')
    if owner_div:
        owner_name = owner_div.find(class_='ClassifiedDetailOwnerDetails-title')
        result['owner_name'] = owner_name.get_text(strip=True) if owner_name else None

    return result
```

### 22.11 Using `ccapi/v4/` to Get Related Listings

```python
import requests

BASE = "https://www.njuskalo.hr"

def get_similar_listings(listing_id: int, limit: int = 12) -> list:
    """Get similar listings for a given listing ID via ccapi."""
    token = get_bearer_token()
    resp = requests.get(
        f"{BASE}/ccapi/v4/similar-classifieds",
        params={
            "filter[classifiedId]": listing_id,
            "page[limit]":          limit,
            "include":              "image.variation_360x360c,image.variations",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resolve_similar_ads(resp.json())


def get_recommended_listings(listing_id: int, limit: int = 12, offset: int = 0) -> list:
    """Get recommended listings for a given listing ID via ccapi."""
    token = get_bearer_token()
    resp = requests.get(
        f"{BASE}/ccapi/v4/ad-detail-view/recommended-ads",
        params={
            "filter[adId]":  listing_id,
            "page[limit]":   limit,
            "page[offset]":  offset,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    # Build image lookup
    img_lookup = {
        inc['id']: inc['attributes']['url']
        for inc in data.get('included', [])
        if inc['type'] == 'recommended-ads-images'
    }
    results = []
    for item in data.get('data', []):
        attrs = item['attributes']
        img_id = item.get('relationships', {}).get('adImage', {}).get('data', {}).get('id')
        results.append({
            'id':            item['id'],
            'title':         attrs['title'],
            'url':           attrs['url'],
            'price':         attrs['price'],
            'price_fmt':     attrs['formattedPrice'],
            'image_url':     img_lookup.get(img_id, ''),
        })
    return results
```

### 22.12 `ccapi/v4/` — Sibling Endpoints to Explore

The `/ccapi/v4/` prefix suggests a versioned REST API with more endpoints. Observed so far:

| Endpoint | Method | Description |
|---|---|---|
| `POST /oauth2/token` | POST | Get Bearer token |
| `GET /ccapi/v4/similar-classifieds` | GET | Similar listings for a given ID |
| `GET /ccapi/v4/ad-detail-view/recommended-ads` | GET | Recommended listings for a given ID |

Potential sibling endpoints to probe (not yet confirmed):
- `GET /ccapi/v4/classifieds/{id}` — full listing data as JSON
- `GET /ccapi/v4/classifieds?filter[categoryId]={id}` — listings by category
- `GET /ccapi/v4/classifieds?filter[userId]={id}` — listings by seller
- `GET /ccapi/v4/users/{id}` — seller profile
- `GET /ccapi/v4/classifieds/{id}/images` — listing images
- `GET /ccapi/v4/search?q={term}` — search

> **Recommended next step:** With a valid Bearer token, try `GET /ccapi/v4/classifieds/47225243` and similar patterns. If the API exposes full listing data as JSON, it would bypass the need to parse `__INITIAL_STATE__` entirely.
