import os, re, json, hashlib, datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "state.json"

# ===== إعدادات =====
TIMESPAN = "12h"         # آخر 12 ساعة (تقدر تخليها 1d)
MAX_ITEMS = 12           # كم خبر بالتقرير

COUNTRY_KEYS = {
    "saudi arabia": "المملكة العربية السعودية",
    "sudan": "السودان",
    "somalia": "الصومال",
    "ethiopia": "إثيوبيا",
    "djibouti": "جيبوتي",
    "jordan": "الأردن",
}

# كلمات للأمراض الحيوانية (إنجليزي لأن الأخبار غالباً كذا)
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

# مناطق (قاموس + fallback)
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

def sid(url: str, title: str):
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

def extract_region(text: str):
    """
    يحاول يلقط منطقة من العنوان مثل (CENTRAL DARFUR) أو كلمات داخل النص.
    """
    low = (text or "").lower()

    # 1) أي شيء بين أقواس
    m = re.findall(r"\(([^)]+)\)", text or "")
    candidates = [c.strip() for c in m if c.strip()]

    # 2) أو حاول يطابق من القاموس مباشرة من النص
    for k, ar in REGION_AR.items():
        if k in low:
            return ar

    # 3) لو فيه أقواس جرّب ترجمتها
    for c in candidates:
        key = c.lower().strip()
        if key in REGION_AR:
            return REGION_AR[key]

    return "غير محدد"

def gdelt_query_url():
    # نص بحث: أمراض + مواشي + دولك
    diseases = "(" + " OR ".join([f'"{k}"' for k in ["ppr","rift valley","foot and mouth","avian influenza","lumpy skin","anthrax","rabies"]]) + ")"
    animals = '("livestock" OR cattle OR sheep OR goat OR camels OR poultry OR "animal disease")'
    countries = "(" + " OR ".join([f'"{c}"' for c in ["Saudi Arabia","Sudan","Somalia","Ethiopia","Djibouti","Jordan"]]) + ")"
    q = f"{diseases} AND {animals} AND {countries}"

    # GDELT DOC API
    return (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={requests.utils.quote(q)}"
        f"&mode=artlist&format=json&sort=datedesc&maxrecords=250&timespan={TIMESPAN}"
    )

def main():
    state = load_state()

    try:
        url = gdelt_query_url()
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 (compatible; KSA-Animal-Health-Monitor/1.0)"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        tg_send(f"⚠️ تعذر جلب الأخبار حالياً.\n🕒 {now_ksa_str()}\nالسبب: {type(e).__name__}")
        return

    arts = data.get("articles", []) or []
    new_items = []

    for a in arts:
        title = (a.get("title") or "").strip()
        link = (a.get("url") or "").strip()
        if not title or not link:
            continue

        blob = f"{title} {a.get('sourceCountry','')} {a.get('domain','')}"
        country_ar = detect_country(blob)
        disease_ar = detect_disease(blob)
        if not country_ar or not disease_ar:
            continue

        region_ar = extract_region(title)

        k = sid(link, title)
        if k in state["seen"]:
            continue

        state["seen"][k] = {"first_seen": now_ksa_str()}
        new_items.append({
            "disease": disease_ar,
            "country": country_ar,
            "region": region_ar,
            "title": title,
            "url": link,
            "date": (a.get("seendate") or "").replace("T"," ").replace("Z",""),
        })

        if len(new_items) >= MAX_ITEMS:
            break

    if not new_items:
        tg_send(
            "📄 تقرير رصد الأمراض الحيوانية (أخبار عالمية)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            f"✅ لا توجد أخبار جديدة مطابقة ضمن آخر {TIMESPAN}.\n"
            "🟢 الحالة التشغيلية: مستقر"
        )
        save_state(state)
        return

    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (أخبار عالمية)",
        f"🕒 {now_ksa_str()}",
        "════════════════════",
        f"عدد الإشارات الجديدة: {len(new_items)}",
        "════════════════════",
    ]

    for i, x in enumerate(new_items, 1):
        lines.append(
            f"{i}) 🐾 {x['disease']}\n"
            f"   🌍 الدولة: {x['country']}\n"
            f"   📍 المنطقة: {x['region']}\n"
            f"   📰 العنوان: {x['title']}\n"
            f"   🔗 الرابط: {x['url']}"
        )

    tg_send("\n".join(lines))
    save_state(state)

if __name__ == "__main__":
    main()
