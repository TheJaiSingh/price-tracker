"""
notifier.py
------------
Brevo HTTPS API se email bhejta hai (Railway SMTP block karta hai).

Env variables (Railway -> Variables):
    BREVO_API_KEY  - Brevo dashboard -> SMTP & API -> API keys
    SENDER_EMAIL   - Brevo mein verified sender email
"""

import os
import html as _html
import requests

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
SENDER_NAME = "PriceWatch"


def _env(name):
    v = os.environ.get(name)
    return v.strip().strip('"').strip("'") if v else None


def _send(to_email: str, subject: str, html_body: str) -> bool:
    key, sender = _env("BREVO_API_KEY"), _env("SENDER_EMAIL")
    if not key or not sender:
        print(f"[notifier] Missing env -> BREVO_API_KEY set: {bool(key)}, SENDER_EMAIL set: {bool(sender)}")
        return False
    payload = {
        "sender": {"name": SENDER_NAME, "email": sender},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
    }
    headers = {"api-key": key, "accept": "application/json", "content-type": "application/json"}
    try:
        r = requests.post(BREVO_URL, json=payload, headers=headers, timeout=15)
        if r.status_code in (200, 201, 202):
            print(f"[notifier] Email sent to {to_email}: {subject}")
            return True
        print(f"[notifier] Brevo API error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[notifier] Failed to send email: {e}")
    return False


def _short(text, n):
    text = str(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def send_price_alert(product_name, current_price, target_price, product_url, receiver_email,
                     image_url=None, reason=None, site="amazon"):
    name = _html.escape(_short(product_name, 110))
    shop = "Flipkart" if site == "flipkart" else "Amazon"
    img = (f'<img src="{_html.escape(image_url)}" width="200" style="border-radius:8px;margin-bottom:16px;">'
           if image_url else "")
    why = reason or "Your target price has been reached!"
    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#20261C;">
      <div style="max-width:420px;margin:auto;padding:24px;border:1px solid #eee;border-radius:12px;">
        <p style="font-size:13px;letter-spacing:1px;color:#D2481E;font-weight:bold;">PRICE DROP ALERT</p>
        {img}
        <h2 style="margin:0 0 10px;">{name}</h2>
        <p style="color:#5B6156;">{_html.escape(why)}</p>
        <table style="margin:16px 0;">
          <tr><td style="color:#5B6156;padding-right:10px;">Current Price:</td>
              <td style="font-weight:bold;font-size:20px;color:#3E8E5C;">₹{float(current_price):,.2f}</td></tr>
          <tr><td style="color:#5B6156;padding-right:10px;">Your Target:</td>
              <td>₹{float(target_price):,.2f}</td></tr>
        </table>
        <a href="{_html.escape(product_url)}" style="display:inline-block;background:#20261C;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;">Buy Now on {shop}</a>
        <p style="margin-top:24px;font-size:12px;color:#999;">— PriceWatch (Price Tracker)</p>
      </div>
    </body></html>"""
    return _send(receiver_email, f"🎯 Price Drop Alert: {_short(product_name, 55)}", body)


def send_weekly_summary(receiver_email, user_name, rows):
    """rows: [{name, before, now, change_pct, lowest, target}]"""
    trs = ""
    for r in rows:
        ch = r["change_pct"]
        color = "#3E8E5C" if ch < 0 else ("#B3362B" if ch > 0 else "#5B6156")
        arrow = "↓" if ch < 0 else ("↑" if ch > 0 else "–")
        trs += (f'<tr><td style="padding:8px 6px;border-top:1px solid #eee;">{_html.escape(str(r["name"]))[:60]}</td>'
                f'<td style="padding:8px 6px;border-top:1px solid #eee;">₹{r["before"]:,.0f}</td>'
                f'<td style="padding:8px 6px;border-top:1px solid #eee;font-weight:bold;">₹{r["now"]:,.0f}</td>'
                f'<td style="padding:8px 6px;border-top:1px solid #eee;color:{color};font-weight:bold;">{arrow} {abs(ch):.1f}%</td></tr>')
    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#20261C;">
      <div style="max-width:560px;margin:auto;padding:24px;border:1px solid #eee;border-radius:12px;">
        <p style="font-size:13px;letter-spacing:1px;color:#D2481E;font-weight:bold;">WEEKLY SUMMARY</p>
        <h2 style="margin:0 0 6px;">Hi {_html.escape(user_name or "there")}, here's your week</h2>
        <p style="color:#5B6156;margin:0 0 14px;">How your tracked products moved over the last 7 days.</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr style="text-align:left;color:#5B6156;"><th style="padding:6px;">Product</th><th style="padding:6px;">Last week</th><th style="padding:6px;">Now</th><th style="padding:6px;">Change</th></tr>
          {trs}
        </table>
        <p style="margin-top:24px;font-size:12px;color:#999;">— PriceWatch (Price Tracker)</p>
      </div>
    </body></html>"""
    return _send(receiver_email, "📊 Your PriceWatch weekly summary", body)
