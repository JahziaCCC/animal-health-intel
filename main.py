import os
import re
import json
import hashlib
import datetime
import requests
import xml.etree.ElementTree as ET

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "state.json"

# ===== إعدادات =====
MAX_ITEMS = 8
MAX_AGE_DAYS = 30   # استبعاد الأخبار القديمة

COUNTRY_KEYS = {
    "saudi arabia": "المملكة العربية السعودية",
    "sudan": "السودان",
    "somalia": "الصومال",
    "ethiopia": "إثيوبيا",
    "djibouti": "جيبوتي",
    "jordan": "الأردن",
}

DISEASE_KEYS = {
    "peste des petits ruminants": "طاعون المجترات الصغيرة (PPR)",
    "ppr": "طاعون المجترات الصغيرة (PPR)",
    "rift valley": "حمّى الوادي المتصدّع (RVF)",
    "rvf": "حمّى الوادي المتصدّع (RVF)",
    "foot and mouth": "الحمّى القلاعية (FMD)",
    "fmd": "الحمّى القلاعية (FMD)",
    "avian influenza": "إنفلونزا الطيور",
    "h5n1": "إنفلونزا الطيور (H5N1)",
    "lumpy skin": "مرض الجلد العقدي (LSD)",
    "anthrax": "الجمرة الخبيثة",
    "rabies": "داء الكلب",
}

REGION_AR = {
    "riyadh": "الرياض",
    "makkah": "مكة المكرمة",
    "madinah": "المدينة المنورة",
    "eastern province": "المنطقة الشرقية",
    "qassim": "القصيم",
    "asir": "عسير",
    "tabuk": "تبوك",
    "hail": "حائل",
    "jazan": "جازان",
    "najran": "نجران",
    "khartoum": "الخرطوم",
    "darfur": "دارفور",
    "oromia": "أوروميا",
    "amhara": "أمهرا",
    "addis ababa": "أديس أبابا",
    "amman": "عمّان",
    "irbid": "إربد",
}

GOOGLE_RSS = "https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"


# ===== أدوات =====
def now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)

def now_ksa_str():
    return now_ksa().strftime("%Y-%m-%d %H:%M") + " بتوقيت السعودية"


# ===== Telegram (مع تقسيم الرسائل) =====
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"

    parts = [text[i:i+3500] for i in range(0, len(text), 3500)]

    for p in parts:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": p,
                "disable_web_page_preview": True
            },
            timeout=30
        )
        r.raise_for_status()


# ===== State =====
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"seen": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def make_sid(url, title):
    raw = (url or "") + "|" + (title or "")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ===== كشف البيانات =====
def detect_country(text):
    low = text.lower()
    for k, v in COUNTRY_KEYS.items():
        if k in low:
            return v
    return None

def detect_disease(text):
    low = text.lower()
    for k, v in DISEASE_KEYS.items():
        if k in low:
            return v
    return None

def detect_region(text):
    low = text.lower()
    for k, v in REGION_AR.items():
        if k in low:
            return v
    return "غير محدد"


# ===== جلب RSS =====
def fetch_google_rss(query):
    url = GOOGLE_RSS.format(q=requests.utils.quote(query))
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, timeout=45, headers=headers)
    r.raise_for_status()

    root = ET.fromstring(r.text)

    items = []
    for it in root.findall(".//item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "pub": (it.findtext("pubDate") or "").strip(),
            "desc": (it.findtext("description") or "").strip(),
        })
    return items


# ===== فلتر التاريخ =====
def is_recent(pubdate):
    try:
        dt = datetime.datetime.strptime(pubdate, "%a, %d %b %Y %H:%M:%S %Z")
        dt = dt.replace(tzinfo=datetime.timezone.utc)
        age = now_ksa() - dt.astimezone(KSA_TZ)
        return age.days <= MAX_AGE_DAYS
    except:
        return True


# ===== MAIN =====
def main():

    state = load_state()

    queries = [
        '("PPR" OR "rift valley fever" OR "foot and mouth disease" OR "avian influenza" OR "lumpy skin disease") (livestock OR sheep OR goats OR cattle) (Saudi Arabia OR Sudan OR Somalia OR Ethiopia OR Djibouti OR Jordan)'
    ]

    all_items = []

    try:
        for q in queries:
            all_items.extend(fetch_google_rss(q))
    except Exception as e:
        tg_send(
            "⚠️ تعذر جلب الأخبار حالياً.\n"
            f"🕒 {now_ksa_str()}\n"
            f"السبب: {type(e).__name__}"
        )
        return

    new_events = []

    for it in all_items:

        if not is_recent(it["pub"]):
            continue

        blob = f"{it['title']} {it['desc']}"

        country = detect_country(blob)
        disease = detect_disease(blob)

        if not country or not disease:
            continue

        region = detect_region(blob)

        sid = make_sid(it["link"], it["title"])
        if sid in state["seen"]:
            continue

        state["seen"][sid] = {"first_seen": now_ksa_str()}

        new_events.append({
            "country": country,
            "disease": disease,
            "region": region,
            "title": it["title"],
            "link": it["link"]
        })

        if len(new_events) >= MAX_ITEMS:
            break

    # ===== تقرير =====
    if not new_events:
        tg_send(
            "📄 تقرير رصد الأمراض الحيوانية (Google News)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            "✅ لا توجد أخبار جديدة حديثة.\n"
            "🟢 الحالة التشغيلية: مستقر"
        )
        save_state(state)
        return

    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (Google News)",
        f"🕒 {now_ksa_str()}",
        "════════════════════",
        f"عدد الإشارات الجديدة: {len(new_events)}",
        "════════════════════",
    ]

    for i, e in enumerate(new_events, 1):
        lines.append(
            f"{i}) 🐾 {e['disease']}\n"
            f"   🌍 الدولة: {e['country']}\n"
            f"   📍 المنطقة: {e['region']}\n"
            f"   📰 العنوان: {e['title']}\n"
            f"   🔗 الرابط: {e['link']}"
        )

    tg_send("\n".join(lines))
    save_state(state)


if __name__ == "__main__":
    main()
