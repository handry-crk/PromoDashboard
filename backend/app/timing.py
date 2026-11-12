"""Asisten Timing Promo — recommends WHEN to run a promo.

Pure logic (no DB). Demand indices are illustrative defaults based on CRK revenue insight
(weekday weaker than weekend, gajian lifts spending, Dec high season, rainy season lifts delivery,
twin dates drive marketplace). They are explained in every answer so the team can challenge them.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

DOW = {  # Monday..Sunday
    "offline": [0.85, 0.85, 0.90, 0.92, 1.05, 1.25, 1.20],
    "online_food": [0.92, 0.90, 0.92, 0.95, 1.05, 1.20, 1.15],
    "marketplace": [0.95, 0.95, 1.00, 1.00, 1.00, 1.05, 1.05],
    "event": [0.60, 0.60, 0.65, 0.70, 0.90, 1.40, 1.30],
}
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
BLN_SHORT = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7, "agu": 8, "agt": 8, "aug": 8,
             "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12}
DEFAULT_DURATION = {"trial": 7, "awareness": 3, "aov": 14, "jam_sepi": 14, "repeat": 30, "online": 14, "capture": 30}
OBJ_LABEL = {"trial": "trial / traffic", "aov": "naikkan AOV", "jam_sepi": "isi jam sepi", "repeat": "repeat / retention",
             "online": "online / delivery", "awareness": "awareness / event", "capture": "capture data"}


def fmt(d: date) -> str:
    return f"{d.day} {BULAN[d.month - 1][:3]}"


def fmt_range(a: date, b: date) -> str:
    if a.month == b.month:
        return f"{a.day}–{b.day} {BULAN[a.month - 1][:3]} {a.year}"
    return f"{fmt(a)} – {fmt(b)} {b.year}"


def moment_on(d: date, moments: list[dict]):
    iso = d.isoformat()
    return [m for m in moments if m["date"] <= iso <= (m.get("end") or m["date"])]


def demand(d: date, ch: str, moments: list[dict], pay_tilt: float = 1.0):
    """Relative demand for one day (1.0 = normal) plus the tags that explain it."""
    tags = []
    v = DOW.get(ch, DOW["offline"])[d.weekday()]
    if d.weekday() >= 5:
        tags.append("weekend")
    if d.day >= 25 or d.day <= 3:
        f = (1.12 if d.day >= 25 else 1.08) if ch != "marketplace" else 1.06
        v *= 1 + (f - 1) * pay_tilt
        tags.append("gajian")
    elif 15 <= d.day <= 24:
        v *= 0.93
        tags.append("tanggal tua")
    m = d.month
    if m == 12:
        v *= 1.12
        tags.append("musim liburan")
    elif m == 1:
        v *= 0.95
    elif m in (6, 7):
        v *= 1.08
        tags.append("libur sekolah")
    if m in (11, 12, 1, 2):
        if ch == "online_food":
            v *= 1.08
            tags.append("musim hujan (delivery naik)")
        elif ch == "offline":
            v *= 0.96
    for mo in moment_on(d, moments):
        lab, typ = mo["label"], mo.get("type")
        if "Gajian" in lab:
            continue
        if "kembar" in lab.lower() or "Harbolnas" in lab:
            v *= {"marketplace": 2.0 if "Harbolnas" in lab else 1.7, "online_food": 1.10}.get(ch, 1.03)
        elif "Idul Fitri" in lab:
            v *= {"offline": 0.6, "online_food": 0.7, "event": 0.5}.get(ch, 0.85)
        elif "Ramadan" in lab:
            v *= {"offline": 1.10, "online_food": 1.15, "event": 0.8}.get(ch, 1.0)
        elif typ == "libur":
            v *= {"offline": 1.12, "event": 1.25, "online_food": 1.05}.get(ch, 1.0)
        elif typ in ("momen", "belanja", "musim"):
            v *= 1.10
        tags.append(lab)
    return v, tags


def value_for(objective: str, d: float) -> float:
    if objective == "jam_sepi":
        return 1 / d
    if objective in ("repeat", "capture"):
        return 1 + 0.4 * (d - 1)
    return d


def overlaps(a1, b1, a2, b2):
    return not (b1 < a2 or b2 < a1)


def recommend_timing(req: dict, promos: list[dict], moments: list[dict], today: date, history: list[dict] | None = None):
    ch = req.get("channelType") or "offline"
    platform = req.get("platformProfileId")
    objective = req.get("objective") or "trial"
    duration = max(1, min(int(req.get("duration") or DEFAULT_DURATION.get(objective, 14)), 60))
    lead = int(req.get("leadDays") if req.get("leadDays") is not None else (14 if ch == "event" else 7))
    products = set(req.get("products") or [])
    areas = set(req.get("areas") or ["bandung", "jakarta"])
    h_start = date.fromisoformat(req["from"]) if req.get("from") else today
    h_end = date.fromisoformat(req["to"]) if req.get("to") else today + timedelta(days=90)
    earliest = max(today + timedelta(days=lead), h_start)
    if earliest > h_end:
        earliest = h_end
    # history tilt for payday
    pay_tilt, hist_note = 1.0, None
    hs = [h for h in (history or []) if h.get("channelType") == ch and h.get("achievement") is not None]
    if len(hs) >= 3:
        with_pay = [h["achievement"] for h in hs if h.get("hasPayday")]
        without = [h["achievement"] for h in hs if not h.get("hasPayday")]
        if with_pay and without:
            a, b = sum(with_pay) / len(with_pay), sum(without) / len(without)
            pay_tilt = max(0.5, min(2.0, a / b if b else 1))
            hist_note = f"Histori {len(hs)} promo {ch.replace('_', ' ')}: yang mencakup gajian mencapai {a*100:.0f}% target vs {b*100:.0f}% tanpa gajian."

    # demand cache
    cache = {}

    def day(d):
        if d not in cache:
            cache[d] = demand(d, ch, moments, pay_tilt)
        return cache[d]

    others = [p for p in promos if p.get("effectiveStatus") not in ("rejected", "done") and p.get("id") != req.get("excludeId")]
    cands = []
    d = earliest
    while d <= h_end:
        a, b = d, d + timedelta(days=duration - 1)
        vals, tags = [], {}
        for i in range(duration):
            dd = a + timedelta(days=i)
            v, tg = day(dd)
            vals.append(value_for(objective, v))
            for t in tg:
                tags[t] = tags.get(t, 0) + 1
        raw = sum(vals) / len(vals)
        pen, cautions = 0, []
        for p in others:
            pa, pb = date.fromisoformat(p["periodStart"]), date.fromisoformat(p["periodEnd"])
            if not set(p.get("areas") or []) & areas:
                continue
            same_prod = bool(products & set(p.get("products") or []))
            if overlaps(a, b, pa, pb):
                if same_prod and p.get("platformProfileId") == platform:
                    pen += 35
                    cautions.append(f"Bentrok dengan {p['nama']} ({fmt_range(pa, pb)})")
                elif same_prod and p.get("channelType") == ch:
                    pen += 8
                    cautions.append(f"Produk sama sedang dipromokan di {p['platformLabel']}")
            if same_prod and p.get("platformProfileId") == platform and pb < a:
                gap = (a - pb).days
                if gap < 7:
                    pen += 25
                    cautions.append(f"Hanya {gap} hari setelah {p['nama']} selesai")
                elif gap < 14:
                    pen += 15
                    cautions.append(f"Jeda {gap} hari dari {p['nama']} (saran ≥ 14 hari)")
        crowd = sum(1 for p in others if p.get("platformProfileId") == platform and set(p.get("areas") or []) & areas
                    and overlaps(a, b, date.fromisoformat(p["periodStart"]), date.fromisoformat(p["periodEnd"])))
        if crowd >= 2:
            pen += 10 * (crowd - 1)
            cautions.append(f"{crowd} promo lain sudah jalan di platform ini")
        idul = [t for t in tags if "Idul Fitri" in t]
        if idul and ch in ("offline", "event"):
            cautions.append("Mencakup Idul Fitri: banyak outlet tutup / crew mudik")
        cands.append({"start": a, "end": b, "raw": raw, "pen": pen, "tags": tags, "cautions": list(dict.fromkeys(cautions))})
        d += timedelta(days=1)
    if not cands:
        return {"error": "Tidak ada tanggal yang bisa dinilai pada rentang ini."}
    lo, hi = min(c["raw"] for c in cands), max(c["raw"] for c in cands)
    for c in cands:
        base = 50 if hi - lo < 1e-9 else 40 + 60 * (c["raw"] - lo) / (hi - lo)
        c["score"] = max(0, min(100, round(base - c["pen"])))
    ranked = sorted(cands, key=lambda c: (-c["score"], c["start"]))
    picks = []
    for c in ranked:
        if all(not overlaps(c["start"], c["end"], p["start"], p["end"]) for p in picks):
            picks.append(c)
        if len(picks) == 3:
            break
    worst = min(cands, key=lambda c: (c["score"], c["start"]))

    def explain(c):
        n = duration
        t = c["tags"]
        wk = t.get("weekend", 0)
        pay = t.get("gajian", 0)
        tua = t.get("tanggal tua", 0)
        rs = []
        if objective == "jam_sepi":
            wd = n - wk
            rs.append(f"{wd} dari {n} hari adalah weekday, saat traffic normal paling rendah")
            if tua:
                rs.append(f"{tua} hari tanggal tua (15–24): daya beli turun, promo membantu mengisi")
        else:
            if wk:
                rs.append(f"Mencakup {wk} hari weekend")
            if pay:
                rs.append(f"Mencakup {pay} hari periode gajian (25–3)")
        mom = [k for k in t if k not in ("weekend", "gajian", "tanggal tua", "musim liburan", "libur sekolah", "musim hujan (delivery naik)")]
        if mom and objective != "jam_sepi":
            rs.append("Momen: " + ", ".join(mom[:4]))
        if objective != "jam_sepi":
            for k in ("musim liburan", "libur sekolah", "musim hujan (delivery naik)"):
                if t.get(k):
                    rs.append(k[0].upper() + k[1:])
        if not c["cautions"]:
            rs.append("Tidak bentrok dengan promo lain")
        return rs

    def why_low(c):
        t, n = c["tags"], duration
        if c["cautions"]:
            return c["cautions"][0]
        if objective == "jam_sepi":
            busy = [k for k in t if k not in ("tanggal tua",)]
            return "periode ramai (" + ", ".join(busy[:3]) + "), promo isi jam sepi kurang terasa" if busy else "traffic normal sudah tinggi"
        bits = []
        if t.get("tanggal tua"):
            bits.append(f"{t['tanggal tua']} hari tanggal tua")
        if n - t.get("weekend", 0) >= max(1, round(n * 0.7)):
            bits.append("hampir semua weekday")
        if c["start"].month == 1:
            bits.append("Januari biasanya sepi setelah liburan")
        return ", ".join(bits) or "traffic dan daya beli paling rendah di rentang ini"

    def pack(c, label):
        return {"start": c["start"].isoformat(), "end": c["end"].isoformat(), "label": label, "range": fmt_range(c["start"], c["end"]),
                "startDay": HARI[c["start"].weekday()], "score": c["score"], "reasons": explain(c), "cautions": c["cautions"] + (
                    [f"Mencakup {', '.join(k for k in c['tags'] if k not in ('weekend', 'gajian', 'tanggal tua'))[:80]} — traffic naik"]
                    if objective == "jam_sepi" and any(k not in ("weekend", "gajian", "tanggal tua") for k in c["tags"]) else []),
                "whyLow": why_low(c)}

    recs = [pack(c, "Waktu terbaik" if i == 0 else "Alternatif") for i, c in enumerate(picks)]
    check = None
    if req.get("checkStart"):
        cs = date.fromisoformat(req["checkStart"])
        ce = date.fromisoformat(req["checkEnd"]) if req.get("checkEnd") else cs + timedelta(days=duration - 1)
        match = next((c for c in cands if c["start"] == cs), None)
        if match is None:
            # outside candidate range: score it standalone on the same scale
            vals, tags = [], {}
            n = (ce - cs).days + 1
            for i in range(n):
                v, tg = day(cs + timedelta(days=i))
                vals.append(value_for(objective, v))
                for tt in tg:
                    tags[tt] = tags.get(tt, 0) + 1
            raw = sum(vals) / len(vals)
            base = 50 if hi - lo < 1e-9 else 40 + 60 * (raw - lo) / (hi - lo)
            match = {"start": cs, "end": ce, "raw": raw, "pen": 0, "tags": tags, "cautions": [], "score": max(0, min(100, round(base)))}
            if cs < today:
                match["cautions"].append("Promo ini sudah dimulai; skor dipakai sebagai evaluasi timing")
            elif cs < today + timedelta(days=lead):
                match["cautions"].append(f"Kurang dari H-{lead}: waktu persiapan POSM, SKU, dan konten mepet")
        verdict = "Bagus" if match["score"] >= 75 else "Cukup" if match["score"] >= 50 else "Kurang tepat"
        check = {**pack(match, "Tanggal yang dicek"), "verdict": verdict, "gapToBest": recs[0]["score"] - match["score"] if recs else 0}
    heat = [{"date": c["start"].isoformat(), "score": c["score"]} for c in cands]
    ex = {
        "jam_sepi": "Untuk isi jam sepi, saya cari hari yang traffic normalnya paling rendah (weekday, tanggal tua).",
        "repeat": "Untuk repeat, timing tidak terlalu menentukan; saya pilih periode yang tidak bentrok dan tidak terlalu dekat promo lain.",
        "capture": "Untuk capture data, saya pilih periode yang ramai tapi tidak bentrok.",
    }.get(objective, "Untuk objective ini, saya cari periode dengan traffic dan daya beli tertinggi (weekend, gajian, momen).")
    return {"objective": objective, "duration": duration, "leadDays": lead, "channelType": ch,
            "horizon": {"from": earliest.isoformat(), "to": h_end.isoformat()}, "recommendations": recs, "check": check,
            "avoid": pack(worst, "Sebaiknya dihindari"), "heat": heat, "method": ex, "historyNote": hist_note}


# ---------------------------------------------------------------------------
# chat parsing (Bahasa Indonesia, keyword based)
# ---------------------------------------------------------------------------
PLATFORM_WORDS = [
    (r"\bgo ?food\b|\bgojek\b", "gofood"), (r"\bgrab ?food\b|\bgrab\b", "grabfood"), (r"\bshopee ?food\b", "shopeefood"),
    (r"\bshopee\b", "shopee"), (r"\btokopedia\b|\btokped\b|\btiktok\b", "tokopedia_tiktok"), (r"\bgerobak\b", "offline_gerobak"),
    (r"\bkios\b|\boutlet\b|\btoko\b", "offline_kios"), (r"\bbazaa?r\b|\bfood ?fest", "event_bazaar"), (r"\bkonser\b|\bmusik\b", "event_konser"),
    (r"\bkampus\b|\bmall\b|\bcfd\b", "event_kampus"), (r"\bcorporate\b|\bb2b\b|\bkantor\b|\bcatering\b", "event_corporate"),
]
OBJ_WORDS = [
    (r"\bsepi\b|\bweekday\b|jam sepi", "jam_sepi"), (r"\baov\b|basket|nilai transaksi|upsell|bundle", "aov"),
    (r"\brepeat\b|balik lagi|loyal|retensi|retention|langganan", "repeat"), (r"\bdata\b|\bcrm\b|\bcapture\b", "capture"),
    (r"\bawareness\b|\bbrand\b|\bevent\b|\bopening\b", "awareness"), (r"\bonline\b|\bdelivery\b|antar", "online"),
    (r"\btrial\b|\bcoba\b|\btraffic\b|\bramai\b|pelanggan baru|customer baru", "trial"),
]


def parse_message(text: str, ctx: dict, products: dict, profiles: dict, today: date) -> dict:
    t = " " + (text or "").lower() + " "
    out = dict(ctx or {})
    out.pop("checkStart", None)
    out.pop("checkEnd", None)
    for pat, pid in PLATFORM_WORDS:
        if re.search(pat, t) and pid in profiles:
            out["platformProfileId"] = pid
            break
    for pat, obj in OBJ_WORDS:
        if re.search(pat, t):
            out["objective"] = obj
            break
    m = re.search(r"(\d+)\s*(hari|minggu|bulan)", t)
    if m:
        n = int(m.group(1)) * {"hari": 1, "minggu": 7, "bulan": 30}[m.group(2)]
        out["duration"] = max(1, min(n, 60))
    elif "seminggu" in t:
        out["duration"] = 7
    elif "sebulan" in t:
        out["duration"] = 30
    elif "weekend" in t and "duration" not in out:
        out["duration"] = 2
    if re.search(r"bandung", t):
        out["areas"] = ["bandung"]
    elif re.search(r"jakarta|jabodetabek|bekasi|depok|tangerang|bogor", t):
        out["areas"] = ["jakarta"]
    # products
    found = []
    chan = (profiles.get(out.get("platformProfileId")) or {}).get("productChannel")
    words = {"mozza": "mozza", "beef": "beef", "ayam": "ayam", "bojot": "bojot", "mix": "mix", "frozen": "frozen", "kuah": "kuah",
             "mentai": "mentai", "kare": "kare", "takoyaki": "takoyaki", "minuman": "mn-", "teh": "mn-"}
    for w, key in words.items():
        if re.search(rf"\b{w}\b", t):
            for p in products.values():
                if chan and chan not in (p.get("channels") or []):
                    continue
                if w != "frozen" and p.get("kategori") == "frozen" and not re.search(r"\bfrozen\b", t):
                    continue
                if key in p["id"] or key in p["nama"].lower():
                    found.append(p["id"])
    if found:
        out["products"] = sorted(set(found))
    # horizon: month names, "bulan depan", "minggu depan"
    for name, num in [(b.lower(), i + 1) for i, b in enumerate(BULAN)] + list(BLN_SHORT.items()):
        if re.search(rf"\b{name}\b", t) and not re.search(rf"\d{{1,2}}\s*(?:-|–|s/?d|sampai)?\s*\d{{0,2}}\s*{name}\b", t):
            y = today.year + (1 if num < today.month else 0)
            out["from"] = date(y, num, 1).isoformat()
            nxt = date(y + (num == 12), num % 12 + 1, 1)
            out["to"] = (nxt - timedelta(days=1)).isoformat()
            break
    if "bulan depan" in t:
        y, mth = today.year + (today.month == 12), today.month % 12 + 1
        out["from"] = date(y, mth, 1).isoformat()
        out["to"] = (date(y + (mth == 12), mth % 12 + 1, 1) - timedelta(days=1)).isoformat()
    elif "minggu depan" in t:
        out["from"] = (today + timedelta(days=7 - today.weekday())).isoformat()
        out["to"] = (today + timedelta(days=45)).isoformat()
    # explicit date check: "1-14 des", "1 des", "tanggal 20 desember"
    m = re.search(r"(\d{1,2})\s*(?:-|–|s/?d|sampai)\s*(\d{1,2})\s*([a-z]+)", t) or re.search(r"(\d{1,2})()\s*([a-z]+)", t)
    if m:
        mon = None
        word = m.group(3)
        for name, num in [(b.lower(), i + 1) for i, b in enumerate(BULAN)] + list(BLN_SHORT.items()):
            if word.startswith(name):
                mon = num
                break
        if mon:
            y = today.year + (1 if mon < today.month else 0)
            try:
                cs = date(y, mon, int(m.group(1)))
                ce = date(y, mon, int(m.group(2))) if m.group(2) else None
                out["checkStart"] = cs.isoformat()
                if ce and ce >= cs:
                    out["checkEnd"] = ce.isoformat()
                    out["duration"] = (ce - cs).days + 1
                out.pop("from", None)
                out.pop("to", None)
            except ValueError:
                pass
    if "reset" in t or "mulai lagi" in t or "ulang" in t:
        out = {}
    return out


def missing(ctx: dict) -> list[str]:
    need = []
    if not ctx.get("platformProfileId"):
        need.append("platform")
    if not ctx.get("objective"):
        need.append("objective")
    return need
