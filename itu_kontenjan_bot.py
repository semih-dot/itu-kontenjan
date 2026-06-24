#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İTÜ Kontenjan Takip Botu
========================

Takip etmek istedigin CRN'lerde bos yer acildiginda (veya kontenjan
artirildiginda) sana Telegram'dan bildirim gonderir.

Veri kaynagi: itu-helper projesinin 5 dakikada bir guncellenen acik
lessons.psv dosyasi. Bu sayede ITU'nun sunucusuna hic dokunmazsin,
login GEREKMEZ, sifre GEREKMEZ. Sadece okur, bildirir. Dersi sen
elle OBS uzerinden alirsin.

KURULUM (3 adim):
  1) Telegram'da @BotFather'a yaz, /newbot de, bir token al.
  2) @userinfobot'a yaz, sana donen "Id" senin CHAT_ID'in.
  3) Asagidaki AYARLAR bolumunu doldur, sonra:  python3 itu_kontenjan_bot.py

Calistirma modlari:
  python3 itu_kontenjan_bot.py            -> surekli dongu (her INTERVAL sn)
  python3 itu_kontenjan_bot.py --once     -> tek seferlik kontrol (cron/Actions icin)
  python3 itu_kontenjan_bot.py --status   -> takip listesinin anlik durumu (bildirim atmaz)
  python3 itu_kontenjan_bot.py --test     -> Telegram baglantisini test eder (tek mesaj)
"""

import json
import os
import sys
import time
import html
import datetime
import urllib.request
import urllib.parse

# =====================================================================
# AYARLAR  -- burayi doldur
# =====================================================================

# Takip etmek istedigin CRN'ler (tirnak icinde, virgulle ayir)
TAKIP_CRN = [
    "30333",
    "30357",
    "30358",
    "30432",
    "30359",
    "30282",
    # "12345",
]

# Telegram bot bilgilerin. Guvenlik icin ortam degiskeninden de okur:
#   export ITU_BOT_TOKEN="...";  export ITU_CHAT_ID="..."
TELEGRAM_TOKEN = os.environ.get("ITU_BOT_TOKEN", "BURAYA_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("ITU_CHAT_ID", "BURAYA_CHAT_ID")

# Kontrol araligi (saniye). Veri zaten 5 dk'de bir guncellendigi icin
# 300 sn'nin altina inmenin anlami yok.
INTERVAL = 300

# Sadece bos yer ACILINCA mi (0 -> >0) bildireyim, yoksa kontenjan
# ARTIRIMINI da (mevcut bos yer daha da artarsa) bildireyim mi?
KONTENJAN_ARTISI_DA_BILDIR = True

# =====================================================================
# Sabitler -- normalde dokunmana gerek yok
# =====================================================================

LESSONS_URL = "https://raw.githubusercontent.com/itu-helper/data/main/lessons.psv"
RESMI_SAYFA = "https://obs.itu.edu.tr/public/DersProgram"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kontenjan_state.json")
USER_AGENT = "itu-kontenjan-takip/1.0 (kisisel kullanim)"

# psv sutun indeksleri
C_CRN, C_KOD, C_HOCA, C_KON, C_YAZ = 0, 1, 3, 8, 9


def zaman():
    return datetime.datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(f"[{zaman()}] {msg}", flush=True)


# ---------------------------------------------------------------------
# Veri cekme ve parse
# ---------------------------------------------------------------------
def dersleri_cek():
    """lessons.psv'yi indirir ve {crn: {...}} sozlugu dondurur."""
    req = urllib.request.Request(LESSONS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as r:
        ham = r.read().decode("utf-8", errors="replace")

    dersler = {}
    for satir in ham.splitlines():
        if not satir.strip():
            continue
        p = satir.split("|")
        if len(p) <= C_YAZ:
            continue
        try:
            kontenjan = int(p[C_KON])
            yazilan = int(p[C_YAZ])
        except ValueError:
            continue
        crn = p[C_CRN].strip()
        dersler[crn] = {
            "crn": crn,
            "kod": p[C_KOD].strip(),
            "hoca": p[C_HOCA].strip(),
            "kontenjan": kontenjan,
            "yazilan": yazilan,
            "bos": kontenjan - yazilan,
        }
    return dersler


# ---------------------------------------------------------------------
# Durum (state) -- restart/cron sonrasi tekrar bildirim spam'ini onler
# ---------------------------------------------------------------------
def state_yukle():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


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


def bildirim_metni(d, baslik):
    kod = html.escape(d["kod"])
    hoca = html.escape(d["hoca"])
    return (
        f"🎯 <b>{baslik}</b>\n"
        f"<b>{kod}</b>  (CRN {d['crn']})\n"
        f"Bos yer: <b>{d['bos']}</b>  ({d['yazilan']}/{d['kontenjan']})\n"
        f"Hoca: {hoca}\n"
        f"➡️ Hemen OBS'den al: {RESMI_SAYFA}"
    )


# ---------------------------------------------------------------------
# Tek kontrol turu
# ---------------------------------------------------------------------
def kontrol_et(state, sessiz=False):
    """
    Bir tur veriyi ceker, takip edilen CRN'leri kontrol eder,
    gereken durumda bildirir ve state'i gunceller.
    Geri donus: (bulunamayan_crn_listesi).
    """
    dersler = dersleri_cek()
    bulunamayan = []

    for crn in TAKIP_CRN:
        crn = crn.strip()
        d = dersler.get(crn)

        if d is None:
            bulunamayan.append(crn)
            # daha once de bulunamadiysa tekrar uyarma
            if state.get(crn, {}).get("durum") != "yok":
                if not sessiz:
                    log(f"CRN {crn}: listede yok (yanlis CRN olabilir ya da henuz acilmadi)")
                state[crn] = {"durum": "yok", "bos": None}
            continue

        onceki = state.get(crn, {})
        onceki_bos = onceki.get("bos")
        simdi_bos = d["bos"]

        bildir = False
        baslik = ""

        # Durum 1: bos yer yoktu / bilinmiyordu, simdi acildi
        if simdi_bos > 0 and (onceki_bos is None or onceki_bos == 0):
            bildir, baslik = True, "BOS YER ACILDI!"
        # Durum 2: zaten bos yer vardi, daha da artti (kontenjan artirimi)
        elif (KONTENJAN_ARTISI_DA_BILDIR and onceki_bos is not None
              and simdi_bos > onceki_bos > 0):
            bildir, baslik = True, "KONTENJAN ARTTI!"

        if bildir and not sessiz:
            log(f"CRN {crn} ({d['kod']}): {baslik} -> bos {simdi_bos} ({d['yazilan']}/{d['kontenjan']})")
            telegram_gonder(bildirim_metni(d, baslik))
        elif not sessiz:
            log(f"CRN {crn} ({d['kod']}): bos {simdi_bos} ({d['yazilan']}/{d['kontenjan']}) - degisiklik yok")

        state[crn] = {"durum": "var", "bos": simdi_bos,
                      "kod": d["kod"], "kontenjan": d["kontenjan"], "yazilan": d["yazilan"]}

    return bulunamayan


# ---------------------------------------------------------------------
# Calistirma modlari
# ---------------------------------------------------------------------
def mod_status():
    """Bildirim atmadan anlik durumu yazdirir."""
    dersler = dersleri_cek()
    print(f"\n{'CRN':<8} {'DERS':<12} {'DURUM':<10} DETAY")
    print("-" * 50)
    for crn in TAKIP_CRN:
        crn = crn.strip()
        d = dersler.get(crn)
        if d is None:
            print(f"{crn:<8} {'?':<12} {'YOK':<10} listede bulunamadi")
        else:
            durum = "BOS VAR" if d["bos"] > 0 else "DOLU"
            print(f"{crn:<8} {d['kod']:<12} {durum:<10} {d['yazilan']}/{d['kontenjan']} (bos: {d['bos']})")
    print()


def mod_once():
    state = state_yukle()
    kontrol_et(state)
    state_kaydet(state)


def mod_loop():
    log(f"Bot basladi. {len(TAKIP_CRN)} CRN takip ediliyor, her {INTERVAL} sn'de bir kontrol.")
    telegram_gonder(f"✅ İTÜ kontenjan botu basladi. {len(TAKIP_CRN)} ders takipte.")
    state = state_yukle()
    while True:
        try:
            kontrol_et(state)
            state_kaydet(state)
        except Exception as e:
            log(f"HATA (tur atlandi): {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    if not TAKIP_CRN:
        sys.exit("Once TAKIP_CRN listesine en az bir CRN ekle.")
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--test":
        ok = telegram_gonder("✅ İTÜ kontenjan botu calisiyor! (test mesaji)")
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
