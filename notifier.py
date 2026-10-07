"""
notifier.py
------------
Price target hit hone par HTML email (product image ke sath) bhejta hai.
Ab Gmail SMTP ki jagah Brevo ki HTTPS API use hoti hai, kyunki Railway
SMTP ports (465/587) block karta hai.

Env variables (Railway -> Variables):
    BREVO_API_KEY  - Brevo dashboard -> SMTP & API -> API keys
    SENDER_EMAIL   - wahi email jo Brevo mein "Senders" mein verified hai
"""

import os
import requests

BREVO_API_KEY = os.environ.get("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")
SENDER_EMAIL = os.environ.get("sjai4247@gmail.com")
SENDER_NAME = "PriceWatch"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def send_price_alert(product_name: str, current_price: float, target_price: float,
                     product_url: str, receiver_email: str, image_url: str = None):
    if not BREVO_API_KEY or not SENDER_EMAIL:
        print("[notifier] Missing BREVO_API_KEY or SENDER_EMAIL env variable")
        return False

    subject = f"🎯 Price Drop Alert: {product_name}"

    image_html = (
        f'<img src="{image_url}" width="200" style="border-radius:8px; margin-bottom:16px;">'
        if image_url else ""
    )

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color:#20261C;">
      <div style="max-width:420px; margin:auto; padding:24px; border:1px solid #eee; border-radius:12px;">
        <p style="font-size:13px; letter-spacing:1px; color:#D2481E; font-weight:bold;">PRICE DROP ALERT</p>
        {image_html}
        <h2 style="margin:0 0 10px;">{product_name}</h2>
        <p style="color:#5B6156;">Your target price has been reached!</p>
        <table style="margin:16px 0;">
          <tr><td style="color:#5B6156; padding-right:10px;">Current Price:</td>
              <td style="font-weight:bold; font-size:20px; color:#3E8E5C;">₹{current_price}</td></tr>
          <tr><td style="color:#5B6156; padding-right:10px;">Your Target:</td>
              <td>₹{target_price}</td></tr>
        </table>
        <a href="{product_url}" style="display:inline-block; background:#20261C; color:#fff; padding:12px 24px; border-radius:8px; text-decoration:none;">Buy Now on Amazon</a>
        <p style="margin-top:24px; font-size:12px; color:#999;">— PriceWatch (Amazon Price Tracker)</p>
      </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": receiver_email}],
        "subject": subject,
        "htmlContent": html_body,
    }
    headers = {
        "api-key": BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }

    try:
        resp = requests.post(BREVO_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201, 202):
            print(f"[notifier] Email sent to {receiver_email} for {product_name}")
            return True
        print(f"[notifier] Brevo API error {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        print(f"[notifier] Failed to send email: {e}")
        return False
