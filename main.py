import os, re, json, hashlib, datetime
import requests
import xml.etree.ElementTree as ET

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "state.json"

# ===== إعدادات =====
MAX_ITEMS = 12   # أقصى عدد عناصر في كل تقرير

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
    "north darfur": "شمال دارفور",
    "central darfur": "وسط دارفور",
    "south darfur": "جنوب دارفور",
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

# Google News RSS template
# ملاحظة: نستخدم EN عشان كشف الكلمات أسهل + النتائج أغزر
GOOGLE_RSS = "https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"

def now_ksa_str():
    return datetime.datetime.now(tz=KSA_TZ).strftime("%Y-%m-%d %H:%M") + " بتوقيت السعودية"

def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=30)
    r.raise_for_status()

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def make_sid(url: str, title: str) -> str:
    raw = (url or "") + "|" + (title or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def detect_country(text: str):
    low = (text or "").lower()
    for k, ar in COUNTRY_KEYS.items():
        if k in low:
            return ar
    return None

def detect_disease(text: str):
    low = (text or "").lower()
    for k, ar in DISEASE_KEYS.items():
        if k in low:
            return ar
    return None

def detect_region(text: str):
    low = (text or "").lower()
    for k, ar in REGION_AR.items():
        if k in low:
            return ar
    return "غير محدد"

def fetch_google_rss(query: str):
    url = GOOGLE_RSS.format(q=requests.utils.quote(query))
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AnimalHealthIntel/1.0)"}
    r = requests.get(url, timeout=45, headers=headers)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    items = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        desc = (it.findtext("description") or "").strip()
        items.append({"title": title, "link": link, "pubDate": pub, "desc": desc})
    return items

def main():
    state = load_state()

    # نبني 3-4 استعلامات فقط (عشان ما نكثر على Google)
    queries = [
        # أخبار عن الأمراض + مواشي + الدول
        '("PPR" OR "peste des petits ruminants" OR "rift valley fever" OR "foot and mouth disease" OR "avian influenza" OR "lumpy skin disease") (livestock OR cattle OR sheep OR goats) (Saudi Arabia OR Sudan OR Somalia OR Ethiopia OR Djibouti OR Jordan)',
        # استعلام مركز على PPR في دول التوريد
        '("peste des petits ruminants" OR PPR) (Sudan OR Somalia OR Ethiopia OR Djibouti)',
        # استعلام مركز على RVF و FMD
        '("rift valley fever" OR RVF OR "foot and mouth disease" OR FMD) (Sudan OR Somalia OR Ethiopia OR Saudi Arabia)',
    ]

    all_items = []
    try:
        for q in queries:
            all_items.extend(fetch_google_rss(q))
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "غير معروف")
        tg_send(f"⚠️ تعذر جلب RSS من Google News حالياً.\n🕒 {now_ksa_str()}\nرمز الخطأ: {status}")
        return
    except Exception as e:
        tg_send(f"⚠️ تعذر جلب الأخبار حالياً.\n🕒 {now_ksa_str()}\nالسبب: {type(e).__name__}")
        return

    new_events = []
    for it in all_items:
        title = it["title"]
        link = it["link"]
        blob = f"{title} {it.get('desc','')}"
        country = detect_country(blob)
        disease = detect_disease(blob)
        if not country or not disease:
            continue

        region = detect_region(blob)
        sid = make_sid(link, title)
        if sid in state["seen"]:
            continue

        state["seen"][sid] = {"first_seen": now_ksa_str()}
        new_events.append({
            "disease": disease,
            "country": country,
            "region": region,
            "title": title,
            "link": link,
        })

        if len(new_events) >= MAX_ITEMS:
            break

    if not new_events:
        tg_send(
            "📄 تقرير رصد الأمراض الحيوانية (أخبار Google)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            "✅ لا توجد أخبار جديدة مطابقة للدول/الأمراض المحددة.\n"
            "🟢 الحالة التشغيلية: مستقر"
        )
        save_state(state)
        return

    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (أخبار Google)",
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
