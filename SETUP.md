# Setup Steps (in order)

## 1. MySQL setup
- MySQL Workbench ya command line kholo
- `database.sql` file run karo:
  ```
  mysql -u root -p < database.sql
  ```
  (Ye "price_tracker" naam ki database aur 2 tables bana dega)

## 2. Install Python packages
Terminal/CMD mein backend folder ke andar jao:
```
cd price_tracker_backend
pip install -r requirements.txt
```

## 3. Password set karo
`main.py` file kholo, ye line dhundo:
```python
"password": "YOUR_MYSQL_PASSWORD",
```
Apna MySQL password yahan daalo.

## 4. Server start karo
```
uvicorn main:app --reload
```
Terminal mein "Uvicorn running on http://127.0.0.1:8000" dikhega.

## 5. Test karo (browser mein)
Ye URL kholo:
```
http://127.0.0.1:8000/docs
```
Yahan Swagger UI khulega jisme har API ko directly test kar sakte ho -
"Try it out" button daba ke.

## 6. Sample test (POST /products)
```json
{
  "product_url": "https://www.amazon.in/dp/B08XYZ1234",
  "target_price": 999
}
```
"Execute" dabao - agar sab sahi hai to response mein product ka data
aayega aur database mein bhi save ho jayega.

---
## Agar koi error aaye
- "Access denied for user" -> password galat hai main.py mein
- "Unknown database" -> Step 1 (database.sql) run nahi hui
- "Module not found" -> Step 2 (pip install) dobara try karo
