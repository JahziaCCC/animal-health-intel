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
MAX_AGE_DAYS = 120  # خليها 90-180 حسب رغبتك

# دول تحت المراقبة (تقدر تزيد)
COUNTRY_KEYS = {
    "saudi arabia": "المملكة العربية السعودية",
    "kingdom of saudi arabia": "المملكة العربية السعودية",
    "ksa": "المملكة العربية السعودية",
    "sudan": "السودان",
    "somalia": "الصومال",
    "ethiopia": "إثيوبيا",
    "djibouti": "جيبوتي",
    "jordan": "الأردن",
    "india": "الهند",
    "pakistan": "باكستان",
    "australia": "أستراليا",
    "brazil": "البرازيل",
}

# أمراضك (أسماء كاملة + اختصار بشرط سياق)
DISEASE_FULL = {
    "rift valley fever": "حمّى الوادي المتصدّع (RVF)",
    "peste des petits ruminants": "طاعون المجترات الصغيرة (PPR)",
    "foot and mouth disease": "الحمّى القلاعية (FMD)",
    "avian influenza": "إنفلونزا الطيور",
    "highly pathogenic avian influenza": "إنفلونزا الطيور عالية الإمراض (HPAI)",
    "lumpy skin disease": "مرض الجلد العقدي (LSD)",
    "anthrax": "الجمرة الخبيثة",
    "rabies": "داء الكلب",
}

DISEASE_ABBR = {
    "rvf": "حمّى الوادي المتصدّع (RVF)",
    "ppr": "طاعون المجترات الصغيرة (PPR)",
    "fmd": "الحمّى القلاعية (FMD)",
    "h5n1": "إنفلونزا الطيور (H5N1)",
}

DISEASE_CONTEXT = [
    "outbreak", "case", "cases", "fever", "virus", "infection",
    "detected", "confirmed", "epidemic", "surveillance", "vaccination",
]

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
    "al bahah": "الباحة",
    "al jawf": "الجوف",
    "northern borders": "الحدود الشمالية",
    "khartoum": "الخرطوم",
    "darfur": "دارفور",
    "oromia": "أوروميا",
    "amhara": "أمهرا",
    "addis ababa": "أديس أبابا",
    "amman": "عمّان",
    "irbid": "إربد",
}

# مصادر
PROMED_RSS = "https://promedmail.org/promed-posts?format=rss"
GOOGLE_RSS = "https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"
GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"


# ===== وقت =====
def now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)

def now_ksa_str():
    return now_ksa().strftime("%Y-%m-%d %H:%M") + " بتوقيت السعودية"


# ===== Telegram =====
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    parts = [text[i:i+3500] for i in range(0, len(text), 3500)]
    for p in parts:
        r = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": p, "disable_web_page_preview": True},
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


# ===== كشف =====
def detect_country(text):
    low = (text or "").lower()
    for k, v in COUNTRY_KEYS.items():
        if k in low:
            return v
    return None

def detect_region(text, country_ar):
    low = (text or "").lower()
    for k, v in REGION_AR.items():
        if k in low:
            return v
    return "داخل الدولة" if country_ar else "غير محدد"

def detect_disease(text):
    low = (text or "").lower()

    # 1) أسماء كاملة
    for k, v in DISEASE_FULL.items():
        if k in low:
            return v

    # 2) اختصار بشرط سياق
    has_context = any(c in low for c in DISEASE_CONTEXT)
    if has_context:
        for k, v in DISEASE_ABBR.items():
            if re.search(rf"\b{k}\b", low):
                return v

    return None

def classify_item(title: str, desc: str) -> str:
    low = f"{title} {desc}".lower()
    if "outbreak" in low or "confirmed" in low or "cases" in low:
        return "🟥 تفشي/حالات"
    if "ban" in low or "imports" in low or "import ban" in low:
        return "🟦 قرار/منع استيراد"
    if "study" in low or "investigation" in low or "characterization" in low:
        return "🟩 دراسة/بحث"
    return "🟨 خبر عام"


# ===== فلترة العمر (لـ GDELT/Google) =====
def within_days(iso_or_pubdate: str, days: int) -> bool:
    if not iso_or_pubdate:
        return True
    # GDELT ISO: 2026-02-28T00:00:00Z
    try:
        if "T" in iso_or_pubdate and iso_or_pubdate.endswith("Z"):
            dt = datetime.datetime.strptime(iso_or_pubdate, "%Y-%m-%dT%H:%M:%SZ")
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            # Google pubDate: Sat, 28 Feb 2026 00:00:00 GMT
            dt = datetime.datetime.strptime(iso_or_pubdate, "%a, %d %b %Y %H:%M:%S %Z")
            dt = dt.replace(tzinfo=datetime.timezone.utc)

        age = now_ksa() - dt.astimezone(KSA_TZ)
        return age.days <= days
    except:
        return True


# ===== جلب ProMED RSS =====
def fetch_promed():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(PROMED_RSS, timeout=45, headers=headers)
    r.raise_for_status()
    root = ET.fromstring(r.text)

    items = []
    for it in root.findall(".//item"):
        items.append({
            "source": "ProMED",
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "pub": (it.findtext("pubDate") or "").strip(),
            "desc": (it.findtext("description") or "").strip(),
        })
    return items


# ===== جلب Google News RSS =====
def fetch_google(query):
    url = GOOGLE_RSS.format(q=requests.utils.quote(query))
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, timeout=45, headers=headers)
    r.raise_for_status()
    root = ET.fromstring(r.text)

    items = []
    for it in root.findall(".//item"):
        items.append({
            "source": "Google News",
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "pub": (it.findtext("pubDate") or "").strip(),
            "desc": (it.findtext("description") or "").strip(),
        })
    return items


# ===== جلب GDELT =====
def fetch_gdelt(query, maxrecords=50):
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "sort": "HybridRel",
        "maxrecords": str(maxrecords),
        "formatting": "json",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(GDELT_DOC, params=params, timeout=45, headers=headers)
    r.raise_for_status()
    data = r.json()

    items = []
    for a in data.get("articles", []) or []:
        items.append({
            "source": "GDELT",
            "title": (a.get("title") or "").strip(),
            "link": (a.get("url") or "").strip(),
            "pub": (a.get("seendate") or "").strip(),  # ISO Z
            "desc": (a.get("sourceCountry") or "") + " " + (a.get("snippet") or ""),
        })
    return items


def main():
    state = load_state()

    # استعلام واسع لكن “ذكي” داخل الكود هو اللي يفلتر
    countries_q = "(Saudi Arabia OR Sudan OR Somalia OR Ethiopia OR Djibouti OR Jordan OR India)"
    diseases_q = '("rift valley fever" OR RVF OR "peste des petits ruminants" OR PPR OR "foot and mouth disease" OR FMD OR "avian influenza" OR H5N1 OR "lumpy skin disease")'
    context_q = "(outbreak OR cases OR virus OR fever OR confirmed OR detected OR surveillance OR vaccination)"

    google_query = f"{diseases_q} {context_q} {countries_q}"
    gdelt_query = f'{diseases_q} {context_q} {countries_q}'

    all_items = []
    errors = []

    # 1) ProMED
    try:
        all_items.extend(fetch_promed())
    except Exception as e:
        errors.append(f"ProMED={type(e).__name__}")

    # 2) GDELT
    try:
        all_items.extend(fetch_gdelt(gdelt_query, maxrecords=60))
    except Exception as e:
        errors.append(f"GDELT={type(e).__name__}")

    # 3) Google News (fallback)
    try:
        all_items.extend(fetch_google(google_query))
    except Exception as e:
        errors.append(f"Google={type(e).__name__}")

    # لو كلهم فشلوا
    if not all_items:
        tg_send(
            "⚠️ تعذر جلب المصادر حالياً.\n"
            f"🕒 {now_ksa_str()}\n"
            f"تفاصيل: {', '.join(errors) if errors else 'غير معروف'}"
        )
        return

    new_events = []

    for it in all_items:
        # فلتر العمر (لـ Google/GDELT – ProMED أحياناً بدون pubDate واضح)
        if it["source"] in ("Google News", "GDELT"):
            if not within_days(it.get("pub", ""), MAX_AGE_DAYS):
                continue

        blob = f"{it.get('title','')} {it.get('desc','')}"
        country = detect_country(blob)
        disease = detect_disease(blob)
        if not country or not disease:
            continue

        region = detect_region(blob, country)
        label = classify_item(it.get("title",""), it.get("desc",""))

        sid = make_sid(it.get("link",""), it.get("title",""))
        if sid in state["seen"]:
            continue
        state["seen"][sid] = {"first_seen": now_ksa_str(), "source": it["source"]}

        new_events.append({
            "source": it["source"],
            "country": country,
            "disease": disease,
            "region": region,
            "label": label,
            "title": it.get("title",""),
            "link": it.get("link",""),
        })

        if len(new_events) >= MAX_ITEMS:
            break

    if not new_events:
        tg_send(
            "📄 تقرير رصد الأمراض الحيوانية (مصادر عالمية متعددة)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            "✅ لا توجد إشارات جديدة مطابقة حالياً.\n"
            f"ℹ️ حالة المصادر: {('✅' if not errors else '؛ '.join(errors))}"
        )
        save_state(state)
        return

    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (مصادر عالمية متعددة)",
        f"🕒 {now_ksa_str()}",
        "════════════════════",
        f"عدد الإشارات الجديدة: {len(new_events)}",
        f"ℹ️ حالة المصادر: {('✅' if not errors else '؛ '.join(errors))}",
        "════════════════════",
    ]

    for i, e in enumerate(new_events, 1):
        lines.append(
            f"{i}) [{e['source']}] {e['label']}  🐾 {e['disease']}\n"
            f"   🌍 الدولة: {e['country']}\n"
            f"   📍 المنطقة: {e['region']}\n"
            f"   📰 العنوان: {e['title']}\n"
            f"   🔗 الرابط: {e['link']}"
        )

    tg_send("\n".join(lines))
    save_state(state)


if __name__ == "__main__":
    main()
