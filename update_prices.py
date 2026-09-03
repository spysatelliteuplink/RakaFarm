import os
import requests
import json
from datetime import datetime
import time

# ================== CONFIG ==================
# เวลาทำงานบน GitHub ตัวนี้จะไปอ่านค่าจาก Secret ข้างนอก
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lmghalsohhwlwyfbivvg.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MOC_API_KEY = os.environ.get("MOC_API_KEY", "")

# ถ้าไม่มี Service Role Key ก็จบการทำงานทันที
if not SUPABASE_KEY:
    print("❌ Missing SUPABASE_SERVICE_ROLE_KEY")
    exit(1)

# หัวข้อสำหรับเรียก Supabase (ใช้สิทธิ์แบบ Admin)
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ================== 1. รายการสินค้า (ใช้ให้ครบทุกหมวด) ==================
PRODUCTS = [
    {"id": "P11001", "name": "ข้าวเปลือกหอมมะลินาปี", "cat": "ข้าว"},
    {"id": "P11002", "name": "ข้าวเปลือกเจ้า", "cat": "ข้าว"},
    {"id": "P21001", "name": "มันสำปะหลัง", "cat": "พืชไร่"},
    {"id": "RUB001", "name": "ยางแผ่นดิบ", "cat": "ยางพารา"},
    {"id": "LIV001", "name": "หมูขุน", "cat": "สัตว์เลี้ยง"},
    {"id": "FERT001", "name": "ปุ๋ยยูเรีย", "cat": "ปุ๋ย"},
]

# ================== 2. ฟังก์ชันเรียก MOC ==================
def fetch_price(product_id, date_str):
    if not MOC_API_KEY:
        # ถ้าไม่มี Key ก็ใช้ตัวเลขสุ่ม (Mock) เพื่อให้เห็นการทำงาน
        import random
        return {
            "avg": round(random.uniform(100, 500), 2),
            "min": round(random.uniform(90, 400), 2),
            "max": round(random.uniform(110, 600), 2),
            "list": []
        }
    
    url = "https://dataapi.moc.go.th/gis-product-price"
    params = {
        "product_id": product_id,
        "from_date": date_str,
        "to_date": date_str,
        "api_key": MOC_API_KEY
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data and len(data) > 0:
            item = data[0]
            return {
                "avg": round((item.get("price_min_avg", 0) + item.get("price_max_avg", 0)) / 2, 2),
                "min": item.get("price_min_avg", 0),
                "max": item.get("price_max_avg", 0),
                "list": item.get("price_list", [])
            }
    except Exception as e:
        print(f"Error: {e}")
    return None

# ================== 3. อัปโหลดขึ้น Supabase ==================
def upsert_product(product):
    # ตรวจสอบว่ามีสินค้านี้ในระบบหรือยัง
    check = requests.get(
        f"{SUPABASE_URL}/rest/v1/products?product_code=eq.{product['id']}&select=id",
        headers=HEADERS
    ).json()
    
    if check and len(check) > 0:
        return check[0]["id"]
    
    # ถ้าไม่มี -> สร้างใหม่
    new_prod = {
        "product_code": product["id"],
        "name_th": product["name"],
        "category": product["cat"]
    }
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/products",
        headers=HEADERS,
        json=new_prod
    )
    return resp.json()[0]["id"] if resp.status_code == 201 else None

def save_price(product_uuid, product_code, price_data, date_str):
    payload = {
        "product_id": product_uuid,
        "price_avg": price_data["avg"],
        "price_min": price_data["min"],
        "price_max": price_data["max"],
        "scraped_at": date_str,
        "source": "moc"
    }
    headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"}
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/daily_prices?on_conflict=product_id,scraped_at",
        headers=headers,
        json=payload
    )
    return resp.status_code in [200, 201]

# ================== 4. เริ่มทำงาน ==================
def main():
    print("🚀 เริ่มอัปเดตราคา...")
    today = datetime.now().strftime("%Y-%m-%d")
    success = 0

    for p in PRODUCTS:
        print(f"⏳ กำลังดึง {p['name']}...")
        price = fetch_price(p["id"], today)
        if not price:
            print(f"   ❌ ดึงไม่สำเร็จ")
            continue
        
        # หา UUID ของสินค้า
        uuid = upsert_product(p)
        if not uuid:
            print(f"   ❌ ไม่สามารถสร้างสินค้าได้")
            continue
        
        # บันทึกราคา
        if save_price(uuid, p["id"], price, today):
            print(f"   ✅ {p['name']}: {price['avg']} บาท")
            success += 1
        else:
            print(f"   ❌ บันทึกล้มเหลว")
        
        time.sleep(0.5)  # หน่วงเวลา

    print(f"🎉 สำเร็จ {success}/{len(PRODUCTS)} รายการ")

if __name__ == "__main__":
    main()