#!/usr/bin/env python3
"""
PakSaleFinder — Daily Product Scraper
Fetches sale products from 7 Pakistani fashion brands via Shopify API
and updates window.LIVE_PRODUCTS in index.html.

Run via GitHub Actions or manually:
  python scraper/update.py
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

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
        "base_url": "https://limelightpk.com",
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
    {
        "name": "Zellbury",
        "base_url": "https://www.zellbury.com",
        "is_featured": False,
    },
]

# ──────────────────────────────────────────────
# CATEGORY / FABRIC / SEASON DETECTION
# ──────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "Lawn Suits": ["lawn", "unstitched", "3-piece", "3 piece", "suit", "collection"],
    "Kurtas": ["kurta", "kameez", "kurti"],
    "Dupattas": ["dupatta", "chunni"],
    "Bottoms": ["trouser", "palazzo", "pant", "shalwar"],
    "Dresses": ["dress", "frock", "maxi", "gown"],
    "Accessories": ["bag", "purse", "scarf", "jewel", "jewelry", "handbag"],
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
    "spring": ["spring", "lawn", "summer", "eid"],
    "winter": ["winter", "khaddar", "khadar", "wool", "velvet", "shawl", "warmth"],
    "autumn": ["autumn", "fall"],
}


def detect_category(title: str, tags: list) -> str:
    text = (title + " " + " ".join(tags)).lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return cat
    return "Lawn Suits"  # default


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
# HTTP HELPER
# ──────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PakSaleFinder/1.0; +https://paksalefinder.com)"
    ),
    "Accept": "application/json",
}


def fetch_json(url: str, retries: int = 3, delay: float = 2.0):
    """Fetch JSON from url with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
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
        except Exception as exc:
            print(f"    Error on attempt {attempt+1}: {exc}")
            time.sleep(delay)
    return None


# ──────────────────────────────────────────────
# SHOPIFY SCRAPER
# ──────────────────────────────────────────────
def scrape_brand(brand: dict, max_pages: int = 10) -> list:
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
        print(f"  Page {page}: {len(raw_products)} products fetched")

        for product in raw_products:
            # Check each variant for a sale
            for variant in product.get("variants", []):
                try:
                    price = float(variant.get("price", 0) or 0)
                    compare_at = float(variant.get("compare_at_price") or 0)
                except (ValueError, TypeError):
                    continue

                if compare_at > price > 0:
                    # It's on sale — build our product object
                    discount = round((compare_at - price) / compare_at * 100)

                    # Skip tiny discounts (< 5%)
                    if discount < 5:
                        continue

                    # Get best image
                    image_url = ""
                    images = product.get("images", [])
                    if images:
                        image_url = images[0].get("src", "")
                    elif variant.get("featured_image"):
                        image_url = variant["featured_image"].get("src", "")

                    # Skip if no image
                    if not image_url:
                        continue

                    title = product.get("title", "").strip()
                    handle = product.get("handle", "")
                    tags = [t.lower() for t in product.get("tags", [])]
                    available = variant.get("available", True)

                    products.append({
                        "brand": brand_name,
                        "title": title,
                        "image": image_url,
                        "original_price": int(round(compare_at)),
                        "sale_price": int(round(price)),
                        "discount_percent": discount,
                        "category": detect_category(title, tags),
                        "fabric": detect_fabric(title, tags),
                        "season": detect_season(title, tags),
                        "product_link": f"{base_url}/products/{handle}",
                        "availability": "in_stock" if available else "out_of_stock",
                        "is_featured": brand["is_featured"],
                        "currency": "PKR",
                    })
                    # Only take first sale variant per product
                    break

        # Check if there are more pages
        if len(raw_products) < 250:
            break

        page += 1
        time.sleep(1.0)  # polite delay between pages

    print(f"  → {len(products)} sale products found")
    return products


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"PakSaleFinder Scraper — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    all_products = []
    failed_brands = []

    for brand in BRANDS:
        try:
            products = scrape_brand(brand)
            all_products.extend(products)
        except Exception as exc:
            print(f"  ERROR scraping {brand['name']}: {exc}")
            failed_brands.append(brand["name"])

    if not all_products:
        print("\nNo products found — aborting to preserve existing data.")
        sys.exit(1)

    # Sort: featured first, then by discount descending
    all_products.sort(key=lambda p: (-int(p["is_featured"]), -p["discount_percent"]))

    # Assign stable IDs
    for i, p in enumerate(all_products, 1):
        p["id"] = i

    print(f"\nTotal sale products: {len(all_products)}")
    if failed_brands:
        print(f"Failed brands (kept old data): {', '.join(failed_brands)}")

    # ── Update index.html ──
    index_path = "index.html"
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"\nERROR: {index_path} not found. Run from repo root.")
        sys.exit(1)

    products_json = json.dumps(all_products, ensure_ascii=False, separators=(",", ":"))
    new_line = f"        window.LIVE_PRODUCTS = {products_json};"

    # Replace the existing LIVE_PRODUCTS assignment
    pattern = r"        window\.LIVE_PRODUCTS\s*=\s*\[.*?\];"
    updated_html, count = re.subn(pattern, new_line, html, flags=re.DOTALL)

    if count == 0:
        print("\nERROR: Could not find window.LIVE_PRODUCTS in index.html")
        print("Make sure the scraper is run from the repo root directory.")
        sys.exit(1)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(updated_html)

    print(f"\n✓ index.html updated with {len(all_products)} products")
    print(f"✓ Scraper finished at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
