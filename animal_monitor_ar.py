import os
import re
import json
import hashlib
import datetime
import requests
import xml.etree.ElementTree as ET

# =========================
# الإعدادات الأساسية
# =========================
BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "state.json"

# =========================
# إعدادات التشغيل
# =========================
MAX_ITEMS = 10
MAX_AGE_DAYS = 180

# الدول المستهدفة
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

# الأمراض المحددة
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

# اختصارات الأمراض مع شرط وجود سياق
DISEASE_ABBR = {
    "rvf": "حمّى الوادي المتصدّع (RVF)",
    "ppr": "طاعون المجترات الصغيرة (PPR)",
    "fmd": "الحمّى القلاعية (FMD)",
    "h5n1": "إنفلونزا الطيور (H5N1)",
}

# كلمات سياق مرضي
DISEASE_CONTEXT = [
    "outbreak", "case", "cases", "fever", "virus", "infection",
    "detected", "confirmed", "epidemic", "surveillance",
    "vaccination", "animal health", "livestock disease",
    "veterinary", "animal disease", "zoonotic"
]

# المناطق الشائعة بالعربي
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
    "north darfur": "شمال دارفور",
    "south darfur": "جنوب دارفور",
    "central darfur": "وسط دارفور",
    "oromia": "أوروميا",
    "amhara": "أمهرا",
    "addis ababa": "أديس أبابا",
    "banadir": "بنادر",
    "puntland": "بونتلاند",
    "somaliland": "صوماليلاند",
    "amman": "عمّان",
    "irbid": "إربد",
    "zarqa": "الزرقاء",
    "aqaba": "العقبة",
}

GOOGLE_RSS = "https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"

# =========================
# أدوات الوقت
# =========================
def now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)

def now_ksa_str():
    return now_ksa().strftime("%Y-%m-%d %H:%M") + " بتوقيت السعودية"

# =========================
# Telegram
# =========================
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    parts = [text[i:i+3500] for i in range(0, len(text), 3500)]

    for part in parts:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": part,
                "disable_web_page_preview": True
            },
            timeout=30
        )
        r.raise_for_status()

# =========================
# حفظ الحالة
# =========================
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def make_sid(url, title):
    raw = (url or "") + "|" + (title or "")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

# =========================
# كشف البيانات
# =========================
def detect_country(text):
    low = (text or "").lower()
    for key, value in COUNTRY_KEYS.items():
        if key in low:
            return value
    return None

def detect_region(text, country_ar):
    low = (text or "").lower()
    for key, value in REGION_AR.items():
        if key in low:
            return value
    return "داخل الدولة" if country_ar else "غير محدد"

def detect_disease(text):
    low = (text or "").lower()

    # أولاً: أسماء كاملة
    for key, value in DISEASE_FULL.items():
        if key in low:
            return value

    # ثانيًا: اختصارات بشرط وجود سياق
    has_context = any(ctx in low for ctx in DISEASE_CONTEXT)
    if has_context:
        for key, value in DISEASE_ABBR.items():
            if re.search(rf"\b{key}\b", low):
                return value

    # ثالثًا: تنبيه بيطري عام إذا ظهر سياق مرضي واضح
    generic_signals = [
        "animal disease", "livestock disease", "animal health alert",
        "veterinary outbreak", "veterinary alert", "zoonotic disease"
    ]
    if any(sig in low for sig in generic_signals):
        return "تنبيه صحي بيطري عام"

    return None

def classify_item(title: str, desc: str) -> str:
    low = f"{title} {desc}".lower()

    if "outbreak" in low or "confirmed" in low or "cases" in low or "detected" in low:
        return "🟥 تفشي/حالات"
    if "ban" in low or "imports" in low or "import ban" in low or "suspend" in low:
        return "🟦 قرار/منع استيراد"
    if "study" in low or "investigation" in low or "characterization" in low or "research" in low:
        return "🟩 دراسة/بحث"
    return "🟨 خبر عام"

# =========================
# فلترة التاريخ
# =========================
def within_days(pub: str, days: int) -> bool:
    if not pub:
        return True

    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(pub, fmt).replace(tzinfo=datetime.timezone.utc)
            age = now_ksa() - dt.astimezone(KSA_TZ)
            return age.days <= days
        except Exception:
            continue

    return True

# =========================
# جلب Google News RSS
# =========================
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

# =========================
# البرنامج الرئيسي
# =========================
def main():
    state = load_state()

    # استعلامات متعددة لزيادة فرص الالتقاط
    queries = [
        '("rift valley fever" OR RVF OR "peste des petits ruminants" OR PPR OR "foot and mouth disease" OR FMD OR "avian influenza" OR H5N1 OR "lumpy skin disease" OR anthrax OR rabies) (Saudi Arabia OR Sudan OR Somalia OR Ethiopia OR Djibouti OR Jordan OR India)',
        '("animal disease" OR "livestock disease" OR "animal health alert" OR "veterinary outbreak") (Saudi Arabia OR Sudan OR Somalia OR Ethiopia OR Djibouti OR Jordan OR India)',
    ]

    items = []
    status_notes = []

    for q in queries:
        try:
            items.extend(fetch_google(q))
            status_notes.append("Google=OK")
            break
        except Exception as e:
            status_notes.append(f"Google={type(e).__name__}")

    if not items:
        tg_send(
            "⚠️ تعذر جلب الأخبار حالياً.\n"
            f"🕒 {now_ksa_str()}\n"
            f"حالة المصدر: {'؛ '.join(status_notes)}"
        )
        return

    new_events = []

    for it in items:
        if not within_days(it.get("pub", ""), MAX_AGE_DAYS):
            continue

        blob = f"{it.get('title','')} {it.get('desc','')}"

        disease = detect_disease(blob)
        country = detect_country(blob)

        if not disease or not country:
            continue

        region = detect_region(blob, country)
        label = classify_item(it.get("title", ""), it.get("desc", ""))

        sid = make_sid(it.get("link", ""), it.get("title", ""))
        if sid in state["seen"]:
            continue

        state["seen"][sid] = {
            "first_seen": now_ksa_str(),
            "source": it["source"]
        }

        new_events.append({
            "source": it["source"],
            "label": label,
            "disease": disease,
            "country": country,
            "region": region,
            "title": it.get("title", ""),
            "link": it.get("link", ""),
        })

        if len(new_events) >= MAX_ITEMS:
            break

    if not new_events:
        tg_send(
            "📄 تقرير رصد الأمراض الحيوانية (مستقل)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            "✅ لا توجد إشارات جديدة مطابقة حالياً.\n"
            f"ℹ️ حالة المصدر: {'؛ '.join(status_notes)}"
        )
        save_state(state)
        return

    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (مستقل)",
        f"🕒 {now_ksa_str()}",
        "════════════════════",
        f"عدد الإشارات الجديدة: {len(new_events)}",
        f"ℹ️ حالة المصدر: {'؛ '.join(status_notes)}",
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
