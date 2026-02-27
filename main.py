import os, re, json, hashlib, datetime
import requests
import xml.etree.ElementTree as ET

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "state.json"

# ===== إعدادات =====
MAX_ITEMS_PER_RUN = 15

# الدول تحت المراقبة (بالإنجليزي كما تظهر في النص غالباً)
COUNTRY_KEYS = {
    "saudi arabia": "المملكة العربية السعودية",
    "ksa": "المملكة العربية السعودية",
    "sudan": "السودان",
    "somalia": "الصومال",
    "ethiopia": "إثيوبيا",
    "djibouti": "جيبوتي",
    "jordan": "الأردن",
}

# الأمراض (كلمات مفتاحية)
DISEASE_KEYS = {
    "ppr": "طاعون المجترات الصغيرة (PPR)",
    "peste des petits ruminants": "طاعون المجترات الصغيرة (PPR)",
    "rift valley": "حمّى الوادي المتصدع (RVF)",
    "rvf": "حمّى الوادي المتصدع (RVF)",
    "foot and mouth": "الحمّى القلاعية (FMD)",
    "fmd": "الحمّى القلاعية (FMD)",
    "avian influenza": "إنفلونزا الطيور",
    "h5n1": "إنفلونزا الطيور (H5N1)",
    "lumpy skin": "مرض الجلد العقدي (LSD)",
}

# قاموس مناطق (قابل للتوسعة) + تعريب تلقائي fallback
REGION_AR = {
    # KSA
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
    "al bahah": "الباحة",
    "al jawf": "الجوف",
    "northern borders": "الحدود الشمالية",
    # Sudan
    "khartoum": "الخرطوم",
    "darfur": "دارفور",
    "kassala": "كسلا",
    "gedaref": "القضارف",
    "gezira": "الجزيرة",
    "red sea": "البحر الأحمر",
    # Somalia
    "banadir": "بنادر",
    "puntland": "بونتلاند",
    "somaliland": "صوماليلاند",
    # Ethiopia
    "oromia": "أوروميا",
    "amhara": "أمهرا",
    "tigray": "تيغراي",
    "afar": "عفار",
    "addis ababa": "أديس أبابا",
    # Djibouti
    "ali sabieh": "علي صبيح",
    "tadjourah": "تاجورة",
    "obock": "أوبوك",
    "dikhil": "دخيل",
    "arta": "عرطة",
    # Jordan
    "amman": "عمّان",
    "zarqa": "الزرقاء",
    "irbid": "إربد",
    "aqaba": "العقبة",
}

# مصدر RSS (تنبيه: إذا تغير المصدر نبدله بسهولة)
RSS_URLS = [
    "https://promedmail.org/rss/",  # RSS عام
]

def now_ksa_str():
    return datetime.datetime.now(tz=KSA_TZ).strftime("%Y-%m-%d %H:%M") + " بتوقيت السعودية"

def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=30)
    r.raise_for_status()

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def sid_from(link: str, title: str) -> str:
    raw = (link or "") + "|" + (title or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def arabize_simple(text: str) -> str:
    if not text:
        return "-"
    t = text.strip()
    if re.search(r"[\u0600-\u06FF]", t):
        return t
    # تعريب خفيف جداً
    rep = [
        ("-"," "), ("_"," "),
    ]
    for a,b in rep:
        t = t.replace(a,b)
    # لو كلمة/منطقة موجودة في القاموس
    key = t.lower()
    if key in REGION_AR:
        return REGION_AR[key]
    return t  # fallback: نتركها كما هي بدل تهجئة غريبة

def detect_country(text: str) -> str | None:
    low = (text or "").lower()
    for k, ar in COUNTRY_KEYS.items():
        if k in low:
            return ar
    return None

def detect_disease(text: str) -> str | None:
    low = (text or "").lower()
    for k, ar in DISEASE_KEYS.items():
        if k in low:
            return ar
    return None

def detect_region(text: str) -> str:
    low = (text or "").lower()
    for k, ar in REGION_AR.items():
        if k in low:
            return ar
    return "غير محدد"

def fetch_rss_items():
    items = []
    for url in RSS_URLS:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.text)

        # RSS structure: channel/item
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            desc = (it.findtext("description") or "").strip()
            items.append({"title": title, "link": link, "pubDate": pub, "desc": desc})
    return items

def main():
    state = load_state()

    try:
        items = fetch_rss_items()
    except Exception as e:
        tg_send(f"⚠️ تعذر جلب RSS حالياً.\n🕒 {now_ksa_str()}\nتفاصيل مختصرة: {type(e).__name__}")
        return

    new_events = []
    for it in items:
        title = it["title"]
        blob = f"{it['title']} {it['desc']}"
        country = detect_country(blob)
        disease = detect_disease(blob)

        if not country or not disease:
            continue

        region = detect_region(blob)
        sid = sid_from(it["link"], title)
        if sid in state["seen"]:
            continue

        state["seen"][sid] = {"first_seen": now_ksa_str()}
        new_events.append({
            "country": country,
            "region": region,
            "disease": disease,
            "title": title,
            "link": it["link"],
            "pubDate": it["pubDate"],
        })

        if len(new_events) >= MAX_ITEMS_PER_RUN:
            break

    # تقرير عربي
    if not new_events:
        tg_send(
            "📄 تقرير رصد الأمراض الحيوانية (RSS)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            "✅ لا توجد أحداث جديدة مطابقة للدول/الأمراض المحددة.\n"
            "🟢 الحالة التشغيلية: مستقر"
        )
        save_state(state)
        return

    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (RSS)",
        f"🕒 {now_ksa_str()}",
        "════════════════════",
        f"عدد الأحداث الجديدة: {len(new_events)}",
        "════════════════════",
    ]
    for i, e in enumerate(new_events, 1):
        lines.append(
            f"{i}) 🐾 {e['disease']}\n"
            f"   🌍 الدولة: {e['country']}\n"
            f"   📍 المنطقة: {e['region']}\n"
            f"   📰 العنوان: {e['title']}\n"
            f"   🔗 المصدر: {e['link']}"
        )

    tg_send("\n".join(lines))
    save_state(state)

if __name__ == "__main__":
    main()
