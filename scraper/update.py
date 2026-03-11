#!/usr/bin/env python3
"""
PakSaleFinder — Daily Product Scraper
Fetches sale products from 13 Pakistani fashion brands via Shopify API
and updates window.LIVE_PRODUCTS in index.html.

Run via GitHub Actions or manually:
  python scraper/update.py
"""

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
    # NOTE: Khaadi (khaadi.com) does not use Shopify — requires a custom
    # scraper (Magento/custom platform). Skipped until custom support is added.
]

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
