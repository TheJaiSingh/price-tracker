"""
scraper.py
-----------
Amazon aur Flipkart product page se naam, image aur price nikalta hai.

Cloud servers (jaise Railway) ko Amazon/Flipkart aksar block karte hain. Isliye:
1. SCRAPER_API_KEY env variable set ho to request ScraperAPI ke through jaati hai (reliable).
2. Warna seedha try hota hai.
3. Price na mile to bhi asli NAME (page ya URL se) aur IMAGE (Amazon ASIN se) use hota hai.
   Sirf price demo mode mein thoda hilta hai.
"""

import os
import re
import json
import random
from urllib.parse import urlparse, unquote, parse_qs

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


def site_of(url: str) -> str:
    host = urlparse(url if url.lower().startswith("http") else "https://" + url).netloc.lower()
    return "flipkart" if ("flipkart" in host or "fkrt" in host) else "amazon"


def clean_url(url: str) -> str:
    """Tracking hata ke saaf link banata hai."""
    url = url.strip()
    if not url.lower().startswith("http"):
        url = "https://" + url.lstrip("/")
    parsed = urlparse(url)
    if site_of(url) == "flipkart":
        pid = parse_qs(parsed.query).get("pid", [None])[0]
        return f"https://{parsed.netloc}{parsed.path}" + (f"?pid={pid}" if pid else "")
    m = ASIN_RE.search(url)
    if m and "amazon" in parsed.netloc:
        return f"https://{parsed.netloc}/dp/{m.group(1).upper()}"
    return url


def get_asin(url: str):
    m = ASIN_RE.search(url)
    return m.group(1).upper() if m else None


def name_from_url(url: str):
    """Link ke slug se naam. Amazon: .../Name-Here/dp/ASIN  |  Flipkart: /name-here/p/itm..."""
    parts = [p for p in unquote(urlparse(url).path).split("/") if p]
    marker = "p" if site_of(url) == "flipkart" else "dp"
    for i, p in enumerate(parts):
        if p.lower() == marker and i > 0:
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


def _find_product(node):
    """JSON-LD ke andar Product object dhundta hai."""
    if isinstance(node, list):
        for x in node:
            r = _find_product(x)
            if r:
                return r
    elif isinstance(node, dict):
        t = node.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return node
        for v in node.values():
            if isinstance(v, (list, dict)):
                r = _find_product(v)
                if r:
                    return r
    return None


def _jsonld(soup):
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            prod = _find_product(json.loads(tag.string or ""))
        except Exception:
            continue
        if not prod:
            continue
        img = prod.get("image")
        img = img[0] if isinstance(img, list) and img else img
        offers = prod.get("offers")
        offers = offers[0] if isinstance(offers, list) and offers else offers
        price = None
        if isinstance(offers, dict):
            price = _to_price(str(offers.get("price") or offers.get("lowPrice") or ""))
        return price, prod.get("name"), (img if isinstance(img, str) else None)
    return None, None, None


def _parse(html: str):
    low = html.lower()
    if "enter the characters you see below" in low or "api-services-support@amazon.com" in low:
        raise ValueError("Bot check (captcha)")
    soup = BeautifulSoup(html, "html.parser")

    name = None
    for sel in ("#productTitle", "span.VU-ZEz", "span.B_NuCI"):
        t = soup.select_one(sel)
        if t and t.get_text(strip=True):
            name = t.get_text(strip=True)
            break

    image = None
    img = soup.find("img", {"id": "landingImage"})
    if img:
        image = img.get("data-old-hires") or img.get("src")
    if not image:
        for sel in ("img.DByuf4", "img._396cs4"):
            t = soup.select_one(sel)
            if t and t.get("src"):
                image = t["src"]
                break

    price = None
    for sel in (".a-price .a-offscreen", "span.a-price-whole", "#priceblock_ourprice",
                "#priceblock_dealprice", "div.Nx9bqj", "div._30jeq3"):
        tag = soup.select_one(sel)
        if tag:
            price = _to_price(tag.get_text())
            if price:
                break

    # JSON-LD / og tags se khali jagah bharo (dono sites ke liye)
    lp, ln, li = _jsonld(soup)
    price = price or lp
    name = name or ln
    image = image or li
    if not name:
        og = soup.find("meta", {"property": "og:title"})
        name = og["content"].strip() if og and og.get("content") else None
    if not image:
        og = soup.find("meta", {"property": "og:image"})
        image = og["content"] if og and og.get("content") else None
    return price, name, image


def fetch_product(url: str, previous_price: float = None) -> dict:
    """
    Returns: {"price", "name", "image", "url", "real", "site"}
    real=True matlab price asli page se mila.
    """
    cleaned = clean_url(url)
    site = site_of(cleaned)
    asin = get_asin(cleaned)
    price = name = image = None
    try:
        price, name, image = _parse(_get_html(cleaned))
    except Exception as e:
        print(f"[scraper] Real scraping failed ({e})")

    real = price is not None
    if not name:
        name = name_from_url(url) or (f"Amazon product {asin}" if asin else f"{site.title()} product")
    if not image and asin:
        image = f"https://m.media-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg"
    if not price:
        print("[scraper] Using demo price")
        price = (round(previous_price * random.uniform(0.96, 1.01), 2)
                 if previous_price else round(random.uniform(999, 15000), 2))
    return {"price": price, "name": name, "image": image or "", "url": cleaned, "real": real, "site": site}


def get_amazon_price(product_url: str):
    """Purana format (price, name, image) - compatibility ke liye."""
    d = fetch_product(product_url)
    return d["price"], d["name"], d["image"]
