import os
import json
import time
import hashlib
import datetime
import re
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "state.json"

# ===== إعدادات سهلة التعديل =====
LOOKBACK_DAYS = 14           # يرجع آخر 14 يوم
MAX_REPORTS = 80             # حد أقصى للتقارير في كل تشغيل
ALERT_THRESHOLD = 70         # إذا وصلت/تجاوزت = تنبيه فوري (عالي)

# الدول اللي تهمك (السعودية + دول التوريد)
COUNTRIES = [
    "Saudi Arabia",
    "Sudan", "Somalia", "Djibouti", "Ethiopia",
    "Australia", "Brazil", "India", "Pakistan", "Jordan"
]

# كلمات مفتاحية للأمراض المهمة (فلتر ذكي بسيط)
DISEASE_KEYWORDS = [
    "peste des petits ruminants",   # PPR
    "rift valley",                  # RVF
    "foot and mouth",               # FMD
    "highly pathogenic avian influenza",
    "avian influenza",
    "african swine fever",
    "lumpy skin disease",
]

# أوزان تقريبية
WEIGHTS = {
    "peste des petits ruminants": 40,
    "rift valley": 45,
    "foot and mouth": 35,
    "highly pathogenic avian influenza": 35,
    "avian influenza": 28,
    "african swine fever": 25,
    "lumpy skin disease": 25,
}

# ===== ترجمة الدول =====
COUNTRY_AR = {
    "Saudi Arabia": "المملكة العربية السعودية",
    "Sudan": "السودان",
    "Somalia": "الصومال",
    "Djibouti": "جيبوتي",
    "Ethiopia": "إثيوبيا",
    "Australia": "أستراليا",
    "Brazil": "البرازيل",
    "India": "الهند",
    "Pakistan": "باكستان",
    "Jordan": "الأردن",
}

# ===== ترجمة الأمراض (قواعد) =====
DISEASE_AR_RULES = [
    ("peste des petits ruminants", "طاعون المجترات الصغيرة (PPR)"),
    ("rift valley", "حمّى الوادي المتصدّع (RVF)"),
    ("foot and mouth", "الحمّى القلاعية (FMD)"),
    ("highly pathogenic avian influenza", "إنفلونزا الطيور عالية الإمراض (HPAI)"),
    ("avian influenza", "إنفلونزا الطيور"),
    ("african swine fever", "حمّى الخنازير الأفريقية (ASF)"),
    ("lumpy skin disease", "مرض الجلد العقدي (LSD)"),
]

# ===== ترجمة المناطق (قاموس + تعريب تلقائي) =====
# السعودية (مناطق/إمارات)
KSA_REGIONS_AR = {
    "Riyadh": "الرياض",
    "Makkah": "مكة المكرمة",
    "Al Madinah": "المدينة المنورة",
    "Madinah": "المدينة المنورة",
    "Eastern Province": "المنطقة الشرقية",
    "Ash Sharqiyah": "المنطقة الشرقية",
    "Al Qassim": "القصيم",
    "Qassim": "القصيم",
    "Asir": "عسير",
    "Tabuk": "تبوك",
    "Hail": "حائل",
    "Jazan": "جازان",
    "Najran": "نجران",
    "Al Bahah": "الباحة",
    "Al Jawf": "الجوف",
    "Jawf": "الجوف",
    "Northern Borders": "الحدود الشمالية",
}

# السودان (ولايات شائعة)
SUDAN_REGIONS_AR = {
    "Khartoum": "الخرطوم",
    "Darfur": "دارفور",
    "North Darfur": "شمال دارفور",
    "South Darfur": "جنوب دارفور",
    "West Darfur": "غرب دارفور",
    "East Darfur": "شرق دارفور",
    "Central Darfur": "وسط دارفور",
    "Kassala": "كسلا",
    "Gedaref": "القضارف",
    "Al Jazirah": "الجزيرة",
    "Gezira": "الجزيرة",
    "Red Sea": "البحر الأحمر",
    "River Nile": "نهر النيل",
    "White Nile": "النيل الأبيض",
    "Blue Nile": "النيل الأزرق",
    "North Kordofan": "شمال كردفان",
    "South Kordofan": "جنوب كردفان",
}

# الصومال (أقاليم شائعة)
SOMALIA_REGIONS_AR = {
    "Banadir": "بنادر",
    "Puntland": "بونتلاند",
    "Somaliland": "صوماليلاند",
    "Galmudug": "غلمدغ",
    "Hirshabelle": "هيرشبيلي",
    "Jubaland": "جوبالاند",
    "South West": "الجنوب الغربي",
}

# إثيوبيا (أقاليم شائعة)
ETHIOPIA_REGIONS_AR = {
    "Oromia": "أوروميا",
    "Amhara": "أمهرا",
    "Tigray": "تيغراي",
    "Somali": "الإقليم الصومالي",
    "Afar": "عفار",
    "Sidama": "سيداما",
    "SNNPR": "جنوب الأمم والقوميات والشعوب",
    "Addis Ababa": "أديس أبابا",
}

# جيبوتي
DJIBOUTI_REGIONS_AR = {
    "Djibouti": "جيبوتي (العاصمة)",
    "Ali Sabieh": "علي صبيح",
    "Dikhil": "دخيل",
    "Tadjourah": "تاجورة",
    "Obock": "أوبوك",
    "Arta": "عرطة",
}

# الأردن (محافظات شائعة)
JORDAN_REGIONS_AR = {
    "Amman": "عمّان",
    "Zarqa": "الزرقاء",
    "Irbid": "إربد",
    "Aqaba": "العقبة",
    "Mafraq": "المفرق",
    "Karak": "الكرك",
    "Balqa": "البلقاء",
    "Madaba": "مادبا",
    "Jerash": "جرش",
    "Ajloun": "عجلون",
    "Tafilah": "الطفيلة",
    "Ma'an": "معان",
}

# ===== WAHIS endpoints =====
BASE = "https://wahis.woah.org"
URL_FILTERS_COUNTRY = BASE + "/pi/reports/filters?columnName=country"
URL_LIST = BASE + "/pi/getReportList"
URL_REPORT = BASE + "/pi/getReport/{rid}"

def now_ksa_str():
    return datetime.datetime.now(tz=KSA_TZ).strftime("%Y-%m-%d %H:%M") + " بتوقيت السعودية"

def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=30)
    r.raise_for_status()

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def stable_id(item: dict) -> str:
    raw = json.dumps(item, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def best_match(target: str, options: list[str]):
    t = (target or "").strip().lower()
    for o in options:
        if t == o.lower():
            return o
    for o in options:
        if t and t in o.lower():
            return o
    return None

def resolve_countries():
    # نطابق أسماء الدول حسب WAHIS لتقليل الأخطاء
    try:
        r = requests.get(URL_FILTERS_COUNTRY, timeout=60)
        r.raise_for_status()
        available = r.json().get("dropDownValue", []) or []
    except Exception:
        return COUNTRIES

    resolved = []
    for c in COUNTRIES:
        m = best_match(c, available)
        resolved.append(m or c)

    out = []
    for x in resolved:
        if x not in out:
            out.append(x)
    return out

def contains_priority_disease(disease: str) -> bool:
    d = (disease or "").lower()
    return any(k in d for k in DISEASE_KEYWORDS)

def score_event(country: str, disease: str) -> int:
    d = (disease or "").lower()

    base = 15
    for k, w in WEIGHTS.items():
        if k in d:
            base = w
            break

    score = base

    # داخل السعودية حساسية أعلى
    if (country or "").lower() in {"saudi arabia", "ksa"}:
        score += 25

    # دول ضمن قائمتك (غير السعودية)
    if country != "Saudi Arabia" and country in COUNTRIES:
        score += 15

    return max(0, min(100, score))

def level(score: int) -> str:
    if score >= 75:
        return "🔴 عالي"
    if score >= 50:
        return "🟠 متوسط"
    return "🟢 منخفض"

def to_ar_country(name: str) -> str:
    if not name:
        return "-"
    return COUNTRY_AR.get(name, name)

def to_ar_disease(name: str) -> str:
    if not name:
        return "-"
    n = name.lower()
    for key, ar in DISEASE_AR_RULES:
        if key in n:
            return ar
    return name

# تعريب تلقائي بسيط للأسماء اللاتينية (لما ما نعرف ترجمتها)
def arabize_latin(text: str) -> str:
    if not text:
        return "-"
    t = text.strip()
    # إذا فيها أحرف عربية أصلاً، رجعها
    if re.search(r"[\u0600-\u06FF]", t):
        return t
    # تغييرات شائعة
    repl = [
        ("-"," "), ("_"," "),
        ("Governorate","محافظة"), ("Region","إقليم"), ("State","ولاية"),
    ]
    for a,b in repl:
        t = t.replace(a,b)

    # تهجئة تقريبية (خفيفة) — الهدف “مقروء” مو ترجمة مثالية
    mapping = [
        ("aa","ا"), ("ee","ي"), ("oo","و"),
        ("kh","خ"), ("sh","ش"), ("th","ث"), ("dh","ذ"), ("gh","غ"),
        ("ch","تش"), ("ph","ف"),
        ("a","ا"), ("b","ب"), ("c","ك"), ("d","د"), ("e","ي"), ("f","ف"),
        ("g","ج"), ("h","ه"), ("i","ي"), ("j","ج"), ("k","ك"), ("l","ل"),
        ("m","م"), ("n","ن"), ("o","و"), ("p","ب"), ("q","ق"), ("r","ر"),
        ("s","س"), ("t","ت"), ("u","و"), ("v","ف"), ("w","و"), ("x","كس"),
        ("y","ي"), ("z","ز"),
    ]
    out = ""
    lower = t.lower()
    i = 0
    while i < len(lower):
        # جرّب الثنائيات أولاً
        if i+1 < len(lower):
            pair = lower[i:i+2]
            hit = next((ar for en, ar in mapping if en == pair), None)
            if hit:
                out += hit
                i += 2
                continue
        ch = lower[i]
        hit = next((ar for en, ar in mapping if en == ch), None)
        out += hit if hit else ch
        i += 1
    # تنظيف فراغات
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out

def to_ar_region(country_en: str, region_en: str) -> str:
    r = (region_en or "").strip()
    if not r:
        return "-"
    # قاموس حسب الدولة
    if country_en == "Saudi Arabia":
        return KSA_REGIONS_AR.get(r, arabize_latin(r))
    if country_en == "Sudan":
        return SUDAN_REGIONS_AR.get(r, arabize_latin(r))
    if country_en == "Somalia":
        return SOMALIA_REGIONS_AR.get(r, arabize_latin(r))
    if country_en == "Ethiopia":
        return ETHIOPIA_REGIONS_AR.get(r, arabize_latin(r))
    if country_en == "Djibouti":
        return DJIBOUTI_REGIONS_AR.get(r, arabize_latin(r))
    if country_en == "Jordan":
        return JORDAN_REGIONS_AR.get(r, arabize_latin(r))
    # دول أخرى: تعريب تلقائي
    return arabize_latin(r)

def wahis_list(countries: list[str], start_date: str, end_date: str):
    payload = {
        "pageNumber": 1,
        "pageSize": 1000000,
        "searchText": "",
        "sortColName": "",
        "sortColOrder": "DESC",
        "reportFilters": {
            "country": countries,
            "region": [],
            "epiEventId": [],
            "diseases": [],
            "diseaseType": [],
            "reason": [],
            "eventDate": {},
            "eventStatus": [],
            "reportHistoryType": [],
            "reportDate": {"startDate": start_date, "endDate": end_date}
        },
        "languageChanged": False
    }
    r = requests.post(URL_LIST, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def wahis_report(report_info_id: int):
    r = requests.get(URL_REPORT.format(rid=report_info_id), timeout=60)
    r.raise_for_status()
    return r.json()

def build_summary(new_events: list[dict], window_days: int) -> str:
    if not new_events:
        return (
            "📄 تقرير رصد الأمراض الحيوانية (WAHIS)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            f"✅ لا توجد أحداث جديدة ضمن آخر {window_days} يوم للدول المحددة.\n"
            "🟢 الحالة التشغيلية: مستقر"
        )

    top = sorted(new_events, key=lambda x: x["score"], reverse=True)[:5]
    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (WAHIS)",
        f"🕒 {now_ksa_str()}",
        "════════════════════",
        f"عدد الأحداث الجديدة: {len(new_events)}",
        "أعلى المخاطر (Top 5):",
    ]
    for x in top:
        lines.append(
            f"- {x['level']} {to_ar_disease(x['disease'])} | {to_ar_country(x['country'])} - {x['region_ar']} | ({x['score']}/100)"
        )
    return "\n".join(lines)

def build_alert(x: dict) -> str:
    return (
        "🚨 تنبيه مرض حيواني (WAHIS)\n\n"
        f"🐾 المرض: {to_ar_disease(x['disease'])}\n"
        f"🌍 الدولة: {to_ar_country(x['country'])}\n"
        f"📍 المنطقة: {x['region_ar']}\n"
        f"⚠️ مستوى الخطر: {x['level']} ({x['score']}/100)\n"
        f"🗓 تاريخ التقرير: {x['reportDate']}\n"
        f"🆔 رقم التقرير: {x['reportId']}\n"
        f"🕒 {now_ksa_str()}"
    )

def main():
    state = load_state()

    end = datetime.date.today()
    start = end - datetime.timedelta(days=LOOKBACK_DAYS)
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    countries = resolve_countries()

    # 1) جلب قائمة التقارير
    data = wahis_list(countries, start_s, end_s)
    reports = data.get("homePageDto", []) or []
    if not reports:
        tg_send(build_summary([], LOOKBACK_DAYS))
        save_state(state)
        return

    reports = reports[:MAX_REPORTS]
    new_events = []

    # 2) قراءة التفاصيل واستخراج الأحداث
    for rep in reports:
        rid = rep.get("reportInfoId")
        if not rid:
            continue

        try:
            time.sleep(0.35)
            full = wahis_report(rid)
        except Exception:
            continue

        outbreak_map = (full.get("eventOutbreakDto") or {}).get("outbreakMap") or {}
        if not outbreak_map:
            continue

        report_id = (full.get("reportDto") or {}).get("reportId", "") or rep.get("reportId", "")
        report_date = (full.get("reportDto") or {}).get("reportDate", "") or rep.get("reportDate", "")

        for _, ob in outbreak_map.items():
            country = ob.get("country") or rep.get("country", "")
            region = ob.get("region") or ob.get("admin1") or ""
            disease = ob.get("disease") or rep.get("disease", "")

            if not disease:
                continue
            if not contains_priority_disease(disease):
                continue

            score = score_event(country, disease)
            item = {
                "country": country,
                "region": region or "-",
                "region_ar": to_ar_region(country, region or "-"),
                "disease": disease,
                "score": score,
                "level": level(score),
                "reportId": report_id,
                "reportDate": report_date,
            }

            sid = stable_id(item)
            if sid in state["seen"]:
                continue

            state["seen"][sid] = {"first_seen": now_ksa_str()}
            new_events.append(item)

    # 3) إرسال التقرير + التنبيهات العالية
    tg_send(build_summary(new_events, LOOKBACK_DAYS))

    high = [x for x in new_events if x["score"] >= ALERT_THRESHOLD]
    high = sorted(high, key=lambda x: x["score"], reverse=True)[:10]
    for x in high:
        tg_send(build_alert(x))

    save_state(state)

if __name__ == "__main__":
    main()
