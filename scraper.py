"""
scraper.py
-----------
Amazon product page se REAL name, image aur price nikalta hai.

Amazon cloud servers (jaise Railway) ko aksar block karta hai. Isliye:
1. Agar SCRAPER_API_KEY env variable set hai, to request ScraperAPI ke
   through jaati hai (reliable tareeka).
2. Warna seedha try karta hai.
3. Price na mile to bhi real NAME (page se ya URL se) aur IMAGE (ASIN se)
   use hota hai. Sirf price demo mode mein thoda hilta hai.
"""

import os
import re
import random
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.google.com/",
}

ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.I)


def clean_url(url: str) -> str:
    """Lamba tracking wala link -> https://www.amazon.in/dp/ASIN"""
    url = url.strip()
    if not url.lower().startswith("http"):
        url = "https://" + url.lstrip("/")
    m = ASIN_RE.search(url)
    host = urlparse(url).netloc
    if m and "amazon" in host:
        return f"https://{host}/dp/{m.group(1).upper()}"
    return url


def get_asin(url: str):
    m = ASIN_RE.search(url)
    return m.group(1).upper() if m else None


def name_from_url(url: str):
    """Link ke slug se naam: .../Samsung-A36-Dark-Blue-128/dp/B0... -> 'Samsung A36 Dark Blue 128'"""
    parts = [p for p in unquote(urlparse(url).path).split("/") if p]
    for i, p in enumerate(parts):
        if p.lower() == "dp" and i > 0:
            slug = parts[i - 1]
            if slug.lower() not in ("gp", "product") and not re.fullmatch(r"[A-Z0-9]{10}", slug):
                return slug.replace("-", " ").strip()
    return None


def _to_price(text):
    m = re.search(r"[\d,]+(?:\.\d+)?", text or "")
    return float(m.group().replace(",", "")) if m else None


def _get_html(url: str) -> str:
    if SCRAPER_API_KEY:
        r = requests.get(
            "https://api.scraperapi.com/",
            params={"api_key": SCRAPER_API_KEY, "url": url, "country_code": "in"},
            timeout=60,
        )
    else:
        r = requests.get(url, headers=HEADERS, timeout=10)
    return r.text


def _parse(html: str):
    low = html.lower()
    if "enter the characters you see below" in low or "api-services-support@amazon.com" in low:
        raise ValueError("Amazon bot check (captcha)")
    soup = BeautifulSoup(html, "html.parser")

    # NAME
    name = None
    t = soup.find(id="productTitle")
    if t:
        name = t.get_text(strip=True)
    if not name:
        og = soup.find("meta", {"property": "og:title"})
        if og and og.get("content"):
            name = og["content"].strip()

    # IMAGE
    image = None
    img = soup.find("img", {"id": "landingImage"})
    if img:
        image = img.get("data-old-hires") or img.get("src")
    if not image:
        og = soup.find("meta", {"property": "og:image"})
        if og and og.get("content"):
            image = og["content"]

    # PRICE
    price = None
    for sel in (".a-price .a-offscreen", "span.a-price-whole",
                "#priceblock_ourprice", "#priceblock_dealprice"):
        tag = soup.select_one(sel)
        if tag:
            price = _to_price(tag.get_text())
            if price:
                break
    return price, name, image


def fetch_product(url: str, previous_price: float = None) -> dict:
    """
    Returns: {"price", "name", "image", "url", "real"}
    real=True matlab price asli Amazon page se mila.
    """
    cleaned = clean_url(url)
    asin = get_asin(cleaned)
    price = name = image = None
    try:
        price, name, image = _parse(_get_html(cleaned))
    except Exception as e:
        print(f"[scraper] Real scraping failed ({e})")

    real = price is not None
    if not name:
        name = name_from_url(url) or (f"Amazon product {asin}" if asin else "Amazon product")
    if not image and asin:
        image = f"https://m.media-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg"
    if not price:
        print("[scraper] Using demo price")
        price = (round(previous_price * random.uniform(0.96, 1.01), 2)
                 if previous_price else round(random.uniform(999, 15000), 2))
    return {"price": price, "name": name, "image": image or "", "url": cleaned, "real": real}


def get_amazon_price(product_url: str):
    """Purana format (price, name, image) - compatibility ke liye."""
    d = fetch_product(product_url)
    return d["price"], d["name"], d["image"]
