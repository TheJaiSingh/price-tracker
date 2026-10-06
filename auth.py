"""
auth.py
--------
Google Sign-In verify karne ka code.

Jab user "Sign in with Google" button dabata hai (frontend pe), Google
ek "ID token" deta hai jo prove karta hai "ye waqai is email ka malik hai".
Ye file us token ko verify karti hai aur uske andar se email/naam nikalti hai.
"""

import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Google Cloud Console se mila hua Client ID - env variable se, ya local
# testing ke liye seedha yahan bhi daal sakte ho (default value)
GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_CLIENT_ID", "331699817935-ui9behvct4leckcuujfogbsv4km696t7.apps.googleusercontent.com"
)


def verify_google_token(token: str):
    """
    Token verify karta hai aur user ki info (email, naam, google_id) return karta hai.
    Agar token galat/fake hai, to exception raise hogi.
    """
    idinfo = id_token.verify_oauth2_token(
        token, google_requests.Request(), GOOGLE_CLIENT_ID
    )
    return {
        "google_id": idinfo["sub"],       # Google ka unique user ID
        "email": idinfo["email"],
        "name": idinfo.get("name", ""),
        "picture": idinfo.get("picture", ""),
    }
