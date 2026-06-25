#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GE Aerospace Staj / Intern Ilan Takip Botu
==========================================

GE Aerospace'in kariyer sitesinde (Workday) yeni bir staj/intern ilani
yayinlandiginda sana Telegram'dan bildirim gonderir.

Veri kaynagi: GE Aerospace Workday'in herkese acik arama API'si
(geaerospace.wd5.myworkdayjobs.com). Login GEREKMEZ, tarayici GEREKMEZ;
duz bir POST istegiyle JSON ilan listesi cekilir.

Bu bot, daha onceki ITU kontenjan botuyla AYNI Telegram botunu ve AYNI
GitHub secret'larini (ITU_BOT_TOKEN, ITU_CHAT_ID) kullanir -- yeni bir
secret olusturmana gerek yok. Ayni repoya koyup ikinci bir workflow ile
calistirabilirsin.

Calistirma modlari:
  python3 ge_intern_bot.py            -> surekli dongu (her INTERVAL sn)
  python3 ge_intern_bot.py --once     -> tek seferlik kontrol (cron/Actions icin)
  python3 ge_intern_bot.py --status   -> eslesen ilanlari listeler (bildirim atmaz)
  python3 ge_intern_bot.py --test     -> Telegram baglantisini test eder (tek mesaj)
"""

import json
import os
import sys
import time
import html
import datetime
import urllib.request

# =====================================================================
# AYARLAR  -- burayi kendine gore ayarla
# =====================================================================

# Hangi kelimeleri arayalim? (Workday arama kutusuna yazar gibi)
# Birden fazla terim verebilirsin; her biri ayri aranir ve sonuclar birlesir.
ARAMA_TERIMLERI = ["intern", "internship", "co-op", "student"]

# Lokasyon filtresi. BOS birakirsan TUM lokasyonlar gelir.
# Ornek: ["Turkey", "Istanbul"] ya da ["United States"] gibi.
LOKASYON_FILTRE = []

# Baslik filtresi. BOS birakirsan tum basliklar gelir.
# Ornek: ["mechanical", "design", "aerospace"] -> sadece bunlari iceren ilanlar.
BASLIK_FILTRE = []

# Telegram bilgilerin -- ITU botuyla AYNI secret'lar.
TELEGRAM_TOKEN = os.environ.get("ITU_BOT_TOKEN", "BURAYA_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("ITU_CHAT_ID", "BURAYA_CHAT_ID")

# Kontrol araligi (saniye). Ilanlar dakika dakika degismedigi icin
# 30 dakika (1800 sn) makul. Cok sik kontrol etmeye gerek yok.
INTERVAL = 1800

# =====================================================================
# Sabitler -- normalde dokunmana gerek yok
# =====================================================================

HOST = "https://geaerospace.wd5.myworkdayjobs.com"
TENANT = "geaerospace"
SITE = "GE_ExternalSite"
JOBS_API = f"{HOST}/wday/cxs/{TENANT}/{SITE}/jobs"
JOB_URL_BASE = f"{HOST}/en-US/{SITE}"

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ge_intern_state.json")
USER_AGENT = "Mozilla/5.0 (kisisel ilan takip botu)"


def zaman():
    return datetime.datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(f"[{zaman()}] {msg}", flush=True)


# ---------------------------------------------------------------------
# Workday API'den ilan cekme
# ---------------------------------------------------------------------
def _api_post(body):
    veri = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        JOBS_API, data=veri,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def ilanlari_cek():
    """Tum arama terimlerini gezer, filtreler ve {id: {...}} dondurur."""
    ham = {}
    for terim in ARAMA_TERIMLERI:
        offset = 0
        while True:
            data = _api_post({
                "appliedFacets": {},
                "limit": 20,
                "offset": offset,
                "searchText": terim,
            })
            postings = data.get("jobPostings", []) or []
            total = data.get("total", 0)
            for p in postings:
                bullets = p.get("bulletFields") or []
                jid = bullets[0] if bullets else p.get("externalPath", "")
                if not jid:
                    continue
                ham[jid] = {
                    "id": jid,
                    "title": (p.get("title") or "").strip(),
                    "location": (p.get("locationsText") or "").strip(),
                    "posted": (p.get("postedOn") or "").strip(),
                    "url": JOB_URL_BASE + (p.get("externalPath") or ""),
                }
            offset += 20
            if not postings or offset >= total:
                break

    # filtreler
    sonuc = {}
    for jid, j in ham.items():
        if LOKASYON_FILTRE and not any(f.lower() in j["location"].lower() for f in LOKASYON_FILTRE):
            continue
        if BASLIK_FILTRE and not any(f.lower() in j["title"].lower() for f in BASLIK_FILTRE):
            continue
        sonuc[jid] = j
    return sonuc


# ---------------------------------------------------------------------
# Durum (state)
# ---------------------------------------------------------------------
def state_yukle():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"initialized": False, "ids": {}}


def state_kaydet(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log(f"UYARI: durum dosyasi yazilamadi: {e}")


# ---------------------------------------------------------------------
# Telegram bildirim
# ---------------------------------------------------------------------
def telegram_gonder(metin):
    if "BURAYA" in TELEGRAM_TOKEN or "BURAYA" in TELEGRAM_CHAT_ID:
        log("UYARI: Telegram ayarlanmamis -> mesaj sadece konsola yazildi:")
        print("    " + metin.replace("\n", "\n    "))
        return False
    import urllib.parse
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    veri = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": metin,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=veri, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        log(f"UYARI: Telegram gonderilemedi: {e}")
        return False


def bildirim_metni(j):
    return (
        f"🛩️ <b>YENI GE AEROSPACE ILANI</b>\n"
        f"<b>{html.escape(j['title'])}</b>\n"
        f"📍 {html.escape(j['location'])}\n"
        f"🕒 {html.escape(j['posted'])}\n"
        f"➡️ {j['url']}"
    )


# ---------------------------------------------------------------------
# Tek kontrol turu
# ---------------------------------------------------------------------
def kontrol_et(state, sessiz=False):
    ilanlar = ilanlari_cek()
    bilinen = state.get("ids", {})

    if not state.get("initialized"):
        # Ilk calisma: mevcut tum ilanlari sessizce kaydet (spam yapma).
        state["ids"] = {jid: j["title"] for jid, j in ilanlar.items()}
        state["initialized"] = True
        if not sessiz:
            log(f"Ilk calisma: {len(ilanlar)} ilan temel alindi (bildirim atilmadi).")
        return

    yeni = [j for jid, j in ilanlar.items() if jid not in bilinen]

    if not sessiz:
        if yeni:
            log(f"{len(yeni)} YENI ilan bulundu.")
        else:
            log(f"Yeni ilan yok. ({len(ilanlar)} ilan takip ediliyor)")

    for j in yeni:
        if not sessiz:
            log(f"  YENI: {j['title']} | {j['location']}")
            telegram_gonder(bildirim_metni(j))

    state["ids"] = {jid: j["title"] for jid, j in ilanlar.items()}


# ---------------------------------------------------------------------
# Calistirma modlari
# ---------------------------------------------------------------------
def mod_status():
    ilanlar = ilanlari_cek()
    print(f"\nEslesen ilan sayisi: {len(ilanlar)}\n" + "-" * 60)
    for j in sorted(ilanlar.values(), key=lambda x: x["title"]):
        print(f"• {j['title']}")
        print(f"    {j['location']}  |  {j['posted']}")
        print(f"    {j['url']}")
    print()


def mod_once():
    state = state_yukle()
    kontrol_et(state)
    state_kaydet(state)


def mod_loop():
    log(f"GE intern botu basladi. Terimler: {ARAMA_TERIMLERI}")
    telegram_gonder("✅ GE Aerospace intern takip botu basladi.")
    state = state_yukle()
    while True:
        try:
            kontrol_et(state)
            state_kaydet(state)
        except Exception as e:
            log(f"HATA (tur atlandi): {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--test":
        ok = telegram_gonder("✅ GE Aerospace botu calisiyor! (test mesaji)")
        log("Test mesaji gonderildi." if ok else "Test mesaji konsola yazildi (Telegram ayarsiz).")
    elif arg == "--status":
        mod_status()
    elif arg == "--once":
        mod_once()
    else:
        try:
            mod_loop()
        except KeyboardInterrupt:
            log("Bot durduruldu.")
