#!/usr/bin/env python3
"""
PakSaleFinder — Daily Product Scraper
Fetches sale products from 15 Pakistani fashion brands via Shopify API
(+ custom scrapers for Nishat Linen and Sapphire) and updates
window.LIVE_PRODUCTS in index.html.

Run via GitHub Actions or manually:
  python scraper/update.py
"""

import html as html_mod
import json
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ──────────────────────────────────────────────
# LIMITS  (keep page size manageable)
# ──────────────────────────────────────────────
PER_BRAND_LIMIT = 150   # max products kept per brand (best discounts first)
TOTAL_LIMIT     = 1200  # absolute cap across all brands

# ──────────────────────────────────────────────
# BRAND CONFIGURATION
# ──────────────────────────────────────────────
BRANDS = [
    {
        "name": "Sana Safinaz",
        "base_url": "https://www.sanasafinaz.com",
        "is_featured": True,
    },
    {
        "name": "Asim Jofa",
        "base_url": "https://www.asimjofa.com",
        "is_featured": True,
    },
    {
        "name": "Baroque",
        "base_url": "https://www.baroque.pk",
        "is_featured": True,
    },
    {
        "name": "Limelight",
        "base_url": "https://limelight.pk",   # correct domain (limelightpk.com SSL broken)
        "is_featured": False,
    },
    {
        "name": "Generation",
        "base_url": "https://www.generation.com.pk",
        "is_featured": False,
    },
    {
        "name": "Alkaram",
        "base_url": "https://www.alkaramstudio.com",
        "is_featured": False,
    },
    # Zellbury does not set compare_at_price on Shopify — no sale detection possible
    # {
    #     "name": "Zellbury",
    #     "base_url": "https://www.zellbury.com",
    #     "is_featured": False,
    # },
    {
        "name": "Maria B",
        "base_url": "https://www.mariab.pk",
        "is_featured": True,
    },
    {
        "name": "Ego",
        "base_url": "https://wearego.com",
        "is_featured": False,
    },
    {
        "name": "Sahr Online",
        "base_url": "https://saharonline.pk",
        "is_featured": False,
    },
    {
        "name": "Malook",
        "base_url": "https://www.malook.pk",
        "is_featured": False,
    },
    {
        "name": "Elan",
        "base_url": "https://elan.pk",
        "is_featured": True,
    },
    {
        "name": "Kayseria",
        "base_url": "https://kayseriastore.com",
        "is_featured": False,
    },
    {
        "name": "Zara Shahjahan",
        "base_url": "https://www.zarashahjahan.com",
        "is_featured": False,
    },
    {
        "name": "Sania Maskatiya",
        "base_url": "https://www.saniamaskatiya.com",
        "is_featured": False,
    },

    # NOTE: Khaadi uses Salesforce Commerce Cloud — requires a custom
    # scraper (see KHAADI_CONFIG and scrape_khaadi below).

    # NOTE: Nishat Linen and Sapphire use custom scrapers (see below).
    # They are NOT in this list because they don't use the standard
    # Shopify compare_at_price flow.
]

# ──────────────────────────────────────────────
# CUSTOM BRAND CONFIGS (non-standard Shopify / non-Shopify)
# ──────────────────────────────────────────────
NISHAT_CONFIG = {
    "name": "Nishat Linen",
    "base_url": "https://nishatlinen.com",
    "is_featured": False,
    # Nishat's "Freedom to Buy" collections contain sale items.
    # Prices are per-meter/per-piece; discount % is stored as a tag (e.g. "18%").
    "sale_collections": [
        "freedom-to-buy",
    ],
}

KHAADI_CONFIG = {
    "name": "Khaadi",
    "base_url": "https://uk.khaadi.com",
    "is_featured": True,
    # Khaadi uses Salesforce Commerce Cloud (Demandware).
    # Product data is parsed from sale page HTML — product tiles contain
    # images, prices (GBP), discount badges, and product links.
    # pk.khaadi.com redirects to uk.khaadi.com so prices are in GBP;
    # we convert to PKR using an approximate exchange rate.
    "sale_paths": [
        "sale",
    ],
    "gbp_to_pkr": 370,  # approximate conversion rate
}

SAPPHIRE_CONFIG = {
    "name": "Sapphire",
    "base_url": "https://pk.sapphireonline.pk",
    "is_featured": True,
    # Sapphire uses Salesforce Commerce Cloud, not Shopify.
    # Product data is extracted from the GA4 dataLayer embedded in collection pages.
    "sale_collections": [
        "last-chance",
        "menswear-shop-by-category-sale",
    ],
}

# ──────────────────────────────────────────────
# CATEGORY / FABRIC / SEASON DETECTION
# ──────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "Lawn Suits": ["lawn", "unstitched", "3-piece", "3 piece", "collection"],
    "Kurtas": ["kurta", "kameez", "kurti"],
    "Dupattas": ["dupatta", "chunni"],
    "Bottoms": ["trouser", "palazzo", "pant", "shalwar"],
    "Dresses": ["dress", "frock", "maxi", "gown"],
    "Accessories": ["bag", "purse", "scarf", "jewel", "jewelry", "handbag"],
    "Pret Dresses": ["pret", "suit", "2-piece", "2 piece", "1-piece", "1 piece"],
}

FABRIC_KEYWORDS = {
    "Lawn": ["lawn"],
    "Chiffon": ["chiffon"],
    "Linen": ["linen"],
    "Cotton": ["cotton"],
    "Silk": ["silk", "karandi"],
    "Khaddar": ["khaddar", "khadar"],
    "Cambric": ["cambric"],
    "Organza": ["organza"],
    "Velvet": ["velvet"],
    "Net": ["net", "tissue"],
}

SEASON_KEYWORDS = {
    "spring":     ["spring", "lawn", "summer", "eid"],
    "winter":     ["winter", "khaddar", "khadar", "wool", "velvet", "shawl"],
    "season_end": ["clearance", "end of season", "end-of-season", "eoss", "sale", "final"],
}


def detect_category(title: str, tags: list) -> str:
    text = (title + " " + " ".join(tags)).lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return cat
    return "Pret Dresses"  # sensible default


def detect_fabric(title: str, tags: list) -> str:
    text = (title + " " + " ".join(tags)).lower()
    for fabric, keywords in FABRIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return fabric
    return "Lawn"  # default


def detect_season(title: str, tags: list) -> str:
    text = (title + " " + " ".join(tags)).lower()
    for season, keywords in SEASON_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return season
    return "spring"  # default


# ──────────────────────────────────────────────
# HTTP HELPER  (with optional SSL bypass)
# ──────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Build a lenient SSL context for stores with cert issues
_SSL_LENIENT = ssl.create_default_context()
_SSL_LENIENT.check_hostname = False
_SSL_LENIENT.verify_mode = ssl.CERT_NONE


def fetch_json(url: str, retries: int = 3, delay: float = 2.0, ssl_lenient: bool = False):
    """Fetch JSON from url with retries. Falls back to lenient SSL on cert errors."""
    ctx = _SSL_LENIENT if ssl_lenient else None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = delay * (attempt + 2)
                print(f"    Rate limited, waiting {wait}s …")
                time.sleep(wait)
            elif e.code in (404, 403):
                print(f"    HTTP {e.code} — skipping {url}")
                return None
            else:
                print(f"    HTTP {e.code} on attempt {attempt+1}: {url}")
                time.sleep(delay)
        except ssl.SSLError:
            if not ssl_lenient:
                print(f"    SSL error — retrying with lenient SSL …")
                return fetch_json(url, retries, delay, ssl_lenient=True)
            print(f"    SSL error (lenient) on attempt {attempt+1}")
            time.sleep(delay)
        except Exception as exc:
            # Try lenient SSL on first non-SSL connection error too
            if "SSL" in str(exc) and not ssl_lenient:
                return fetch_json(url, retries, delay, ssl_lenient=True)
            print(f"    Error on attempt {attempt+1}: {exc}")
            time.sleep(delay)
    return None


def fetch_html(url: str, retries: int = 3, delay: float = 2.0, ssl_lenient: bool = False) -> str | None:
    """Fetch raw HTML from url with retries.  Falls back to lenient SSL on cert errors."""
    ctx = _SSL_LENIENT if ssl_lenient else None
    headers = dict(HEADERS)
    headers["Accept"] = "text/html,application/xhtml+xml"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                return resp.read().decode("utf-8")
        except ssl.SSLError:
            if not ssl_lenient:
                print(f"    SSL error — retrying with lenient SSL …")
                return fetch_html(url, retries, delay, ssl_lenient=True)
            print(f"    SSL error (lenient) on attempt {attempt+1}")
            time.sleep(delay)
        except Exception as exc:
            if "SSL" in str(exc) and not ssl_lenient:
                return fetch_html(url, retries, delay, ssl_lenient=True)
            print(f"    HTML fetch error on attempt {attempt+1}: {exc}")
            time.sleep(delay)
    return None


# ──────────────────────────────────────────────
# SHOPIFY SCRAPER
# ──────────────────────────────────────────────
def scrape_brand(brand: dict, max_pages: int = 20) -> list:
    """Scrape sale products from a Shopify store."""
    base_url = brand["base_url"].rstrip("/")
    brand_name = brand["name"]
    products = []

    print(f"\n[{brand_name}] Scraping {base_url} …")

    page = 1
    while page <= max_pages:
        url = f"{base_url}/products.json?limit=250&page={page}"
        data = fetch_json(url)

        if not data or not data.get("products"):
            break

        raw_products = data["products"]
        print(f"  Page {page}: {len(raw_products)} products")

        for product in raw_products:
            # Check each variant for a sale
            for variant in product.get("variants", []):
                try:
                    price = float(variant.get("price", 0) or 0)
                    compare_at = float(variant.get("compare_at_price") or 0)
                except (ValueError, TypeError):
                    continue

                if compare_at > price > 0:
                    discount = round((compare_at - price) / compare_at * 100)

                    # Skip discounts under 5%
                    if discount < 5:
                        continue

                    # Sanity check: skip obviously corrupted compare_at_price data
                    # (e.g. Limelight stores PKR ~400k for shirts worth PKR 1,500)
                    # A genuine sale rarely exceeds 90% off; ratio > 10x is corrupt.
                    if discount > 90 or compare_at > price * 10:
                        continue

                    # Get best image
                    image_url = ""
                    images = product.get("images", [])
                    if images:
                        image_url = images[0].get("src", "")
                    elif variant.get("featured_image"):
                        image_url = variant["featured_image"].get("src", "")

                    if not image_url:
                        continue

                    title  = product.get("title", "").strip()
                    handle = product.get("handle", "")
                    tags   = [t.lower() for t in product.get("tags", [])]
                    avail  = variant.get("available", True)

                    products.append({
                        "brand":            brand_name,
                        "title":            title,
                        "image":            image_url,
                        "original_price":   int(round(compare_at)),
                        "sale_price":       int(round(price)),
                        "discount_percent": discount,
                        "category":         detect_category(title, tags),
                        "fabric":           detect_fabric(title, tags),
                        "season":           detect_season(title, tags),
                        "product_link":     f"{base_url}/products/{handle}",
                        "availability":     "in_stock" if avail else "out_of_stock",
                        "is_featured":      brand["is_featured"],
                        "currency":         "PKR",
                    })
                    # One entry per product (best variant already found)
                    break

        if len(raw_products) < 250:
            break

        page += 1
        time.sleep(0.8)  # polite delay

    # Keep only top PER_BRAND_LIMIT by discount percentage
    products.sort(key=lambda p: -p["discount_percent"])
    if len(products) > PER_BRAND_LIMIT:
        print(f"  Trimmed from {len(products)} → {PER_BRAND_LIMIT} (top discounts)")
        products = products[:PER_BRAND_LIMIT]

    print(f"  → {len(products)} sale products kept")
    return products


# ──────────────────────────────────────────────
# NISHAT LINEN SCRAPER  (Shopify, but no compare_at_price)
# ──────────────────────────────────────────────
def scrape_nishat(config: dict = NISHAT_CONFIG) -> list:
    """
    Scrape sale products from Nishat Linen.
    Nishat does not use compare_at_price.  Instead, sale items live in
    dedicated collections and the discount percentage is stored as a tag
    (e.g. "18%").  Prices are in Shopify's money format (8.80 → 880 PKR).
    For multi-piece products we sum the first-variant price per piece.
    """
    base_url = config["base_url"].rstrip("/")
    brand_name = config["name"]
    products = []

    print(f"\n[{brand_name}] Scraping {base_url} (custom) …")

    for collection in config["sale_collections"]:
        page = 1
        while page <= 10:
            url = f"{base_url}/collections/{collection}/products.json?limit=250&page={page}"
            data = fetch_json(url)

            if not data or not data.get("products"):
                break

            raw = data["products"]
            print(f"  {collection} page {page}: {len(raw)} products")

            for product in raw:
                tags = [t.strip().lower() for t in product.get("tags", [])]

                # Extract discount percentage from tags (e.g. "18%", "30%")
                discount = 0
                for tag in tags:
                    m = re.match(r"^(\d{1,2})%$", tag)
                    if m:
                        discount = int(m.group(1))
                        break
                if discount < 5:
                    continue

                # Calculate total price from the first variant of each piece
                # Nishat prices are in Shopify money format — multiply by 100
                variants = product.get("variants", [])
                if not variants:
                    continue

                # For single-piece items, take the first variant price.
                # For multi-piece, sum the first variant of each option group.
                seen_options = set()
                total_price = 0.0
                for v in variants:
                    opt1 = v.get("option1", "")
                    if opt1 not in seen_options:
                        seen_options.add(opt1)
                        try:
                            total_price += float(v.get("price", 0) or 0)
                        except (ValueError, TypeError):
                            pass

                # Convert from Shopify money format to PKR
                sale_price = int(round(total_price * 100))
                if sale_price <= 0:
                    continue

                # Derive original price from discount
                original_price = int(round(sale_price / (1 - discount / 100)))

                # Get image
                images = product.get("images", [])
                image_url = images[0].get("src", "") if images else ""
                if not image_url:
                    continue

                title  = product.get("title", "").strip()
                handle = product.get("handle", "")

                products.append({
                    "brand":            brand_name,
                    "title":            title,
                    "image":            image_url,
                    "original_price":   original_price,
                    "sale_price":       sale_price,
                    "discount_percent": discount,
                    "category":         detect_category(title, tags),
                    "fabric":           detect_fabric(title, tags),
                    "season":           detect_season(title, tags),
                    "product_link":     f"{base_url}/products/{handle}",
                    "availability":     "in_stock",
                    "is_featured":      config["is_featured"],
                    "currency":         "PKR",
                })

            if len(raw) < 250:
                break
            page += 1
            time.sleep(0.8)

    # Keep top PER_BRAND_LIMIT by discount
    products.sort(key=lambda p: -p["discount_percent"])
    if len(products) > PER_BRAND_LIMIT:
        print(f"  Trimmed from {len(products)} → {PER_BRAND_LIMIT}")
        products = products[:PER_BRAND_LIMIT]

    print(f"  → {len(products)} sale products kept")
    return products


# ──────────────────────────────────────────────
# SAPPHIRE SCRAPER  (Salesforce Commerce Cloud)
# ──────────────────────────────────────────────
def scrape_sapphire(config: dict = SAPPHIRE_CONFIG) -> list:
    """
    Scrape sale products from Sapphire (pk.sapphireonline.pk).
    Sapphire runs on Salesforce Commerce Cloud.  Product data is extracted
    from the GA4 dataLayer embedded in each collection page, and images/links
    are parsed from the surrounding HTML.
    """
    base_url = config["base_url"].rstrip("/")
    brand_name = config["name"]
    products = []

    print(f"\n[{brand_name}] Scraping {base_url} (custom) …")

    for collection in config["sale_collections"]:
        start = 0
        page_size = 60          # Sapphire uses sz= param
        max_pages = 5           # safety limit

        for page_num in range(max_pages):
            url = f"{base_url}/collections/{collection}?sz={page_size}&start={start}"
            html = fetch_html(url)
            if not html:
                break

            # ── Extract product data from GA4 dataLayer ──
            match = re.search(
                r"ga4DataLayerEvent\s*=\s*(\{.*?\});", html, re.DOTALL
            )
            if not match:
                print(f"  {collection}: no GA4 data found")
                break

            try:
                ga4 = json.loads(match.group(1))
            except json.JSONDecodeError:
                print(f"  {collection}: GA4 JSON parse error")
                break

            items = ga4.get("ecommerce", {}).get("items", [])
            if not items:
                break

            print(f"  {collection} (start={start}): {len(items)} products")

            # ── Extract product links from HTML ──
            link_map = {}   # product_id → link path
            for lid, lpath in re.findall(
                r'href="(/collections/[^"]+/products/([A-Z0-9_]+)\.html)', html
            ):
                pid = lpath  # e.g. WBTM24V60046_999
                if pid not in link_map:
                    link_map[pid] = lid

            # ── Extract product images from HTML ──
            image_list = re.findall(
                r'data-src="(https://pk\.sapphireonline\.pk/dw/image/[^"]+)"', html
            )
            if not image_list:
                image_list = re.findall(
                    r'src="(https://pk\.sapphireonline\.pk/dw/image/[^"]+)"', html
                )
            # Unescape HTML entities in URLs
            image_list = [html_mod.unescape(u) for u in image_list]

            for idx, item in enumerate(items):
                try:
                    price = float(item.get("price", 0) or 0)
                    compare = float(item.get("compare_price", 0) or 0)
                except (ValueError, TypeError):
                    continue

                if price <= 0:
                    continue

                # Only include if there's an actual discount
                if compare > price:
                    discount = round((compare - price) / compare * 100)
                else:
                    # No discount — skip
                    continue

                if discount < 5 or discount > 90:
                    continue

                item_id   = item.get("item_id", "")
                title     = item.get("item_name", "").strip()
                category1 = item.get("item_category", "")
                tags      = [category1.lower()] if category1 else []

                # Build product link
                link_path = link_map.get(item_id, f"/collections/{collection}/products/{item_id}.html")
                product_link = f"{base_url}{link_path}"

                # Get image (matched by position)
                image_url = image_list[idx] if idx < len(image_list) else ""
                if not image_url:
                    continue

                products.append({
                    "brand":            brand_name,
                    "title":            title,
                    "image":            image_url,
                    "original_price":   int(round(compare)),
                    "sale_price":       int(round(price)),
                    "discount_percent": discount,
                    "category":         detect_category(title, tags),
                    "fabric":           detect_fabric(title, tags),
                    "season":           detect_season(title, tags),
                    "product_link":     product_link,
                    "availability":     "in_stock",
                    "is_featured":      config["is_featured"],
                    "currency":         "PKR",
                })

            # Sapphire pages are small; stop if we got fewer items than page size
            if len(items) < page_size:
                break
            start += page_size
            time.sleep(1.0)

    # Keep top PER_BRAND_LIMIT by discount
    products.sort(key=lambda p: -p["discount_percent"])
    if len(products) > PER_BRAND_LIMIT:
        print(f"  Trimmed from {len(products)} → {PER_BRAND_LIMIT}")
        products = products[:PER_BRAND_LIMIT]

    print(f"  → {len(products)} sale products kept")
    return products


# ──────────────────────────────────────────────
# KHAADI SCRAPER  (Salesforce Commerce Cloud / Demandware)
# ──────────────────────────────────────────────
def scrape_khaadi(config: dict = KHAADI_CONFIG) -> list:
    """
    Scrape sale products from Khaadi (uk.khaadi.com).
    Khaadi runs on Salesforce Commerce Cloud.  pk.khaadi.com redirects to
    uk.khaadi.com, so prices are in GBP.  We convert to PKR using an
    approximate exchange rate.

    Product data is extracted from the HTML product tiles which contain:
      - data-productid attribute (SKU)
      - tile-image src + alt text (image, fabric, category info)
      - GBP prices (original and sale)
      - product-sale-label badge (discount %)
      - product link href
    """
    base_url = config["base_url"].rstrip("/")
    brand_name = config["name"]
    gbp_to_pkr = config.get("gbp_to_pkr", 370)
    products = []
    seen_ids = set()

    print(f"\n[{brand_name}] Scraping {base_url} (custom) …")

    for sale_path in config["sale_paths"]:
        start = 0
        page_size = 60
        max_pages = 25  # safety limit — Khaadi has ~1,300 sale items

        for page_num in range(max_pages):
            url = f"{base_url}/{sale_path}/?sz={page_size}&start={start}"
            html = fetch_html(url)
            if not html:
                break

            # ── Extract product tiles ──
            tiles = re.findall(
                r'<div\s+class="product-tile"[^>]*data-productid="([^"]+)"[^>]*>',
                html,
            )
            if not tiles:
                print(f"  {sale_path} (start={start}): no product tiles found")
                break

            print(f"  {sale_path} (start={start}): {len(tiles)} product tiles")

            # ── Extract GA4 data attributes (most reliable source) ──
            ga4_entries = re.findall(r'data-gtmga4data="([^"]+)"', html)

            # ── Extract images: tile-image src with alt text (1 per tile) ──
            image_entries = re.findall(
                r'<img[^>]*class="tile-image[^"]*"[^>]*'
                r'src="([^"]+)"[^>]*alt="([^"]*)"',
                html,
            )

            # ── Extract product links ──
            link_entries = re.findall(
                r'href="(/[a-z][a-z0-9\-]*/[A-Z0-9_\-]+\.html)',
                html,
            )

            # ── Extract discount badges ──
            discount_badges = re.findall(
                r'<span\s+class="product-sale-label"[^>]*>(\d+)%\s*OFF</span>',
                html, re.IGNORECASE,
            )

            # Build a de-duplicated link map for product IDs
            link_map = {}
            for lpath in link_entries:
                pid_match = re.search(r'/([A-Z0-9_\-]+)\.html', lpath)
                if pid_match:
                    pid = pid_match.group(1)
                    if pid not in link_map:
                        link_map[pid] = lpath

            # Build image map: 1 tile-image per product tile
            image_map = {}  # index → (url, alt)
            for img_idx, (img_url, img_alt) in enumerate(image_entries):
                image_map[img_idx] = (
                    html_mod.unescape(img_url),
                    html_mod.unescape(img_alt),
                )

            # Parse GA4 data for sale prices
            ga4_map = {}  # product_id → price
            for ga4_raw in ga4_entries:
                try:
                    ga4_obj = json.loads(html_mod.unescape(ga4_raw))
                    pid = ga4_obj.get("item_id", "")
                    price = float(ga4_obj.get("price", 0) or 0)
                    if pid and price > 0:
                        ga4_map[pid] = price
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

            for idx, product_id in enumerate(tiles):
                if product_id in seen_ids:
                    continue
                seen_ids.add(product_id)

                # Get image and alt text
                img_data = image_map.get(idx)
                if not img_data:
                    continue
                image_url, alt_text = img_data

                if not image_url:
                    continue

                # Parse alt text for title/fabric info
                # Format: "Embroidered | Karandi | Kurta | GBP 7.50"
                alt_parts = [p.strip() for p in alt_text.split("|")]
                # Remove the GBP price part from the end
                alt_clean = [p for p in alt_parts if "GBP" not in p]
                title = alt_clean[-1] if alt_clean else product_id
                title = title.strip()
                if not title:
                    title = product_id

                # Get sale price from GA4 data (most reliable)
                sale_gbp = ga4_map.get(product_id, 0)

                # Get discount from badge
                if idx < len(discount_badges):
                    discount = int(discount_badges[idx])
                else:
                    continue  # skip if no discount badge

                if discount < 5 or discount > 95:
                    continue

                # Calculate original price from sale price and discount
                if sale_gbp > 0:
                    orig_gbp = sale_gbp / (1 - discount / 100)
                else:
                    # Fallback: try to extract from alt text
                    price_match = re.search(r'GBP\s*([\d,.]+)', alt_text)
                    if price_match:
                        sale_gbp = float(price_match.group(1).replace(",", ""))
                        orig_gbp = sale_gbp / (1 - discount / 100)
                    else:
                        continue

                if sale_gbp <= 0:
                    continue

                # Convert GBP to PKR
                sale_pkr = int(round(sale_gbp * gbp_to_pkr))
                orig_pkr = int(round(orig_gbp * gbp_to_pkr))

                # Build product link
                link_path = link_map.get(product_id, f"/{sale_path}/{product_id}.html")
                product_link = f"{base_url}{link_path}"

                # Build tags from alt text parts for category/fabric detection
                tags = [p.lower() for p in alt_clean]

                display_title = " | ".join(alt_clean) if len(alt_clean) > 1 else title

                products.append({
                    "brand":            brand_name,
                    "title":            display_title,
                    "image":            image_url,
                    "original_price":   orig_pkr,
                    "sale_price":       sale_pkr,
                    "discount_percent": discount,
                    "category":         detect_category(title, tags),
                    "fabric":           detect_fabric(title, tags),
                    "season":           detect_season(title, tags),
                    "product_link":     product_link,
                    "availability":     "in_stock",
                    "is_featured":      config["is_featured"],
                    "currency":         "PKR",
                })

            # Stop if very few tiles (Khaadi sometimes returns slightly fewer
            # than page_size even on non-last pages, so only stop on truly empty)
            if len(tiles) < page_size // 2:
                break
            start += page_size
            time.sleep(1.0)

    # Keep top PER_BRAND_LIMIT by discount
    products.sort(key=lambda p: -p["discount_percent"])
    if len(products) > PER_BRAND_LIMIT:
        print(f"  Trimmed from {len(products)} → {PER_BRAND_LIMIT}")
        products = products[:PER_BRAND_LIMIT]

    print(f"  → {len(products)} sale products kept")
    return products


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    now_utc = datetime.now(timezone.utc)
    print("=" * 60)
    print(f"PakSaleFinder Scraper — {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    all_products  = []
    failed_brands = []
    brands_ok     = []

    for brand in BRANDS:
        try:
            products = scrape_brand(brand)
            all_products.extend(products)
            brands_ok.append(brand["name"])
        except Exception as exc:
            print(f"  ERROR scraping {brand['name']}: {exc}")
            failed_brands.append(brand["name"])

    # ── Custom scrapers ──
    custom_scrapers = [
        (NISHAT_CONFIG["name"],   lambda: scrape_nishat(NISHAT_CONFIG)),
        (SAPPHIRE_CONFIG["name"], lambda: scrape_sapphire(SAPPHIRE_CONFIG)),
        (KHAADI_CONFIG["name"],   lambda: scrape_khaadi(KHAADI_CONFIG)),
    ]
    for brand_name, scraper_fn in custom_scrapers:
        try:
            products = scraper_fn()
            all_products.extend(products)
            brands_ok.append(brand_name)
        except Exception as exc:
            print(f"  ERROR scraping {brand_name}: {exc}")
            failed_brands.append(brand_name)

    if not all_products:
        print("\nNo products found — aborting to preserve existing data.")
        sys.exit(1)

    # Global sort: featured brands first, then by discount %
    all_products.sort(key=lambda p: (-int(p["is_featured"]), -p["discount_percent"]))

    # Global cap
    if len(all_products) > TOTAL_LIMIT:
        print(f"\nTotal trimmed from {len(all_products)} → {TOTAL_LIMIT}")
        all_products = all_products[:TOTAL_LIMIT]

    # Assign stable IDs
    for i, p in enumerate(all_products, 1):
        p["id"] = i

    total = len(all_products)
    print(f"\nFinal product count: {total}")
    print(f"Brands scraped: {', '.join(brands_ok)}")
    if failed_brands:
        print(f"Failed brands:  {', '.join(failed_brands)}")

    # ── Update index.html ──
    index_path = "index.html"
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"\nERROR: {index_path} not found. Run from repo root.")
        sys.exit(1)

    # ── Patch window.LIVE_PRODUCTS ──
    products_json = json.dumps(all_products, ensure_ascii=False, separators=(",", ":"))
    new_products_line = f"window.LIVE_PRODUCTS = {products_json};"

    pattern_products = r"window\.LIVE_PRODUCTS\s*=\s*\[.*?\];"
    updated_html, count = re.subn(
        pattern_products, new_products_line, html, flags=re.DOTALL
    )
    if count == 0:
        print("\nERROR: Could not find window.LIVE_PRODUCTS in index.html")
        sys.exit(1)

    # ── Patch window.LIVE_META ──
    pk_months = ["", "January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
    pk_date = f"{now_utc.day} {pk_months[now_utc.month]} {now_utc.year}"
    meta = {
        "last_updated":    now_utc.isoformat(),
        "last_updated_pk": pk_date,
        "total_products":  total,
        "brands_scraped":  brands_ok,
        "season_summary":  {},
    }
    new_meta_line = f"window.LIVE_META = {json.dumps(meta, ensure_ascii=False, separators=(',', ':'))};"
    pattern_meta  = r"window\.LIVE_META\s*=\s*\{.*?\};"
    updated_html, _ = re.subn(pattern_meta, new_meta_line, updated_html, flags=re.DOTALL)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(updated_html)

    print(f"\n✓ index.html updated with {total} products")
    print(f"✓ LIVE_META updated — {pk_date}")
    print(f"✓ Scraper finished at {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
