"""
main.py
--------
FastAPI backend with Google Sign-In.

Endpoints:
 POST   /auth/google                  login with Google
 POST   /products?email=              add product (target price, optional % drop alert)
 GET    /products?email=              list products (+ lowest price, check count)
 GET    /products/{id}/history        price history
 POST   /products/{id}/refresh        re-check price now (+ email alert, only once per new low)
 POST   /products/check-all?email=    re-check all of this user's products
 PATCH  /products/{id}?email=         edit target price / % drop alert
 DELETE /products/{id}?email=         delete product
 GET    /export.csv?email=            download price history as CSV
 POST   /summary/send?email=          send the weekly summary email now

Background (automatic):
 - every CHECK_INTERVAL_HOURS (default 6) all products are re-checked
 - every 7 days a weekly summary email is sent

Run: uvicorn main:app --reload
"""

import os
import io
import csv
import time
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
import mysql.connector

from scraper import fetch_product, site_of
from notifier import send_price_alert, send_weekly_summary
from auth import verify_google_token

app = FastAPI(title="Price Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "Jai3121@singh"),
    "database": os.environ.get("DB_NAME", "price_tracker"),
    "port": int(os.environ.get("DB_PORT", 3306)),
}

CHECK_HOURS = float(os.environ.get("CHECK_INTERVAL_HOURS", 6))
AUTO_CHECK = os.environ.get("AUTO_CHECK", "1") != "0"


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


class GoogleLogin(BaseModel):
    token: str


class ProductCreate(BaseModel):
    product_url: str
    target_price: float
    alert_percent: Optional[float] = None


class ProductUpdate(BaseModel):
    target_price: Optional[float] = None
    alert_percent: Optional[float] = None   # 0 = percent alert off


# ============================================================
# DB MIGRATION (naye columns / table automatically ban jate hain)
# ============================================================
def ensure_schema():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for ddl in (
            "ALTER TABLE products ADD COLUMN last_alerted_price DECIMAL(12,2) NULL",
            "ALTER TABLE products ADD COLUMN alert_percent DECIMAL(5,2) NULL",
        ):
            try:
                cur.execute(ddl)
            except mysql.connector.Error as e:
                if e.errno != 1060:  # 1060 = column already exists
                    print(f"[schema] {e}")
        cur.execute("CREATE TABLE IF NOT EXISTS app_state (k VARCHAR(50) PRIMARY KEY, v VARCHAR(100))")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[schema] could not migrate: {e}")


def get_state(key):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT v FROM app_state WHERE k = %s", (key,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    return r[0] if r else None


def set_state(key, value):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("REPLACE INTO app_state (k, v) VALUES (%s, %s)", (key, str(value)))
    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# ALERT LOGIC (ek hi alert, jab tak price aur na gire)
# ============================================================
def decide_alert(new, target, pct, start, last):
    """Returns (reason, should_send). last = pichhli alert ka price (ya None)."""
    reason = None
    if new <= target:
        reason = f"Your target price of ₹{target:,.0f} has been reached!"
    elif pct and start and new <= start * (1 - pct / 100):
        reason = f"The price dropped {pct:g}% since you started tracking!"
    if not reason:
        return None, False
    if last is None or new < last:
        return reason, True
    return reason, False


def maybe_alert(cur, pr, new, name, image):
    """pr: dict with id, target_price, alert_percent, last_alerted_price, product_url, email"""
    target = float(pr["target_price"])
    pct = float(pr["alert_percent"]) if pr.get("alert_percent") else None
    last = float(pr["last_alerted_price"]) if pr.get("last_alerted_price") is not None else None
    start = None
    if pct:
        cur.execute("SELECT price FROM price_history WHERE product_id = %s ORDER BY checked_at ASC LIMIT 1", (pr["id"],))
        r = cur.fetchone()
        start = float(r["price"]) if r else None

    reason, send = decide_alert(new, target, pct, start, last)
    sent = False
    if send:
        sent = send_price_alert(name, new, target, pr["product_url"], pr["email"], image, reason, site_of(pr["product_url"]))
        if sent:
            cur.execute("UPDATE products SET last_alerted_price = %s WHERE id = %s", (new, pr["id"]))
    elif reason is None and last is not None:
        cur.execute("UPDATE products SET last_alerted_price = NULL WHERE id = %s", (pr["id"],))
    return sent


def check_product(conn, product_id, auto=False):
    """Price dobara scrape karo, save karo, zaroorat ho to email.
    auto=True (scheduler): asli price na mile to kuch nahi badalta (nakli price se jhootha alert nahi)."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT p.*, u.email FROM products p JOIN users u ON p.user_id = u.id WHERE p.id = %s",
        (product_id,),
    )
    pr = cur.fetchone()
    if not pr:
        cur.close()
        return None

    info = fetch_product(pr["product_url"], previous_price=float(pr["current_price"]))
    if auto and not info["real"]:
        cur.close()
        return {"id": product_id, "new_price": float(pr["current_price"]), "target_hit": False,
                "alert_sent": False, "real": False, "skipped": True}
    new = info["price"]
    if info["real"]:
        cur.execute(
            "UPDATE products SET current_price=%s, product_name=%s, image_url=%s WHERE id=%s",
            (new, info["name"], info["image"] or pr["image_url"], product_id),
        )
        name, image = info["name"], info["image"] or pr["image_url"]
    else:
        cur.execute("UPDATE products SET current_price=%s WHERE id=%s", (new, product_id))
        name, image = pr["product_name"], pr["image_url"]
    cur.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (product_id, new))

    sent = maybe_alert(cur, pr, new, name, image)
    conn.commit()
    cur.close()
    return {
        "id": product_id,
        "new_price": new,
        "target_hit": new <= float(pr["target_price"]),
        "alert_sent": bool(sent),
        "real": info["real"],
    }


# ============================================================
# 1. GOOGLE LOGIN
# ============================================================
@app.post("/auth/google")
def google_login(payload: GoogleLogin):
    try:
        user_info = verify_google_token(payload.token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE google_id = %s", (user_info["google_id"],))
    user = cursor.fetchone()
    if not user:
        cursor.execute(
            "INSERT INTO users (google_id, email, name) VALUES (%s, %s, %s)",
            (user_info["google_id"], user_info["email"], user_info["name"]),
        )
        conn.commit()
        user_id = cursor.lastrowid
    else:
        user_id = user["id"]
    cursor.close()
    conn.close()
    return {"user_id": user_id, "email": user_info["email"], "name": user_info["name"],
            "picture": user_info.get("picture", "")}


def get_user_id_by_email(email: str):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please log in again.")
    return user["id"]


def _validate_pct(pct):
    if pct is not None and pct != 0 and not (1 <= pct <= 90):
        raise HTTPException(status_code=400, detail="alert_percent must be between 1 and 90")


# ============================================================
# 2. ADD PRODUCT
# ============================================================
@app.post("/products")
def add_product(product: ProductCreate, email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    if product.target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price must be above 0")
    _validate_pct(product.alert_percent)

    info = fetch_product(product.product_url)
    price, name, image_url, link = info["price"], info["name"], info["image"], info["url"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "INSERT INTO products (user_id, product_url, product_name, image_url, target_price, current_price, alert_percent) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (user_id, link, name, image_url, product.target_price, price, product.alert_percent or None),
    )
    product_id = cursor.lastrowid
    cursor.execute("INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (product_id, price))

    pr = {"id": product_id, "target_price": product.target_price, "alert_percent": product.alert_percent,
          "last_alerted_price": None, "product_url": link, "email": email}
    maybe_alert(cursor, pr, price, name, image_url)
    conn.commit()
    cursor.close()
    conn.close()
    return {"id": product_id, "name": name, "current_price": price, "image_url": image_url}


# ============================================================
# 3. LIST PRODUCTS (+ lowest price, number of checks)
# ============================================================
@app.get("/products")
def list_products(email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT p.*, "
        "(SELECT MIN(h.price) FROM price_history h WHERE h.product_id = p.id) AS lowest_price, "
        "(SELECT COUNT(*) FROM price_history h WHERE h.product_id = p.id) AS checks "
        "FROM products p WHERE p.user_id = %s ORDER BY p.created_at DESC",
        (user_id,),
    )
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return products


# ============================================================
# 4. PRICE HISTORY
# ============================================================
@app.get("/products/{product_id}/history")
def get_history(product_id: int):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT price, checked_at FROM price_history WHERE product_id = %s ORDER BY checked_at",
        (product_id,),
    )
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return history


# ============================================================
# 5. REFRESH ONE / CHECK ALL
# ============================================================
@app.post("/products/check-all")
def check_all(email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM products WHERE user_id = %s", (user_id,))
    ids = [r[0] for r in cur.fetchall()]
    cur.close()
    results = [r for r in (check_product(conn, i) for i in ids) if r]
    conn.close()
    return {"checked": len(results), "alerts_sent": sum(1 for r in results if r["alert_sent"])}


@app.post("/products/{product_id}/refresh")
def refresh_price(product_id: int):
    conn = get_db_connection()
    result = check_product(conn, product_id)
    conn.close()
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")
    return result


# ============================================================
# 6. EDIT TARGET / % ALERT
# ============================================================
@app.patch("/products/{product_id}")
def update_product(product_id: int, body: ProductUpdate, email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    _validate_pct(body.alert_percent)
    sets, vals = [], []
    if body.target_price is not None:
        if body.target_price <= 0:
            raise HTTPException(status_code=400, detail="target_price must be above 0")
        sets.append("target_price = %s")
        vals.append(body.target_price)
    if body.alert_percent is not None:
        if body.alert_percent == 0:
            sets.append("alert_percent = NULL")
        else:
            sets.append("alert_percent = %s")
            vals.append(body.alert_percent)
    if not sets:
        raise HTTPException(status_code=400, detail="Nothing to update")
    sets.append("last_alerted_price = NULL")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM products WHERE id = %s AND user_id = %s", (product_id, user_id))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")
    cur.execute(f"UPDATE products SET {', '.join(sets)} WHERE id = %s", (*vals, product_id))
    cur.execute(
        "SELECT p.*, u.email FROM products p JOIN users u ON p.user_id = u.id WHERE p.id = %s", (product_id,)
    )
    pr = cur.fetchone()
    sent = maybe_alert(cur, pr, float(pr["current_price"]), pr["product_name"], pr["image_url"])
    conn.commit()
    cur.close()
    conn.close()
    return {"updated": product_id, "alert_sent": bool(sent)}


# ============================================================
# 7. DELETE
# ============================================================
@app.delete("/products/{product_id}")
def delete_product(product_id: int, email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM products WHERE id = %s AND user_id = %s", (product_id, user_id))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")
    cursor.execute("DELETE FROM price_history WHERE product_id = %s", (product_id,))
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"deleted": product_id}


# ============================================================
# 8. CSV EXPORT
# ============================================================
@app.get("/export.csv")
def export_csv(email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT p.product_name, p.product_url, p.target_price, h.price, h.checked_at "
        "FROM products p JOIN price_history h ON h.product_id = p.id "
        "WHERE p.user_id = %s ORDER BY p.id, h.checked_at",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Product", "Site", "Link", "Target price", "Checked at", "Price"])
    for r in rows:
        w.writerow([r["product_name"], site_of(r["product_url"]).title(), r["product_url"],
                    r["target_price"], r["checked_at"], r["price"]])
    return Response(
        "\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=pricewatch_history.csv"},
    )


# ============================================================
# 9. WEEKLY SUMMARY
# ============================================================
def build_summary_rows(cur, user_id):
    cur.execute("SELECT id, product_name, current_price, target_price FROM products WHERE user_id = %s", (user_id,))
    rows = []
    for p in cur.fetchall():
        cur.execute(
            "SELECT price FROM price_history WHERE product_id = %s AND checked_at <= NOW() - INTERVAL 7 DAY "
            "ORDER BY checked_at DESC LIMIT 1", (p["id"],))
        r = cur.fetchone()
        if not r:
            cur.execute("SELECT price FROM price_history WHERE product_id = %s ORDER BY checked_at ASC LIMIT 1", (p["id"],))
            r = cur.fetchone()
        before = float(r["price"]) if r else float(p["current_price"])
        now = float(p["current_price"])
        rows.append({"name": p["product_name"], "before": before, "now": now,
                     "change_pct": ((now - before) / before * 100) if before else 0.0,
                     "target": float(p["target_price"])})
    return rows


def send_summary_to(user_id, email, name):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    rows = build_summary_rows(cur, user_id)
    cur.close()
    conn.close()
    if not rows:
        return False
    return send_weekly_summary(email, name, rows)


@app.post("/summary/send")
def summary_now(email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT name FROM users WHERE id = %s", (user_id,))
    u = cur.fetchone()
    cur.close()
    conn.close()
    return {"sent": bool(send_summary_to(user_id, email, u["name"] if u else ""))}


# ============================================================
# BACKGROUND SCHEDULER (auto price check + weekly summary)
# ============================================================
_check_lock = threading.Lock()


def run_all_checks():
    if not _check_lock.acquire(blocking=False):
        return 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM products")
        ids = [r[0] for r in cur.fetchall()]
        cur.close()
        for pid in ids:
            try:
                check_product(conn, pid, auto=True)
            except Exception as e:
                print(f"[scheduler] product {pid} failed: {e}")
            time.sleep(2)
        conn.close()
        return len(ids)
    finally:
        _check_lock.release()


def send_all_summaries():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DISTINCT u.id, u.email, u.name FROM users u JOIN products p ON p.user_id = u.id")
    users = cur.fetchall()
    cur.close()
    conn.close()
    for u in users:
        try:
            send_summary_to(u["id"], u["email"], u["name"])
        except Exception as e:
            print(f"[scheduler] summary for {u['email']} failed: {e}")


def scheduler_loop():
    time.sleep(30)
    while True:
        try:
            now = time.time()
            if now - float(get_state("last_check") or 0) >= CHECK_HOURS * 3600:
                set_state("last_check", now)
                n = run_all_checks()
                print(f"[scheduler] auto-checked {n} products")
            lw = get_state("last_weekly")
            if lw is None:
                set_state("last_weekly", now)
            elif now - float(lw) >= 7 * 86400:
                set_state("last_weekly", now)
                send_all_summaries()
                print("[scheduler] weekly summaries sent")
        except Exception as e:
            print(f"[scheduler] error: {e}")
        time.sleep(600)


@app.on_event("startup")
def on_startup():
    ensure_schema()
    if AUTO_CHECK:
        threading.Thread(target=scheduler_loop, daemon=True).start()
        print(f"[scheduler] started (every {CHECK_HOURS}h)")


# ============================================================
# SERVE THE FRONTEND
# ============================================================
@app.get("/")
def serve_dashboard():
    return FileResponse("dashboard_connected.html")
