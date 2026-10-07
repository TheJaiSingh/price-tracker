"""
notifier.py
------------
Email bhejta hai jab price target hit ho jaye - ab product image
ke sath (HTML email, plain text nahi).
"""

import os
import socket
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "js7936574@gmail.com")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD", "jgof hvfx fpwx ojfb")

# ---------------------------------------------------------------------------
# FIX: Railway (aur kai cloud hosts) mein IPv6 se Gmail tak connect karne mein
# "Network is unreachable" error aata hai, kyunki unka IPv6 route nahi hota.
# Ye code DNS lookup ko IPv4-only force karta hai, taaki SMTP connection
# hamesha IPv4 use kare.
# ---------------------------------------------------------------------------
_original_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(*args, **kwargs):
    responses = _original_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]


socket.getaddrinfo = _ipv4_only_getaddrinfo


def send_price_alert(product_name: str, current_price: float, target_price: float,
                      product_url: str, receiver_email: str, image_url: str = None):
    subject = f"🎯 Price Drop Alert: {product_name}"

    # HTML email body - image_url ko <img> tag mein daal rahe hain
    image_html = f'<img src="{image_url}" width="200" style="border-radius:8px; margin-bottom:16px;">' if image_url else ""

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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = receiver_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        print(f"[notifier] Email sent to {receiver_email} for {product_name}")
        return True
    except Exception as e:
        print(f"[notifier] Failed to send email: {e}")
        return False
