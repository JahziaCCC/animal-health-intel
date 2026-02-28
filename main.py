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

MAX_ITEMS = 8

# ===== الدول المهمة =====
COUNTRY_KEYS = {
    "saudi arabia": "المملكة العربية السعودية",
    "sudan": "السودان",
    "somalia": "الصومال",
    "ethiopia": "إثيوبيا",
    "djibouti": "جيبوتي",
    "jordan": "الأردن",
}

# ===== الأمراض =====
DISEASE_KEYS = {
    "rift valley fever": "حمّى الوادي المتصدّع (RVF)",
    "peste des petits ruminants": "طاعون المجترات الصغيرة (PPR)",
    "foot and mouth disease": "الحمّى القلاعية (FMD)",
    "avian influenza": "إنفلونزا الطيور",
    "lumpy skin disease": "مرض الجلد العقدي (LSD)",
    "anthrax": "الجمرة الخبيثة",
    "rabies": "داء الكلب",
}

# ===== RSS عالمي (ProMED) =====
PROMED_RSS = "https://promedmail.org/promed-posts?format=rss"

# ===== وقت =====
def now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)

def now_ksa_str():
    return now_ksa().strftime("%Y-%m-%d %H:%M") + " بتوقيت السعودية"

# ===== Telegram =====
def tg_send(text):
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

# ===== جلب ProMED =====
def fetch_promed():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(PROMED_RSS, timeout=45, headers=headers)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    items = []

    for it in root.findall(".//item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "desc": (it.findtext("description") or "").strip(),
        })

    return items

# ===== MAIN =====
def main():

    state = load_state()

    try:
        items = fetch_promed()
    except Exception as e:
        tg_send(
            "⚠️ تعذر جلب بيانات ProMED حالياً.\n"
            f"🕒 {now_ksa_str()}\n"
            f"السبب: {type(e).__name__}"
        )
        return

    new_events = []

    for it in items:

        blob = f"{it['title']} {it['desc']}"

        country = detect_country(blob)
        disease = detect_disease(blob)

        if not country or not disease:
            continue

        sid = make_sid(it["link"], it["title"])
        if sid in state["seen"]:
            continue

        state["seen"][sid] = {"first_seen": now_ksa_str()}

        new_events.append({
            "country": country,
            "disease": disease,
            "title": it["title"],
            "link": it["link"]
        })

        if len(new_events) >= MAX_ITEMS:
            break

    if not new_events:
        tg_send(
            "📄 تقرير رصد الأمراض الحيوانية (ProMED العالمي)\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            "🟢 لا توجد إشارات جديدة حالياً."
        )
        save_state(state)
        return

    lines = [
        "📄 تقرير رصد الأمراض الحيوانية (ProMED العالمي)",
        f"🕒 {now_ksa_str()}",
        "════════════════════",
        f"عدد الإشارات الجديدة: {len(new_events)}",
        "════════════════════",
    ]

    for i, e in enumerate(new_events, 1):
        lines.append(
            f"{i}) 🐾 {e['disease']}\n"
            f"   🌍 الدولة: {e['country']}\n"
            f"   📰 العنوان: {e['title']}\n"
            f"   🔗 الرابط: {e['link']}"
        )

    tg_send("\n".join(lines))
    save_state(state)

if __name__ == "__main__":
    main()
