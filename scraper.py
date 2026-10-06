"""
scraper.py
-----------
Amazon product page se price, naam, aur IMAGE nikalta hai.

Agar real scraping fail ho jaye (Amazon block kare), to fallback
data use hota hai - taaki demo hamesha kaam kare.
"""

import requests
from bs4 import BeautifulSoup
import random

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Agar scraping fail ho to demo ke liye ek placeholder product image
FALLBACK_IMAGE = "https://via.placeholder.com/300x300.png?text=Product+Image"


def get_amazon_price(product_url: str):
    """
    Returns: (price: float, name: str, image_url: str)
    """
    try:
        response = requests.get(product_url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(response.content, "html.parser")

        price_tag = soup.find("span", {"class": "a-price-whole"})
        name_tag = soup.find("span", {"id": "productTitle"})

        # Product image - Amazon mein usually id="landingImage" wali img tag mein hoti hai
        image_tag = soup.find("img", {"id": "landingImage"})
        if not image_tag:
            # fallback: Open Graph meta tag try karo (zyada reliable kabhi kabhi)
            og_image = soup.find("meta", {"property": "og:image"})
            image_url = og_image["content"] if og_image else None
        else:
            image_url = image_tag.get("src") or image_tag.get("data-old-hires")

        if price_tag and name_tag:
            price_text = price_tag.get_text().replace(",", "").replace(".", "").strip()
            price = float(price_text)
            name = name_tag.get_text().strip()
            image = image_url if image_url else FALLBACK_IMAGE
            return price, name, image

        raise ValueError("Price tag not found")

    except Exception as e:
        print(f"[scraper] Real scraping failed ({e}), using fallback mock data.")
        mock_price = round(random.uniform(999, 15000), 2)
        mock_name = "Sample Tracked Product"
        return mock_price, mock_name, FALLBACK_IMAGE
