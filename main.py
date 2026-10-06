"""
main.py
--------
FastAPI backend with Google Sign-In.

Endpoints:
1. POST /auth/google              -> login with Google, creates/finds user
2. POST /products?email=...       -> add product for a specific user
3. GET  /products?email=...       -> list that user's products
4. GET  /products/{id}/history    -> price history for one product
5. POST /products/{id}/refresh    -> re-check price, email alert if target hit

Run: uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import mysql.connector
from scraper import get_amazon_price
from notifier import send_price_alert
from auth import verify_google_token

app = FastAPI(title="Amazon Price Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Database Connection Settings ----------
# os.environ.get(KEY, default) -> Railway pe ye values "Environment Variables"
# se aayengi. Local testing ke liye, default value tera pehle wala password
# use kar lega agar env variable set nahi hai.
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "Jai3121@singh"),
    "database": os.environ.get("DB_NAME", "price_tracker"),
    "port": int(os.environ.get("DB_PORT", 3306)),
}


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


# ---------- Request body shapes ----------
class GoogleLogin(BaseModel):
    token: str   # Google se mila hua ID token (frontend se aayega)


class ProductCreate(BaseModel):
    product_url: str
    target_price: float


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

    # Check karo user pehle se hai kya
    cursor.execute("SELECT * FROM users WHERE google_id = %s", (user_info["google_id"],))
    user = cursor.fetchone()

    if not user:
        # Naya user hai, create karo
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

    return {
        "user_id": user_id,
        "email": user_info["email"],
        "name": user_info["name"],
        "picture": user_info.get("picture", ""),
    }


# ---------- Helper: email se user_id nikalna ----------
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


# ============================================================
# 2. ADD PRODUCT (for the logged-in user)
# ============================================================
@app.post("/products")
def add_product(product: ProductCreate, email: str = Query(...)):
    user_id = get_user_id_by_email(email)
    price, name, image_url = get_amazon_price(product.product_url)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (user_id, product_url, product_name, image_url, target_price, current_price) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, product.product_url, name, image_url, product.target_price, price),
    )
    product_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (product_id, price)
    )
    conn.commit()
    cursor.close()
    conn.close()

    if price <= product.target_price:
        send_price_alert(name, price, product.target_price, product.product_url, email, image_url)

    return {"id": product_id, "name": name, "current_price": price, "image_url": image_url}


# ============================================================
# 3. LIST PRODUCTS (only for the logged-in user)
# ============================================================
@app.get("/products")
def list_products(email: str = Query(...)):
    user_id = get_user_id_by_email(email)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM products WHERE user_id = %s ORDER BY created_at DESC", (user_id,)
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
# 5. REFRESH PRICE (re-scrape + email if target hit)
# ============================================================
@app.post("/products/{product_id}/refresh")
def refresh_price(product_id: int):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT p.*, u.email FROM products p JOIN users u ON p.user_id = u.id WHERE p.id = %s",
        (product_id,),
    )
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")

    new_price, _, new_image = get_amazon_price(product["product_url"])

    cursor.execute(
        "UPDATE products SET current_price = %s, image_url = %s WHERE id = %s",
        (new_price, new_image, product_id),
    )
    cursor.execute(
        "INSERT INTO price_history (product_id, price) VALUES (%s, %s)", (product_id, new_price)
    )
    conn.commit()
    cursor.close()
    conn.close()

    hit_target = new_price <= float(product["target_price"])
    if hit_target:
        send_price_alert(
            product["product_name"], new_price, float(product["target_price"]),
            product["product_url"], product["email"], new_image,
        )

    return {"id": product_id, "new_price": new_price, "target_hit": hit_target}


# ============================================================
# SERVE THE FRONTEND (so the whole project is one single deployment)
# ============================================================
@app.get("/")
def serve_dashboard():
    return FileResponse("dashboard_connected.html")
