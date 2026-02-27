import os
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

COUNTRIES = [
    "Saudi Arabia",
    "Sudan",
    "Somalia",
    "Ethiopia",
    "Djibouti",
    "Jordan"
]

DISEASES = [
    "طاعون المجترات الصغيرة (PPR)",
    "حمّى الوادي المتصدع (RVF)",
    "الحمّى القلاعية (FMD)",
    "إنفلونزا الطيور",
    "مرض الجلد العقدي"
]

def now():
    return datetime.datetime.now(tz=KSA_TZ).strftime("%Y-%m-%d %H:%M")

def send(msg):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg
    }, timeout=30)

def main():

    msg = (
        "📄 تقرير رصد الأمراض الحيوانية\n\n"
        f"🕒 {now()} بتوقيت السعودية\n"
        "════════════════════\n"
        "🌍 الدول تحت المراقبة:\n"
        + "\n".join([f"- {c}" for c in COUNTRIES])
        + "\n\n🐄 الأمراض ذات الأولوية:\n"
        + "\n".join([f"- {d}" for d in DISEASES])
        + "\n\n🟢 النظام يعمل بشكل طبيعي."
    )

    send(msg)

if __name__ == "__main__":
    main()
