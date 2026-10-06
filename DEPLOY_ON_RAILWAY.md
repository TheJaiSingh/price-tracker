# Deploy on Railway (so friends can use it online)

Railway hosts both your backend code AND a MySQL database, free tier available.

## Step 1: Code ko GitHub pe daalo (zaroori hai Railway ke liye)

1. https://github.com pe account banao (agar nahi hai)
2. "New repository" → name: `price-tracker` → Create
3. Apne project folder mein, VS Code terminal mein:
   ```
   git init
   git add .
   git commit -m "first commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/price-tracker.git
   git push -u origin main
   ```
   (GitHub login maangega browser mein, login kar lo)

**Important:** `notifier.py` aur `main.py` mein ab tumhare actual password/secrets
nahi hain (env variables use kar rahe hain) - isliye GitHub pe safely daal sakte ho.

## Step 2: Railway account banao
1. https://railway.app pe jao
2. "Login with GitHub" se sign up karo

## Step 3: MySQL database banao
1. Railway dashboard mein "New Project" → "Provision MySQL"
2. Database ban jayega. Uspe click karo → "Variables" tab
3. Yahan se note kar lo: `MYSQLHOST`, `MYSQLUSER`, `MYSQLPASSWORD`, `MYSQLDATABASE`, `MYSQLPORT`

## Step 4: Database mein tables banao
1. Database ke "Data" tab mein jao, ya apne local MySQL client se Railway
   ke database se connect karo (host/user/password Step 3 se)
2. `database.sql` ka content wahan run karo (same jo localhost pe kiya tha)

## Step 5: Backend deploy karo
1. Usi Railway project mein, "New" → "GitHub Repo" → apna `price-tracker` repo select karo
2. Railway automatically `Procfile` dekh ke deploy kar dega
3. Deploy hone ke baad, "Settings" → "Networking" → "Generate Domain" dabao
4. Ek public URL milega jaisa: `https://price-tracker-production.up.railway.app`

## Step 6: Environment Variables set karo
Backend service ke "Variables" tab mein, ye sab add karo:
```
DB_HOST       = (Railway MySQL ka MYSQLHOST)
DB_USER       = (Railway MySQL ka MYSQLUSER)
DB_PASSWORD   = (Railway MySQL ka MYSQLPASSWORD)
DB_NAME       = (Railway MySQL ka MYSQLDATABASE)
DB_PORT       = (Railway MySQL ka MYSQLPORT)
GOOGLE_CLIENT_ID    = (tumhara Google Client ID)
SENDER_EMAIL        = (tumhara Gmail)
SENDER_APP_PASSWORD = (tumhara Gmail App Password)
```

## Step 7: Google Cloud Console mein naya domain add karo
1. console.cloud.google.com → APIs & Services → Credentials
2. Apna OAuth Client ID edit karo
3. "Authorized JavaScript origins" mein **naya URI add karo**:
   ```
   https://price-tracker-production.up.railway.app
   ```
   (Step 5 wala actual URL daalo)
4. Save karo

## Step 8: dashboard_connected.html mein Client ID update karo (agar already nahi hai)
Code already same-origin use karta hai deployment pe, kuch aur change nahi chahiye.

## Step 9: Test karo
1. Apna Railway URL browser mein kholo: `https://price-tracker-production.up.railway.app`
2. Dashboard khulega, "Sign in with Google" try karo
3. Ye URL apne 10 friends ko bhej do - wo apne Google account se login karke
   apne khud ke products track kar sakte hain!

## Troubleshooting
- "Application failed to respond" -> Railway logs check karo (Deployments tab)
- Login fail ho raha -> Google Cloud Console mein domain sahi se add hua check karo
- Database error -> environment variables sahi se set hain check karo
