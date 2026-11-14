"""CRK Promo Calculator — FastAPI backend."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import logging
import re
import os
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import engine as E
from . import seed as S
from . import timing as T

log = logging.getLogger("crk-promo")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------
USE_MOCK = os.getenv("USE_MOCK_DB", "true").lower() == "true" or not os.getenv("MONGO_URL")
if USE_MOCK:
    import mongomock
    _client = mongomock.MongoClient()
    DB_KIND = "mock"
else:
    from pymongo import MongoClient
    _client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)
    DB_KIND = "mongo"
db = _client[os.getenv("DB_NAME", "crk_promo")]

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
DEFAULT_ADMIN_PIN = os.getenv("DEFAULT_ADMIN_PIN", "1234")
METRICS_API_KEY = os.getenv("METRICS_API_KEY", "change-me-metrics")
for k, v, d in (("SECRET_KEY", SECRET_KEY, "change-me"), ("DEFAULT_ADMIN_PIN", DEFAULT_ADMIN_PIN, "1234"),
                ("METRICS_API_KEY", METRICS_API_KEY, "change-me-metrics")):
    if v == d:
        log.warning("%s masih memakai nilai bawaan — ganti di environment variables Railway.", k)

SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

ROLES = {
    "head": "Marketing Manager",
    "team_leader": "Marketing Team Leader",
    "revenue_growth": "Revenue Growth Specialist",
    "planner": "Promo Planner / Marketing",
    "finance": "Finance",
    "channel_pic": "Channel PIC (Delivery / Marketplace)",
    "viewer": "Viewer",
}

# Hak akses: role baru memakai hak role dasar
PERM_ALIAS = {"team_leader": "planner", "revenue_growth": "finance"}
# Slot pendaftaran mandiri (role → kuota). Role lain hanya bisa diberikan Marketing Manager.
SIGNUP_SLOTS = {"team_leader": 1, "revenue_growth": 1}
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "citarasakuliner.com").lower().lstrip("@")


def perm_of(role: str) -> str:
    return PERM_ALIAS.get(role, role)


def slot_status():
    out = []
    for role, quota in SIGNUP_SLOTS.items():
        used = db.members.count_documents({"role": role, "status": {"$in": ["pending", "approved", "invited"]}, "active": {"$ne": False}})
        out.append({"role": role, "label": ROLES[role], "quota": quota, "used": used, "open": used < quota})
    return out


app = FastAPI(title="CRK Promo Calculator")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now().date()


def clean(doc):
    if doc is None:
        return None
    if isinstance(doc, list):
        return [clean(d) for d in doc]
    d = dict(doc)
    d.pop("_id", None)
    return d


def err(code, msg):
    raise HTTPException(code, msg)


# ---------------------------------------------------------------------------
# settings & auth
# ---------------------------------------------------------------------------

def hash_pin(pin: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", (pin + SECRET_KEY).encode(), salt.encode(), 120_000).hex()
    return f"{salt}${h}"


def check_pin(pin: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_pin(pin, salt), stored)


def get_settings() -> dict:
    s = db.settings.find_one({"_id": "main"})
    if not s:
        s = {"_id": "main", **copy.deepcopy(E.DEFAULT_SETTINGS), "shareToken": secrets.token_urlsafe(24),
             "adminPinHash": hash_pin(DEFAULT_ADMIN_PIN), "adminEmail": "", "appName": "CRK Promo Calculator",
             "baselines": copy.deepcopy(S.BASELINES)}
        db.settings.insert_one(s)
    return s


def public_settings(s):
    s = clean(s)
    s.pop("adminPinHash", None)
    return s


LOCK_MAX, LOCK_WINDOW = 5, 900          # 5 salah dalam 15 menit → kunci 15 menit (per akun)
IP_MAX = 20                              # 20 salah dalam 15 menit dari satu IP → kunci IP


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")) or "?"


def recent_fails(key: str) -> int:
    since = time.time() - LOCK_WINDOW
    return db.login_fails.count_documents({"key": key, "t": {"$gte": since}})


def guard_lock(key: str, limit: int = LOCK_MAX):
    if recent_fails(key) >= limit:
        err(429, "Terlalu banyak percobaan salah. Coba lagi dalam 15 menit atau minta Marketing Manager reset PIN.")


def fail(*keys: str):
    for k in keys:
        db.login_fails.insert_one({"key": k, "t": time.time()})


def clear_fails(key: str):
    db.login_fails.delete_many({"key": key})


def make_session(member: dict) -> str:
    tok = secrets.token_urlsafe(32)
    db.sessions.insert_one({"token": tok, "memberId": member["id"], "at": now_iso()})
    return tok


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        err(401, "Silakan login dulu.")
    tok = authorization[7:]
    s = db.sessions.find_one({"token": tok})
    if not s:
        err(401, "Sesi berakhir. Silakan login lagi.")
    try:
        if (datetime.now(timezone.utc) - datetime.fromisoformat(s["at"])).days >= SESSION_DAYS:
            db.sessions.delete_one({"token": tok})
            err(401, "Sesi berakhir. Silakan login lagi.")
    except (KeyError, ValueError):
        pass
    m = db.members.find_one({"id": s["memberId"]})
    if not m or not m.get("active", True) or m.get("status", "approved") != "approved":
        err(401, "Akun tidak aktif atau belum disetujui Marketing Manager.")
    m = clean(m)
    m.pop("pinHash", None)
    m["perm"] = perm_of(m["role"])
    return m


def require(*roles):
    def dep(user=Depends(current_user)):
        if user.get("isAdmin") or user["perm"] in roles:
            return user
        err(403, "Akses ditolak untuk role Anda.")
    return dep


def is_viewer(user: dict) -> bool:
    return not user.get("isAdmin") and user.get("perm") == "viewer"


def no_viewer(user=Depends(current_user)):
    if is_viewer(user):
        err(403, "Viewer tidak punya akses ke perhitungan margin.")
    return user


SUMMARY_PUBLIC = ("listPrice", "customerPays", "discountTotal", "discountPct", "health", "margin", "menarik", "quadrant", "gate",
                  "targetUnits", "targetTakeRate")


def redact_summary(sm: dict) -> dict:
    out = {}
    for a, x in (sm or {}).items():
        y = {k: x.get(k) for k in SUMMARY_PUBLIC if k in x}
        y["takeaway"] = f"Sehat: {x['health']['label']} · Margin: {x['margin']['label']} · Menarik: {x['menarik']['label']}."
        out[a] = y
    return out


def redact_results(res: dict) -> dict:
    out = {}
    for a, o in (res or {}).items():
        u = o["unit"]
        out[a] = {"area": a, "platformLabel": o.get("platformLabel"), "channelType": o.get("channelType"), "mechanism": o.get("mechanism"),
                  "unit": None, "redacted": True,
                  "price": {"listPrice": u["listPrice"], "customerPays": u["customerPays"], "discountTotal": u["discountTotal"],
                            "discountPct": u["discountPct"]},
                  "health": {"score": o["health"]["score"], "label": o["health"]["label"], "components": [], "hardFails": []},
                  "margin": {"score": o["margin"]["score"], "label": o["margin"]["label"]},
                  "menarik": {"score": o["menarik"]["score"], "label": o["menarik"]["label"], "components": []},
                  "quadrant": o["quadrant"], "gate": {"status": o["gate"]["status"], "conditions": []},
                  "takeaway": f"Sehat: {o['health']['label']} · Margin: {o['margin']['label']} · Menarik: {o['menarik']['label']}.",
                  "durationAdvice": o.get("durationAdvice")}
    return out


PROMO_ACT = {"create": "Membuat promo", "recalc": "Mengubah / menghitung ulang promo", "submit": "Mengajukan promo ke Finance",
             "review_ok": "Meloloskan review margin", "return": "Mengembalikan promo ke draft", "approve": "Menyetujui promo",
             "reject": "Menolak promo", "actual_input": "Mengisi hasil aktual promo", "edit": "Mengubah promo", "delete": "Menghapus promo"}


def audit(user, category: str, action: str, target: str = "", detail: str = "", file=None):
    """Riwayat perubahan: siapa, apa, kapan. Tidak pernah menggagalkan aksi utamanya."""
    try:
        u = user or {}
        db.audit.insert_one({"id": secrets.token_hex(6), "at": now_iso(), "byId": u.get("id"), "byName": u.get("name") or "Sistem",
                             "role": ROLES.get(u.get("role"), "") if u else "", "category": category, "action": action,
                             "target": (target or "")[:120], "detail": (detail or "")[:600], "file": file})
    except Exception as e:  # pragma: no cover
        log.warning("Gagal mencatat riwayat: %s", e)


def fmt_num(v):
    try:
        return f"{int(round(float(v))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


def log_promo(pid, user, action, note=""):
    db.promo_logs.insert_one({"promoId": pid, "at": now_iso(), "byId": user["id"], "byName": user["name"],
                              "action": action, "note": note})
    p = db.promos.find_one({"id": pid}) or {}
    audit(user, "promo", PROMO_ACT.get(action, action), f"{p.get('kode', pid)} {p.get('nama', '')}".strip(), note)


# ---------------------------------------------------------------------------
# data helpers
# ---------------------------------------------------------------------------

def products_map():
    return {p["id"]: clean(p) for p in db.products.find({})}


def profiles_map():
    return {p["id"]: clean(p) for p in db.profiles.find({})}


def baseline_for(settings, pid, area):
    return ((settings.get("baselines") or {}).get(pid) or {}).get(area) or {}


def perf_of(achievement, rating, uplift):
    if achievement is not None:
        return float(achievement)
    if rating:
        return T.PERF_RATING.get(int(rating))
    if uplift is not None:
        return max(0.4, min(1.4, 1 + (float(uplift) - 10) / 50))  # +10% uplift dianggap sesuai target
    return None


def learning_records():
    """Real promo results: promos closed in the dashboard + results entered by hand."""
    profs = profiles_map()
    st = get_settings()
    out = []

    def add(src, rid, d, ach, rating, uplift, take, note):
        try:
            ds, de = date.fromisoformat(d["periodStart"]), date.fromisoformat(d["periodEnd"])
        except Exception:
            return
        if de < ds:
            return
        prof = profs.get(d.get("platformProfileId"), {})
        feat = T.window_features(ds, de, moments_between(ds, de, st))
        out.append({"id": rid, "source": src, "nama": d.get("nama"), "platformProfileId": d.get("platformProfileId"),
                    "platformId": d.get("platformProfileId"), "platformLabel": prof.get("label", "?"),
                    "channelType": prof.get("channelType"), "mechanism": d.get("mechanism"), "objective": d.get("objective"),
                    "areas": d.get("areas") or [], "periodStart": ds.isoformat(), "periodEnd": de.isoformat(),
                    "takeRate": take, "upliftPct": uplift, "achievement": ach, "rating": rating, "perf": perf_of(ach, rating, uplift),
                    "note": note, "by": d.get("by") or d.get("createdBy"), **feat})

    for p in db.promos.find({"status": "done"}):
        a = p.get("actual") or {}
        add("promo", p["id"], p, a.get("achievement"), None, None, a.get("takeRate"), a.get("learningHeadline") or a.get("learning"))
    for r in db.learnings.find({}):
        add("manual", r["id"], r, r.get("achievement"), r.get("rating"), r.get("upliftPct"), r.get("takeRate"), r.get("note"))
    out.sort(key=lambda x: x["periodStart"], reverse=True)
    return out


def history_list():
    return [{"mechanism": r["mechanism"], "platformId": r["platformId"], "takeRate": r["takeRate"], "achievement": r["perf"]}
            for r in learning_records() if r["takeRate"] is not None or r["perf"] is not None]


def effective_status(p):
    st = p.get("status")
    try:
        start = date.fromisoformat(p.get("periodStart"))
        end = date.fromisoformat(p.get("periodEnd"))
    except Exception:
        return st, False
    if st == "approved" and today() >= start:
        st = "running"
    waiting = st == "running" and today() > end
    return st, waiting


def area_inputs(promo, areas, settings, prof_id):
    """Split outlets and fixed costs across areas so a multi-area promo is not double counted."""
    if len(areas) <= 1:
        return {a: promo for a in areas}
    ap = promo.get("areaParams") or {}
    base = {a: baseline_for(settings, prof_id, a) for a in areas}
    outlets = {}
    if all((ap.get(a) or {}).get("outlets") for a in areas):
        outlets = {a: float(ap[a]["outlets"]) for a in areas}
    elif promo.get("outlets"):
        tot = float(promo["outlets"])
        if all(base[a].get("outlets") for a in areas):
            bsum = sum(float(base[a]["outlets"]) for a in areas)
            outlets = {a: tot * float(base[a]["outlets"]) / bsum for a in areas}
        else:
            outlets = {a: tot / len(areas) for a in areas}
    else:
        outlets = {a: float((ap.get(a) or {}).get("outlets") or base[a].get("outlets") or 1) for a in areas}
    total = sum(outlets.values()) or 1
    out = {}
    for a in areas:
        share = outlets[a] / total
        p = dict(promo)
        p["areaParams"] = {**ap, a: {**(ap.get(a) or {}), "outlets": round(outlets[a], 2)}}
        p["fixedCosts"] = [{**f, "amount": E.r(float(f.get("amount") or 0) * share)} for f in promo.get("fixedCosts") or []]
        p["_areaShare"] = share
        out[a] = p
    return out


def compute(promo, areas=None):
    s = get_settings()
    P = products_map()
    prof = profiles_map().get(promo.get("platformProfileId"))
    if not prof:
        err(400, "Pilih platform/channel promo dulu.")
    areas = areas or promo.get("areas") or ["bandung"]
    if prof.get("channelType") == "event":
        areas = areas[:1]  # satu event = satu lokasi; mencegah event dihitung dua kali
    ps, pe = promo.get("periodStart"), promo.get("periodEnd")
    if ps and pe:
        try:
            if date.fromisoformat(pe) < date.fromisoformat(ps):
                err(400, "Tanggal selesai harus sama atau setelah tanggal mulai.")
        except ValueError:
            err(400, "Format tanggal promo tidak valid.")
    hist = history_list()
    per = area_inputs(promo, areas, s, prof["id"])
    out = {}
    for a in areas:
        try:
            out[a] = E.run(per[a], P, prof, a, s, baseline_for(s, prof["id"], a), hist)
            out[a]["areaShare"] = per[a].get("_areaShare", 1)
            out[a]["durationAdvice"] = advice_for(per[a], out[a], prof.get("channelType"))
        except E.CalcError as e:
            err(400, str(e))
    return out


def summary_of(results):
    sm = {}
    for a, o in (results or {}).items():
        u = o["unit"]
        sm[a] = {"listPrice": u["listPrice"], "customerPays": u["customerPays"], "discountTotal": u["discountTotal"],
                 "discountPct": u["discountPct"], "cm": u["cm"], "cmPct": u["cmPct"], "hpp": u["hpp"],
                 "platformFees": u["platformFees"], "effectiveTakeRate": u["effectiveTakeRate"],
                 "health": {"score": o["health"]["score"], "label": o["health"]["label"]},
                 "margin": {"score": o["margin"]["score"], "label": o["margin"]["label"]},
                 "menarik": {"score": o["menarik"]["score"], "label": o["menarik"]["label"]},
                 "quadrant": o["quadrant"], "gate": o["gate"]["status"], "takeaway": o["takeaway"],
                 "targetContribution": o["scenarios"]["target"]["contribution"],
                 "targetUnits": o["scenarios"]["target"]["totalUnits"],
                 "targetIncRevenue": o["scenarios"]["target"]["incRevenue"],
                 "targetIncCM": o["scenarios"]["target"]["incCM"],
                 "targetTakeRate": o["scenarios"]["target"]["takeRate"]}
    return sm


PROMO_FIELDS = ["nama", "objective", "mechanism", "platformProfileId", "areas", "periodStart", "periodEnd", "outlets",
                "outletsLabel", "openRate", "trxPerOutletDay", "items", "params", "areaParams", "funding",
                "programsJoined", "overrides", "maxPerTrx", "quotaPerOutletDay", "capacityPerOutletDay",
                "variableCostPerUnit", "fixedCosts", "segmentMix", "scenarioInputs", "strategic", "trackingReady",
                "description"]


def pick(d, keys):
    return {k: d.get(k) for k in keys if k in d}


def next_code(start: str | None):
    try:
        d = date.fromisoformat(start)
    except Exception:
        d = today()
    pre = f"PR-{d:%y%m}-"
    n = db.promos.count_documents({"kode": {"$regex": f"^{pre}"}}) + 1
    while db.promos.find_one({"kode": f"{pre}{n:02d}"}):
        n += 1
    return f"{pre}{n:02d}"


def enrich_product(p, s):
    return {**p, **E.product_flags(p, s)}


def migrate_event_profiles():
    """Add event templates to databases seeded before they existed. Never touches existing profiles."""
    try:
        if db.products.count_documents({}) == 0:
            return
        for prof in S.PROFILES:
            if prof["channelType"] == "event" and not db.profiles.find_one({"id": prof["id"]}):
                db.profiles.insert_one(copy.deepcopy(prof))
                log.info("Profil event ditambahkan: %s", prof["label"])
        db.profiles.update_one({"id": "event", "channelType": "offline"}, {"$set": {"label": "Event / Booth (lama)", "channelType": "event",
                               "eventDefaults": next(p for p in S.PROFILES if p["id"] == "event_bazaar")["eventDefaults"], "eventFixedTemplate": [], "verified": False}})
    except Exception as e:  # pragma: no cover
        log.warning("Migrasi profil event gagal: %s", e)


migrate_event_profiles()


# ---------------------------------------------------------------------------
# routes: health & auth
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    try:
        db.command("ping") if not USE_MOCK else None
        ok = True
    except Exception:
        ok = False
    return {"ok": ok, "db": DB_KIND}


ENABLE_ADMIN_PIN = os.getenv("ENABLE_ADMIN_PIN", "false").lower() == "true"
INVITE_DAYS = int(os.getenv("INVITE_DAYS", "7"))


@app.get("/api/public/members")
def public_members():
    # Sengaja tidak mengirim daftar nama anggota.
    return {"hasAny": db.members.count_documents({"hidden": {"$ne": True}}) > 0, "emailDomain": EMAIL_DOMAIN,
            "adminPin": ENABLE_ADMIN_PIN, "roles": ROLES}


def find_invite(token: str):
    if not token:
        return None
    inv = db.invites.find_one({"token": token})
    if not inv or inv.get("usedAt") or inv.get("revoked"):
        return None
    if datetime.fromisoformat(inv["expiresAt"]) < datetime.now(timezone.utc):
        return None
    return inv


@app.get("/api/public/invite/{token}")
def public_invite(token: str):
    inv = find_invite(token)
    if not inv:
        err(404, "Link undangan tidak valid, sudah dipakai, atau kedaluwarsa. Minta link baru ke Marketing Manager.")
    return {"role": inv["role"], "label": ROLES.get(inv["role"], inv["role"]), "expiresAt": inv["expiresAt"],
            "emailDomain": EMAIL_DOMAIN}


@app.post("/api/auth/register")
def register(body: dict, request: Request):
    ip = f"ipreg:{client_ip(request)}"
    guard_lock(ip, IP_MAX)
    fail(ip)  # setiap percobaan daftar dihitung untuk membatasi spam
    name = (body.get("name") or "").strip()
    pin = str(body.get("pin") or "")
    role = body.get("role") or ""
    email = (body.get("email") or "").strip().lower()
    if not name:
        err(400, "Isi nama lengkap.")
    if not email.endswith("@" + EMAIL_DOMAIN) or email.count("@") != 1 or len(email) <= len(EMAIL_DOMAIN) + 1:
        err(400, f"Gunakan email kantor @{EMAIL_DOMAIN}.")
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        err(400, "PIN harus 4–6 angka.")
    first = db.members.count_documents({"hidden": {"$ne": True}}) == 0
    inv = None
    if not first:
        inv = find_invite(body.get("invite") or "")
        if not inv:
            err(403, "Pendaftaran hanya lewat link undangan dari Marketing Manager.")
        if inv.get("email") and inv["email"] != email:
            err(400, f"Undangan ini untuk {inv['email']}.")
        role = inv["role"]
    if db.members.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "status": {"$ne": "rejected"}}):
        err(400, "Nama sudah terdaftar. Gunakan nama lengkap yang berbeda.")
    if db.members.find_one({"email": email, "status": {"$ne": "rejected"}}):
        err(400, "Email ini sudah terdaftar.")
    if not first and role in SIGNUP_SLOTS:
        slot = next((x for x in slot_status() if x["role"] == role), None)
        if not slot:
            err(400, "Pilih slot yang tersedia: " + ", ".join(ROLES[k] for k in SIGNUP_SLOTS) + ".")
        if not slot["open"]:
            err(400, f"Slot {slot['label']} sudah terisi. Hubungi Marketing Manager.")
    if not first and role not in ROLES:
        err(400, "Role undangan tidak dikenal.")
    m = {"id": secrets.token_hex(6), "name": name, "role": "head" if first else role, "email": email,
         "phone": body.get("phone", ""), "pinHash": hash_pin(pin), "active": True, "isAdmin": first,
         "status": "approved" if first else "pending", "platforms": [], "createdAt": now_iso()}
    db.members.insert_one(m)
    if inv:
        db.invites.update_one({"token": inv["token"]}, {"$set": {"usedAt": now_iso(), "usedBy": m["id"], "usedByName": name}})
        audit(m, "anggota", "Mendaftar lewat undangan", name, f"{ROLES.get(role, role)} · {email}")
    get_settings()
    if not first:
        return {"pending": True, "message": f"Pendaftaran {ROLES[role]} terkirim. Anda bisa login setelah disetujui Marketing Manager."}
    return {"token": make_session(m), "user": {k: v for k, v in clean(m).items() if k != "pinHash"}}


@app.post("/api/auth/login")
def login(body: dict, request: Request):
    ident = (body.get("identifier") or "").strip()
    ip = f"ip:{client_ip(request)}"
    guard_lock(ip, IP_MAX)
    m = None
    if ident:
        if "@" in ident:
            m = db.members.find_one({"email": ident.lower(), "status": {"$ne": "rejected"}})
        else:
            m = db.members.find_one({"name": {"$regex": f"^{re.escape(ident)}$", "$options": "i"}, "status": {"$ne": "rejected"},
                                     "hidden": {"$ne": True}})
    key = f"m:{m['id']}" if m else f"u:{ident.lower()}"
    guard_lock(key)
    if m and m.get("status") == "invited":
        err(403, "Akun belum diaktifkan. Buka link aktivasi dari Marketing Manager untuk membuat PIN.")
    if not m or not m.get("active", True) or not check_pin(str(body.get("pin") or ""), m.get("pinHash", "")):
        fail(key, ip)
        err(401, "Nama/email atau PIN salah.")
    clear_fails(key)
    if m.get("status", "approved") == "pending":
        err(403, "Akun Anda masih menunggu approval Marketing Manager.")
    if m.get("status") == "invited":
        err(403, "Akun belum diaktifkan. Buka link aktivasi dari Marketing Manager untuk membuat PIN.")
    if m.get("status") == "rejected":
        err(403, "Pendaftaran Anda ditolak. Hubungi Marketing Manager.")
    return {"token": make_session(m), "user": {k: v for k, v in clean(m).items() if k != "pinHash"}}


@app.post("/api/auth/admin-login")
def admin_login(body: dict, request: Request):
    if not ENABLE_ADMIN_PIN:
        err(404, "Login PIN Admin dinonaktifkan.")
    ip = f"ip:{client_ip(request)}"
    guard_lock(ip, IP_MAX)
    guard_lock("admin")
    s = get_settings()
    if not check_pin(str(body.get("pin") or ""), s["adminPinHash"]):
        fail("admin", ip)
        err(401, "PIN Admin salah.")
    m = db.members.find_one({"id": "admin"})
    if not m:
        m = {"id": "admin", "name": "Admin", "role": "head", "isAdmin": True, "active": True, "pinHash": "x$x",
             "createdAt": now_iso(), "hidden": True}
        db.members.insert_one(m)
    return {"token": make_session(m), "user": {k: v for k, v in clean(m).items() if k != "pinHash"}}


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization:
        db.sessions.delete_one({"token": authorization[7:]})
    return {"ok": True}


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def promo_view(p):
    p = clean(p)
    st, waiting = effective_status(p)
    p["effectiveStatus"] = st
    p["waitingActual"] = waiting
    p.pop("results", None)
    return p


@app.get("/api/state")
def state(user=Depends(current_user)):
    s = get_settings()
    promos = [promo_view(p) for p in db.promos.find({}).sort("createdAt", -1)]
    viewer = is_viewer(user)
    if viewer:
        for p in promos:
            p["summary"] = redact_summary(p.get("summary"))
            if p.get("actual"):
                p["actual"] = {k: v for k, v in p["actual"].items() if k not in ("contribution", "platformFees", "merchantDiscount")}
    members = []
    if user.get("isAdmin"):
        members = [{**{k: v for k, v in clean(m).items() if k != "pinHash"}, "status": m.get("status", "approved")}
                   for m in db.members.find({"hidden": {"$ne": True}, "status": {"$ne": "rejected"}})]
    ps_ = public_settings(s)
    if not (user.get("isAdmin") or user.get("perm") == "head"):
        ps_.pop("shareToken", None)
    return {"user": user, "roles": ROLES, "slots": slot_status(), "emailDomain": EMAIL_DOMAIN, "settings": ps_,
            "products": [({k: v for k, v in enrich_product(p, s).items() if k not in ("hpp", "hppBreakdown", "gmPct")} if viewer
                          else enrich_product(p, s)) for p in products_map().values()],
            "profiles": list(profiles_map().values()), "promos": promos, "members": members,
            "mechanisms": E.MECHANISMS, "objectives": E.OBJECTIVES, "empty": db.products.count_documents({}) == 0}


# ---------------------------------------------------------------------------
# calculations
# ---------------------------------------------------------------------------

@app.post("/api/calc")
def api_calc(body: dict, user=Depends(no_viewer)):
    promo = body.get("promo") or body
    return {"results": compute(promo, body.get("areas"))}


@app.post("/api/calc/compare-platforms")
def api_compare(body: dict, user=Depends(no_viewer)):
    promo = body.get("promo") or {}
    area = body.get("area") or (promo.get("areas") or ["bandung"])[0]
    s = get_settings()
    P = products_map()
    rows = []
    for prof in profiles_map().values():
        if not all(E.sells_on(P.get(i.get("productId"), {}), prof) for i in promo.get("items") or [] if i.get("productId") in P):
            continue
        pr = {**promo, "platformProfileId": prof["id"]}
        if prof["channelType"] == "offline":
            pr["programsJoined"] = []
            if pr.get("mechanism") in E.ONLINE_ONLY_MECHS:
                continue
        else:
            pr["programsJoined"] = [x for x in (promo.get("programsJoined") or [])
                                    if x in [g["programKey"] for g in prof.get("programs") or []]]
        try:
            o = E.run(pr, P, prof, area, s, baseline_for(s, prof["id"], area), light=True)
        except E.CalcError:
            continue
        u = o["unit"]
        rows.append({"platformId": prof["id"], "label": prof["label"], "channelType": prof["channelType"],
                     "verified": prof.get("verified"), "customerPays": u["customerPays"], "discountTotal": u["discountTotal"],
                     "platformFees": u["platformFees"] + u["adsCost"], "effectiveTakeRate": u["effectiveTakeRate"],
                     "cm": u["cm"], "cmPct": u["cmPct"], "health": o["health"]["label"], "margin": o["margin"]["label"],
                     "menarik": o["menarik"]["label"], "menarikScore": o["menarik"]["score"], "gate": o["gate"]["status"]})
    if rows:
        best_m = max(rows, key=lambda x: x["cm"])["platformId"]
        best_a = max(rows, key=lambda x: x["menarikScore"])["platformId"]
        for r_ in rows:
            r_["bestMargin"] = r_["platformId"] == best_m
            r_["bestAttract"] = r_["platformId"] == best_a
    return {"area": area, "rows": rows}


@app.post("/api/calc/settlement")
def api_settlement(body: dict, user=Depends(no_viewer)):
    prof = profiles_map().get(body.get("profileId"))
    if not prof:
        err(400, "Pilih profil platform.")
    if body.get("profileOverride"):
        prof = {**prof, **body["profileOverride"]}
    P = products_map()
    area = body.get("area", "bandung")
    items = body.get("items") or []
    lst = 0
    hpp = 0
    units = 0
    for it in items:
        p = P.get(it.get("productId"))
        if not p:
            continue
        q = int(it.get("qty") or 1)
        lp = E.list_price(p, prof, area) or 0
        lst += lp * q
        hpp += p["hpp"] * q
        units += q
    if not units:
        err(400, "Tambahkan item ke keranjang simulasi.")
    disc = E.r(lst * float(body.get("discountPct") or 0) / 100)
    s = E.settle(prof, lst, disc, float(body.get("merchantPct", 100)), is_promo=disc > 0,
                 programs=body.get("programs") or [], units_per_order=1)
    return {"listPrice": lst, "discount": disc, "hpp": hpp, **s, "cm": s["merchantNet"] - hpp,
            "effectiveTakeRate": E.pct(s["platformFees"] + s["adsCost"], s["merchantGross"])}


@app.post("/api/recommend")
def api_recommend(body: dict, user=Depends(no_viewer)):
    s = get_settings()
    prof = profiles_map().get(body.get("platformProfileId"))
    if not prof:
        err(400, "Pilih platform/channel.")
    area = body.get("area", "bandung")
    if prof.get("channelType") == "event":
        body = {**body, "fixedCosts": body.get("fixedCosts") or copy.deepcopy(prof.get("eventFixedTemplate") or []),
                "trackingReady": True}
    res = E.recommend(body, products_map(), prof, s, baseline_for(s, prof["id"], area), history_list())
    for x in res:
        x["promo"]["platformProfileId"] = prof["id"]
        x["promo"]["areas"] = [area]
        u = x["result"]["unit"]
        adv = T.duration_advice(x["promo"]["mechanism"], body.get("objective"), prof.get("channelType"), u["discountPct"] * 100,
                                x["result"]["health"]["label"], (x["promo"].get("params") or {}).get("n"),
                                (prof.get("eventDefaults") or {}).get("days") if prof.get("channelType") == "event" else None,
                                hist=duration_history(x["promo"]["mechanism"]))
        x["result"]["durationAdvice"] = adv
        if not x["promo"].get("periodStart"):
            start = today() + timedelta(days=7)
            x["promo"]["periodStart"] = start.isoformat()
            x["promo"]["periodEnd"] = (start + timedelta(days=adv["rec"] - 1)).isoformat()
    return {"results": res}


# ---------------------------------------------------------------------------
# promos
# ---------------------------------------------------------------------------

@app.get("/api/promos/{pid}")
def get_promo(pid: str, user=Depends(current_user)):
    p = db.promos.find_one({"id": pid})
    if not p:
        err(404, "Promo tidak ditemukan.")
    v = promo_view(p)
    v["results"] = clean(p).get("results")
    v["targets"] = aggregate_targets(p.get("summary") or {})
    if is_viewer(user):
        v["results"] = redact_results(v["results"])
        v["summary"] = redact_summary(v.get("summary"))
        v["targets"] = {k: v["targets"].get(k) for k in ("targetUnits", "targetTakeRate")}
        if v.get("actual"):
            v["actual"] = {k: x for k, x in v["actual"].items() if k not in ("contribution", "platformFees", "merchantDiscount")}
            if v["actual"].get("achievementDetail"):
                v["actual"]["achievementDetail"] = {k: x for k, x in v["actual"]["achievementDetail"].items() if k != "contribution"}
    v["timeline"] = clean(list(db.promo_logs.find({"promoId": pid}).sort("at", 1)))
    v["comments"] = clean(list(db.comments.find({"promoId": pid}).sort("at", 1)))
    pv = (get_settings().get("priceVersion") or 1)
    v["stale"] = (p.get("priceVersion") or 1) != pv or any(
        (profiles_map().get(p.get("platformProfileId")) or {}).get("version", 1) != p.get("profileVersion", 1) for _ in [0])
    return v


def save_results(doc):
    res = compute(doc)
    doc["results"] = res
    doc["summary"] = summary_of(res)
    doc["priceVersion"] = get_settings().get("priceVersion") or 1
    doc["profileVersion"] = (profiles_map().get(doc.get("platformProfileId")) or {}).get("version", 1)
    return doc


@app.post("/api/promos")
def create_promo(body: dict, user=Depends(require("planner", "channel_pic", "head"))):
    doc = pick(body, PROMO_FIELDS)
    if not doc.get("nama"):
        err(400, "Isi nama promo.")
    doc.update({"id": secrets.token_hex(6), "kode": next_code(doc.get("periodStart")), "status": "draft",
                "createdBy": user["name"], "createdById": user["id"], "createdAt": now_iso(), "updatedAt": now_iso()})
    save_results(doc)
    db.promos.insert_one(doc)
    log_promo(doc["id"], user, "create")
    return get_promo(doc["id"], user)


@app.put("/api/promos/{pid}")
def update_promo(pid: str, body: dict, user=Depends(require("planner", "channel_pic", "head"))):
    p = db.promos.find_one({"id": pid})
    if not p:
        err(404, "Promo tidak ditemukan.")
    if p["status"] in ("done",):
        err(400, "Promo yang sudah selesai tidak bisa diubah.")
    upd = pick(body, PROMO_FIELDS)
    doc = {**clean(p), **upd, "updatedAt": now_iso()}
    mech_changed = any(json.dumps(p.get(k), sort_keys=True, default=str) != json.dumps(doc.get(k), sort_keys=True, default=str)
                       for k in ("items", "params", "areaParams", "mechanism", "funding", "programsJoined", "platformProfileId"))
    if p["status"] == "rejected" and upd:
        doc["status"] = "draft"
        log_promo(pid, user, "edit", "Promo yang ditolak direvisi — kembali ke draft")
    elif mech_changed and p["status"] in ("approved", "review_head", "review_finance", "running"):
        doc["status"] = "draft"
        log_promo(pid, user, "edit", "Mekanisme berubah setelah review — status kembali ke draft")
    save_results(doc)
    db.promos.replace_one({"id": pid}, doc)
    log_promo(pid, user, "recalc")
    return get_promo(pid, user)


@app.delete("/api/promos/{pid}")
def delete_promo(pid: str, user=Depends(require("head"))):
    p = db.promos.find_one({"id": pid}) or {}
    audit(user, "promo", "Menghapus promo", f"{p.get('kode', pid)} {p.get('nama', '')}".strip())
    db.promos.delete_one({"id": pid})
    return {"ok": True}


@app.post("/api/promos/{pid}/submit")
def submit_promo(pid: str, body: dict | None = None, user=Depends(require("planner", "channel_pic", "head"))):
    p = db.promos.find_one({"id": pid})
    if not p:
        err(404, "Promo tidak ditemukan.")
    if p["status"] != "draft":
        err(400, f"Promo berstatus {p['status']}; hanya draft yang bisa diajukan.")
    gates = [o["gate"]["status"] for o in (p.get("results") or {}).values()]
    strat = (p.get("strategic") or {})
    if "HOLD" in gates and not (strat.get("isStrategic") and strat.get("reason")):
        err(400, "Promo berstatus HOLD. Perbaiki atau isi alasan strategis sebelum mengajukan.")
    db.promos.update_one({"id": pid}, {"$set": {"status": "review_finance", "updatedAt": now_iso()}})
    log_promo(pid, user, "submit", (body or {}).get("note", ""))
    return get_promo(pid, user)


@app.post("/api/promos/{pid}/review")
def review_promo(pid: str, body: dict, user=Depends(require("finance", "head"))):
    p = db.promos.find_one({"id": pid})
    if not p or p["status"] != "review_finance":
        err(400, "Promo tidak sedang menunggu review Finance.")
    if body.get("decision") == "approve":
        db.promos.update_one({"id": pid}, {"$set": {"status": "review_head"}})
        log_promo(pid, user, "review_ok", body.get("note", ""))
    else:
        if not body.get("note"):
            err(400, "Tulis catatan alasan pengembalian.")
        db.promos.update_one({"id": pid}, {"$set": {"status": "draft"}})
        log_promo(pid, user, "return", body["note"])
    return get_promo(pid, user)


@app.post("/api/promos/{pid}/approve")
def approve_promo(pid: str, body: dict, user=Depends(require("head"))):
    p = db.promos.find_one({"id": pid})
    if not p or p["status"] != "review_head":
        err(400, "Promo belum lolos review Finance.")
    if body.get("decision") == "approve":
        db.promos.update_one({"id": pid}, {"$set": {"status": "approved"}})
        log_promo(pid, user, "approve", body.get("note", ""))
    else:
        if not body.get("note"):
            err(400, "Tulis alasan penolakan.")
        db.promos.update_one({"id": pid}, {"$set": {"status": "rejected", "rejectNote": body["note"]}})
        log_promo(pid, user, "reject", body["note"])
    return get_promo(pid, user)


def aggregate_targets(summary):
    vals = list(summary.values())
    if not vals:
        return {}
    tot = lambda k: sum(v.get(k) or 0 for v in vals)
    units = tot("targetUnits")
    return {"targetUnits": units, "targetIncRevenue": tot("targetIncRevenue"), "targetIncCM": tot("targetIncCM"),
            "targetContribution": tot("targetContribution"),
            "targetTakeRate": sum((v.get("targetTakeRate") or 0) * (v.get("targetUnits") or 0) for v in vals) / units if units else vals[0].get("targetTakeRate"),
            "cmPct": vals[0].get("cmPct")}


@app.post("/api/promos/{pid}/actual")
def actual_promo(pid: str, body: dict, user=Depends(require("planner", "channel_pic", "head", "finance"))):
    p = db.promos.find_one({"id": pid})
    if not p:
        err(404, "Promo tidak ditemukan.")
    st, _ = effective_status(p)
    if st not in ("running", "done", "approved"):
        err(400, "Hasil aktual hanya untuk promo yang sudah berjalan.")
    sm = aggregate_targets(p.get("summary") or {})
    a = {k: body.get(k) for k in ("units", "orders", "transactions", "revenue", "aov", "takeRate", "incRevenue",
                                  "merchantDiscount", "platformFees", "fixedCost", "repeat30d", "learningHeadline",
                                  "learning", "nextAction")}
    num = lambda k: float(a.get(k) or 0)
    ratio = (sm.get("targetIncCM") / sm.get("targetIncRevenue")) if sm.get("targetIncRevenue") else (sm.get("cmPct") or 0)
    a["contribution"] = E.r(num("incRevenue") * ratio - num("fixedCost"))
    achs = []
    for k_act, k_tgt in (("units", "targetUnits"), ("incRevenue", "targetIncRevenue"), ("takeRate", "targetTakeRate")):
        if a.get(k_act) not in (None, "") and sm.get(k_tgt):
            achs.append(num(k_act) / sm[k_tgt])
    a["achievementDetail"] = {"units": num("units") / sm["targetUnits"] if sm.get("targetUnits") else None,
                              "incRevenue": num("incRevenue") / sm["targetIncRevenue"] if sm.get("targetIncRevenue") else None,
                              "takeRate": num("takeRate") / sm["targetTakeRate"] if sm.get("targetTakeRate") else None,
                              "contribution": a["contribution"] / sm["targetContribution"] if sm.get("targetContribution") else None}
    a["achievement"] = round(sum(achs) / len(achs), 3) if achs else None
    a["takeRate"] = num("takeRate") if a.get("takeRate") not in (None, "") else None
    a["at"] = now_iso()
    upd = {"actual": a}
    if body.get("finish"):
        if not a.get("units"):
            err(400, "Isi minimal jumlah unit aktual sebelum menutup promo.")
        upd["status"] = "done"
    db.promos.update_one({"id": pid}, {"$set": upd})
    log_promo(pid, user, "actual_input", "Promo ditutup" if body.get("finish") else "")
    return get_promo(pid, user)


@app.post("/api/promos/{pid}/comments")
def comment_promo(pid: str, body: dict, user=Depends(current_user)):
    if not (body.get("text") or "").strip():
        err(400, "Tulis komentar dulu.")
    db.comments.insert_one({"promoId": pid, "byId": user["id"], "byName": user["name"], "at": now_iso(), "text": body["text"]})
    return get_promo(pid, user)


# ---------------------------------------------------------------------------
# products & platforms
# ---------------------------------------------------------------------------

def bump_price_version(user, note):
    s = get_settings()
    v = (s.get("priceVersion") or 1) + 1
    db.settings.update_one({"_id": "main"}, {"$set": {"priceVersion": v}})
    db.price_versions.insert_one({"version": v, "at": now_iso(), "by": user["name"], "note": note,
                                  "products": list(products_map().values())})
    return v


@app.get("/api/price-versions")
def price_versions(user=Depends(no_viewer)):
    return [{"version": x["version"], "at": x["at"], "by": x["by"], "note": x["note"]}
            for x in db.price_versions.find({}).sort("version", -1)]


@app.post("/api/products")
def add_product(body: dict, user=Depends(require("finance", "head"))):
    if not body.get("nama") or body.get("hpp") in (None, ""):
        err(400, "Isi nama produk dan HPP.")
    p = {"id": body.get("id") or secrets.token_hex(5), "sku": body.get("sku") or "", "nama": body["nama"],
         "kategori": body.get("kategori", "reguler"), "porsi": body.get("porsi", "-"), "hpp": int(body["hpp"]),
         "prices": body.get("prices") or {}, "platformPrices": body.get("platformPrices") or {},
         "channels": body.get("channels") or ["kios"], "active": True}
    db.products.insert_one(p)
    bump_price_version(user, f"Tambah produk {p['nama']}")
    audit(user, "produk", "Menambah produk", p["nama"], f"HPP {fmt_num(p['hpp'])}; harga " + ", ".join(f"{a} {fmt_num(v)}" for a, v in p["prices"].items()))
    return clean(p)


@app.put("/api/products/{pid}")
def edit_product(pid: str, body: dict, user=Depends(current_user)):
    p = db.products.find_one({"id": pid})
    if not p:
        err(404, "Produk tidak ditemukan.")
    if not (user.get("isAdmin") or user["perm"] in ("finance", "head")):
        if user["perm"] == "channel_pic" and set(body.keys()) <= {"platformPrices"}:
            pass
        else:
            err(403, "Hanya Finance yang bisa mengubah HPP dan harga.")
    upd = {k: body[k] for k in ("nama", "sku", "kategori", "porsi", "hpp", "prices", "platformPrices", "channels",
                                "active", "marketplaceCategory") if k in body}
    if "hpp" in upd:
        upd["hpp"] = int(upd["hpp"])
    db.products.update_one({"id": pid}, {"$set": upd})
    changes = ", ".join(f"{k}" for k in upd)
    diffs = []
    if "hpp" in upd and upd["hpp"] != p.get("hpp"):
        diffs.append(f"HPP {fmt_num(p.get('hpp'))} → {fmt_num(upd['hpp'])}")
    for a in ("bandung", "jakarta"):
        if "prices" in upd and (upd["prices"] or {}).get(a) != (p.get("prices") or {}).get(a):
            diffs.append(f"Harga {a.title()} {fmt_num((p.get('prices') or {}).get(a))} → {fmt_num((upd['prices'] or {}).get(a))}")
    for k, lab in (("nama", "Nama"), ("kategori", "Kategori"), ("active", "Aktif"), ("channels", "Channel"), ("platformPrices", "Harga platform")):
        if k in upd and upd[k] != p.get(k, True if k == "active" else None):
            diffs.append(f"{lab} diubah" if k in ("channels", "platformPrices") else f"{lab}: {p.get(k)} → {upd[k]}")
    if diffs:
        audit(user, "produk", "Mengubah produk", p["nama"], "; ".join(diffs))
    bump_price_version(user, f"Ubah {p['nama']}: {changes}")
    return clean(db.products.find_one({"id": pid}))


@app.post("/api/products/import")
async def import_products(request: Request, user=Depends(require("finance", "head"))):
    text = (await request.body()).decode("utf-8-sig")
    n = 0
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("nama"):
            continue
        pid = row.get("id") or row["nama"].lower().replace(" ", "-")
        prices = {}
        for a in ("bandung", "jakarta"):
            if row.get(f"harga_{a}"):
                prices[a] = int(float(row[f"harga_{a}"]))
        doc = {"id": pid, "sku": row.get("sku", ""), "nama": row["nama"], "kategori": row.get("kategori", "reguler"),
               "porsi": row.get("porsi", "-"), "hpp": int(float(row.get("hpp") or 0)), "prices": prices,
               "channels": [c.strip() for c in (row.get("channels") or "kios").split("|") if c.strip()], "active": True}
        existing = db.products.find_one({"id": pid})
        if existing:
            db.products.update_one({"id": pid}, {"$set": doc})
        else:
            doc["platformPrices"] = {}
            db.products.insert_one(doc)
        n += 1
    bump_price_version(user, f"Import CSV {n} produk")
    audit(user, "file", "Mengimport file produk & HPP", f"{n} produk", "", request.headers.get("x-filename"))
    return {"imported": n}


def can_edit_profile(user, prof):
    if user.get("isAdmin") or user["perm"] in ("finance", "head"):
        return True
    return user["perm"] == "channel_pic" and prof["id"] in (user.get("platforms") or [])


@app.post("/api/platform-profiles")
def add_profile(body: dict, user=Depends(require("finance", "head"))):
    if not body.get("label"):
        err(400, "Isi nama profil.")
    p = {**body, "id": body.get("id") or secrets.token_hex(5), "version": 1, "verified": False}
    p.setdefault("feeComponents", [])
    p.setdefault("programs", [])
    db.profiles.insert_one(p)
    audit(user, "platform", "Menambah profil platform", p.get("label", ""))
    return clean(p)


@app.put("/api/platform-profiles/{pid}")
def edit_profile(pid: str, body: dict, user=Depends(current_user)):
    p = db.profiles.find_one({"id": pid})
    if not p:
        err(404, "Profil tidak ditemukan.")
    if not can_edit_profile(user, p):
        err(403, "Anda hanya bisa mengubah profil platform yang Anda pegang.")
    body.pop("id", None)
    body.pop("_id", None)
    old = clean(p)
    db.profile_versions.insert_one({"profileId": pid, "version": old.get("version", 1), "at": now_iso(),
                                    "by": user["name"], "snapshot": old})
    new = {**old, **body, "version": old.get("version", 1) + 1, "verified": False, "updatedAt": now_iso(),
           "updatedBy": user["name"]}
    db.profiles.replace_one({"id": pid}, new)
    diffs = []
    oc = {c.get("key"): c for c in old.get("feeComponents") or []}
    val = lambda x: (f"{x.get('rate') or 0:g}%" if str(x.get("type", "")).startswith("percent") else f"Rp{fmt_num(x.get('amount') or 0)}")
    for c in new.get("feeComponents") or []:
        o = oc.pop(c.get("key"), None)
        if o is None:
            diffs.append(f"+ {c.get('label')} {val(c)}")
        elif val(o) != val(c) or o.get("active", True) != c.get("active", True) or o.get("base") != c.get("base"):
            diffs.append(f"{c.get('label')} {val(o)} → {val(c)}" + ("" if o.get("active", True) == c.get("active", True) else " (aktif/nonaktif)"))
    diffs += [f"− {o.get('label')}" for o in oc.values()]
    for k, lab in (("ppnPct", "PPN atas biaya"), ("adminFeeDiscountPct", "Diskon biaya admin"), ("avgUnitsPerOrder", "Porsi per order"), ("label", "Nama")):
        if old.get(k) != new.get(k):
            diffs.append(f"{lab} {old.get(k)} → {new.get(k)}")
    for k, lab in (("pricing", "Harga/markup"), ("costs", "Biaya channel"), ("ads", "Ads"), ("programs", "Program"),
                   ("eventDefaults", "Asumsi event"), ("eventFixedTemplate", "Template biaya tetap")):
        if old.get(k) != new.get(k):
            diffs.append(f"{lab} diubah")
    audit(user, "platform", "Mengubah biaya platform", new.get("label", pid), "; ".join(diffs) or "Disimpan tanpa perubahan angka")
    return clean(new)


@app.post("/api/platform-profiles/{pid}/duplicate")
def dup_profile(pid: str, user=Depends(require("finance", "head"))):
    p = clean(db.profiles.find_one({"id": pid}))
    if not p:
        err(404, "Profil tidak ditemukan.")
    p.update({"id": f"{pid}-{secrets.token_hex(2)}", "label": p["label"] + " (salinan)", "version": 1, "verified": False})
    db.profiles.insert_one(p)
    audit(user, "platform", "Menduplikat profil platform", p["label"])
    return clean(p)


@app.post("/api/platform-profiles/{pid}/verify")
def verify_profile(pid: str, body: dict | None = None, user=Depends(current_user)):
    p = db.profiles.find_one({"id": pid})
    if not p:
        err(404, "Profil tidak ditemukan.")
    if not can_edit_profile(user, p):
        err(403, "Anda tidak bisa memvalidasi profil ini.")
    note = (body or {}).get("sourceNote") or f"Divalidasi {user['name']}"
    db.profiles.update_one({"id": pid}, {"$set": {"verified": True, "verifiedBy": user["name"], "verifiedAt": now_iso(),
                                                  "sourceNote": note}})
    audit(user, "platform", "Memvalidasi biaya platform", p.get("label", pid), note)
    return clean(db.profiles.find_one({"id": pid}))


@app.get("/api/platform-profiles/{pid}/versions")
def profile_versions(pid: str, user=Depends(current_user)):
    return [{"version": x["version"], "at": x["at"], "by": x["by"]} for x in db.profile_versions.find({"profileId": pid}).sort("version", -1)]


# ---------------------------------------------------------------------------
# settings & members
# ---------------------------------------------------------------------------

@app.put("/api/settings")
def put_settings(body: dict, user=Depends(require("head"))):
    allowed = {"safeDiscountGm", "lowMarginGm", "offlineMarginFloorPct", "onlineMarginFloorPct", "marketplaceMarginFloorPct",
               "psychPoints", "roundingStep", "weights", "fit", "baselines", "adminEmail", "appName"}
    upd = {k: v for k, v in body.items() if k in allowed}
    if body.get("adminPin"):
        upd["adminPinHash"] = hash_pin(str(body["adminPin"]))
    if body.get("regenerateShareToken"):
        upd["shareToken"] = secrets.token_urlsafe(24)
    before = get_settings()
    db.settings.update_one({"_id": "main"}, {"$set": upd})
    names = {"safeDiscountGm": "GM aman diskon", "lowMarginGm": "GM hindari gratis", "offlineMarginFloorPct": "Batas CM offline",
             "onlineMarginFloorPct": "Batas CM online food", "marketplaceMarginFloorPct": "Batas CM marketplace",
             "roundingStep": "Pembulatan harga", "weights": "Bobot rekomendasi", "adminEmail": "Email admin", "fit": "Matriks objective",
             "psychPoints": "Harga psikologis", "adminPinHash": "PIN Admin cadangan diganti", "shareToken": "Link Reporting dibuat ulang"}
    ch = []
    for k, v in upd.items():
        if before.get(k) == v:
            continue
        if k in ("adminPinHash", "shareToken"):
            ch.append(names[k])
        elif k in ("weights", "fit", "psychPoints", "baselines"):
            ch.append(names.get(k, k) + " diubah")
        else:
            ch.append(f"{names.get(k, k)} {before.get(k)} → {v}")
    if ch:
        audit(user, "settings", "Mengubah settings", "", "; ".join(ch))
    return public_settings(get_settings())


@app.put("/api/baselines")
def put_baselines(body: dict, user=Depends(require("head", "finance"))):
    s = get_settings()
    b = s.get("baselines") or {}
    pid, area = body.get("platformId"), body.get("area")
    old_b = dict((b.get(pid) or {}).get(area) or {})
    b.setdefault(pid, {})[area] = body.get("baseline") or {}
    db.settings.update_one({"_id": "main"}, {"$set": {"baselines": b}})
    nb = b[pid][area]
    audit(user, "settings", "Mengubah baseline", f"{(profiles_map().get(pid) or {}).get('label', pid)} · {area}",
          "; ".join(f"{k} {old_b.get(k)} → {nb.get(k)}" for k in sorted(set(old_b) | set(nb)) if old_b.get(k) != nb.get(k)))
    return b


@app.put("/api/members/{mid}")
def put_member(mid: str, body: dict, user=Depends(require("head"))):
    upd = {k: body[k] for k in ("role", "active", "platforms", "email", "phone") if k in body}
    target = db.members.find_one({"id": mid})
    if not target:
        err(404, "Anggota tidak ditemukan.")
    if "role" in upd and upd["role"] not in ROLES:
        err(400, "Role tidak dikenal.")
    losing = (upd.get("active") is False) or ("role" in upd and upd["role"] != "head")
    if losing and (target.get("isAdmin") or target.get("role") == "head"):
        if mid == user["id"]:
            err(400, "Anda tidak bisa menonaktifkan atau menurunkan role akun sendiri.")
        others = db.members.count_documents({"id": {"$ne": mid}, "active": {"$ne": False}, "hidden": {"$ne": True},
                                             "status": {"$nin": ["pending", "rejected", "invited"]},
                                             "$or": [{"isAdmin": True}, {"role": "head"}]})
        if others == 0:
            err(400, "Harus ada minimal satu Marketing Manager aktif.")
    if "role" in upd and upd["role"] in SIGNUP_SLOTS and target.get("role") != upd["role"]:
        slot = next(x for x in slot_status() if x["role"] == upd["role"])
        if not slot["open"]:
            err(400, f"Slot {slot['label']} sudah terisi.")
    db.members.update_one({"id": mid}, {"$set": upd})
    ch = []
    if "role" in upd and upd["role"] != target.get("role"):
        ch.append(f"Role {ROLES.get(target.get('role'), target.get('role'))} → {ROLES.get(upd['role'])}")
    if "active" in upd and upd["active"] != target.get("active", True):
        ch.append("Diaktifkan" if upd["active"] else "Dinonaktifkan")
    if "platforms" in upd and upd["platforms"] != target.get("platforms"):
        ch.append("Platform yang dipegang diubah")
    if ch:
        audit(user, "anggota", "Mengubah anggota", target.get("name", ""), "; ".join(ch))
    return {"ok": True}


AUDIT_CATS = {"promo": "Promo", "produk": "Produk & HPP", "platform": "Biaya platform", "settings": "Settings", "anggota": "Anggota",
              "belajar": "Data belajar", "kalender": "Kalender", "file": "File & import"}


@app.get("/api/audit")
def list_audit(category: str = "", by: str = "", q: str = "", limit: int = 200, user=Depends(no_viewer)):
    flt = {}
    if category in AUDIT_CATS:
        flt["category"] = category
    if by:
        flt["byId"] = by
    rows = clean(list(db.audit.find(flt).sort("at", -1).limit(max(1, min(int(limit), 500)) * (3 if q else 1))))
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in f"{r.get('action','')} {r.get('target','')} {r.get('detail','')} {r.get('byName','')} {r.get('file') or ''}".lower()]
    rows = rows[:max(1, min(int(limit), 500))]
    people = sorted({(r.get("byId"), r.get("byName")) for r in clean(list(db.audit.find({}, {"byId": 1, "byName": 1}))) if r.get("byId")},
                    key=lambda x: x[1] or "")
    return {"rows": rows, "categories": AUDIT_CATS, "people": [{"id": a, "name": b} for a, b in people], "total": db.audit.count_documents(flt)}


SETUP_DAYS = int(os.getenv("SETUP_DAYS", "14"))


def new_setup_token():
    return secrets.token_urlsafe(24), (datetime.now(timezone.utc) + timedelta(days=SETUP_DAYS)).isoformat()


def create_invited_member(name: str, email: str, role: str, by: dict | None):
    """Anggota yang ditambahkan langsung oleh Marketing Manager: sudah disetujui, tinggal membuat PIN lewat link aktivasi."""
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not name:
        raise ValueError("Isi nama anggota.")
    if not email.endswith("@" + EMAIL_DOMAIN) or email.count("@") != 1:
        raise ValueError(f"Gunakan email kantor @{EMAIL_DOMAIN}.")
    if role not in ROLES or role == "head":
        raise ValueError("Pilih role anggota.")
    if db.members.find_one({"email": email, "status": {"$ne": "rejected"}}):
        raise ValueError("Email ini sudah terdaftar.")
    if db.members.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "status": {"$ne": "rejected"}}):
        raise ValueError("Nama sudah terdaftar.")
    if role in SIGNUP_SLOTS:
        slot = next(x for x in slot_status() if x["role"] == role)
        if not slot["open"]:
            raise ValueError(f"Slot {slot['label']} sudah terisi.")
    tok, exp = new_setup_token()
    m = {"id": secrets.token_hex(6), "name": name, "role": role, "email": email, "phone": "", "pinHash": "", "active": True,
         "isAdmin": False, "status": "invited", "platforms": [], "createdAt": now_iso(), "setupToken": tok, "setupExpiresAt": exp,
         "addedBy": (by or {}).get("name") or "Sistem"}
    db.members.insert_one(m)
    audit(by, "anggota", "Menambah anggota", name, f"{ROLES[role]} · {email} (menunggu aktivasi)")
    return m


@app.post("/api/members")
def add_member(body: dict, user=Depends(require("head"))):
    try:
        m = create_invited_member(body.get("name"), body.get("email"), body.get("role"), user)
    except ValueError as e:
        err(400, str(e))
    return {"id": m["id"], "setupToken": m["setupToken"]}


@app.post("/api/members/{mid}/setup-link")
def renew_setup(mid: str, user=Depends(require("head"))):
    m = db.members.find_one({"id": mid})
    if not m or m.get("status") != "invited":
        err(400, "Anggota ini sudah aktif atau tidak ditemukan.")
    tok, exp = new_setup_token()
    db.members.update_one({"id": mid}, {"$set": {"setupToken": tok, "setupExpiresAt": exp}})
    audit(user, "anggota", "Membuat ulang link aktivasi", m.get("name", ""))
    return {"setupToken": tok}


def find_setup(token: str):
    if not token:
        return None
    m = db.members.find_one({"setupToken": token, "status": "invited", "active": {"$ne": False}})
    if not m or datetime.fromisoformat(m["setupExpiresAt"]) < datetime.now(timezone.utc):
        return None
    return m


@app.get("/api/public/setup/{token}")
def public_setup(token: str):
    m = find_setup(token)
    if not m:
        err(404, "Link aktivasi tidak valid atau kedaluwarsa. Minta link baru ke Marketing Manager.")
    return {"name": m["name"], "label": ROLES.get(m["role"], m["role"]), "email": m["email"]}


@app.post("/api/auth/setup")
def auth_setup(body: dict, request: Request):
    ip = f"ipreg:{client_ip(request)}"
    guard_lock(ip, IP_MAX)
    m = find_setup(body.get("token") or "")
    if not m:
        fail(ip)
        err(404, "Link aktivasi tidak valid atau kedaluwarsa. Minta link baru ke Marketing Manager.")
    pin = str(body.get("pin") or "")
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        err(400, "PIN harus 4–6 angka.")
    db.members.update_one({"id": m["id"]}, {"$set": {"pinHash": hash_pin(pin), "status": "approved", "activatedAt": now_iso(),
                                                    "phone": (body.get("phone") or "")[:20]},
                                           "$unset": {"setupToken": "", "setupExpiresAt": ""}})
    m = db.members.find_one({"id": m["id"]})
    audit(m, "anggota", "Mengaktifkan akun", m["name"], ROLES.get(m["role"], ""))
    return {"token": make_session(m), "user": {k: v for k, v in clean(m).items() if k not in ("pinHash",)}}


PRESET_MEMBERS = [
    ("Galuh Yusnindar", "galuh.yusnindar@citarasakuliner.com", "revenue_growth"),
    ("Kintan Asokawati", "kintan.asokawati@citarasakuliner.com", "team_leader"),
]


def seed_preset_members():
    """Tambahkan anggota yang diminta Marketing Manager (14 Nov 2026). Hanya jalan bila sudah ada Admin dan email belum terdaftar."""
    try:
        if db.members.count_documents({"isAdmin": True, "hidden": {"$ne": True}}) == 0:
            return
        for name, email, role in PRESET_MEMBERS:
            if db.members.find_one({"email": email}):
                continue
            try:
                create_invited_member(name, email, role, None)
                log.info("Anggota ditambahkan: %s (%s)", name, role)
            except ValueError as e:
                log.warning("Anggota %s tidak ditambahkan: %s", email, e)
    except Exception as e:  # pragma: no cover
        log.warning("Seed anggota gagal: %s", e)


seed_preset_members()


@app.post("/api/invites")
def create_invite(body: dict, user=Depends(require("head"))):
    role = body.get("role")
    if role not in ROLES or role == "head":
        err(400, "Pilih role yang akan diundang.")
    if role in SIGNUP_SLOTS:
        slot = next(x for x in slot_status() if x["role"] == role)
        pending_inv = db.invites.count_documents({"role": role, "usedAt": None, "revoked": {"$ne": True},
                                                  "expiresAt": {"$gt": now_iso()}})
        if not slot["open"]:
            err(400, f"Slot {slot['label']} sudah terisi.")
        if pending_inv >= slot["quota"] - slot["used"]:
            err(400, f"Masih ada undangan {slot['label']} yang aktif. Batalkan dulu bila ingin membuat yang baru.")
    email = (body.get("email") or "").strip().lower()
    if email and not email.endswith("@" + EMAIL_DOMAIN):
        err(400, f"Email undangan harus @{EMAIL_DOMAIN}.")
    from datetime import timedelta
    inv = {"token": secrets.token_urlsafe(24), "role": role, "email": email or None, "createdBy": user["name"], "createdAt": now_iso(),
           "expiresAt": (datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS)).isoformat(), "usedAt": None}
    db.invites.insert_one(inv)
    audit(user, "anggota", "Membuat link undangan", ROLES.get(role, role), email or "")
    return clean(inv)


@app.get("/api/invites")
def list_invites(user=Depends(require("head"))):
    out = []
    for i in db.invites.find({}).sort("createdAt", -1).limit(30):
        i = clean(i)
        i["state"] = "dipakai" if i.get("usedAt") else "dibatalkan" if i.get("revoked") else \
            "kedaluwarsa" if i["expiresAt"] < now_iso() else "aktif"
        out.append(i)
    return out


@app.delete("/api/invites/{token}")
def revoke_invite(token: str, user=Depends(require("head"))):
    inv = db.invites.find_one({"token": token}) or {}
    db.invites.update_one({"token": token}, {"$set": {"revoked": True}})
    audit(user, "anggota", "Membatalkan link undangan", ROLES.get(inv.get("role"), ""), inv.get("email") or "")
    return {"ok": True}


@app.post("/api/members/{mid}/approve")
def approve_member(mid: str, body: dict, user=Depends(require("head"))):
    m = db.members.find_one({"id": mid})
    if not m or m.get("status") != "pending":
        err(400, "Tidak ada pendaftaran yang menunggu untuk anggota ini.")
    if body.get("decision") == "approve":
        db.members.update_one({"id": mid}, {"$set": {"status": "approved", "approvedBy": user["name"], "approvedAt": now_iso()}})
    else:
        db.members.update_one({"id": mid}, {"$set": {"status": "rejected", "active": False, "rejectedBy": user["name"],
                                                     "rejectedAt": now_iso()}})
    audit(user, "anggota", "Menyetujui anggota" if body.get("decision") == "approve" else "Menolak pendaftaran", m.get("name", ""),
          f"{ROLES.get(m.get('role'), '')} · {m.get('email', '')}")
    return {"ok": True}


@app.post("/api/members/{mid}/reset-pin")
def reset_pin(mid: str, body: dict, user=Depends(require("head"))):
    pin = str(body.get("pin") or "")
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        err(400, "PIN baru harus 4–6 angka.")
    db.members.update_one({"id": mid}, {"$set": {"pinHash": hash_pin(pin)}})
    clear_fails(f"m:{mid}")
    audit(user, "anggota", "Mereset PIN anggota", (db.members.find_one({"id": mid}) or {}).get("name", ""))
    return {"ok": True}


# ---------------------------------------------------------------------------
# calendar
# ---------------------------------------------------------------------------
# Hari besar 2026–2027. Tanggal Islam & Imlek adalah *perkiraan, cek SKB pemerintah.
HOLIDAYS = [
    ("2026-12-12", None, "Harbolnas 12.12", "belanja"), ("2026-12-24", "2026-12-26", "Natal", "libur"),
    ("2026-12-31", "2027-01-01", "Tahun Baru", "libur"), ("2027-02-06", None, "Imlek*", "libur"),
    ("2027-02-08", "2027-03-09", "Ramadan*", "musim"), ("2027-02-14", None, "Valentine", "momen"),
    ("2027-03-10", "2027-03-11", "Idul Fitri*", "libur"), ("2027-03-09", None, "Nyepi*", "libur"),
    ("2027-03-26", None, "Jumat Agung*", "libur"), ("2027-05-01", None, "Hari Buruh", "libur"),
    ("2027-05-06", None, "Kenaikan Isa Almasih*", "libur"), ("2027-05-17", None, "Idul Adha*", "libur"),
    ("2027-05-20", None, "Waisak*", "libur"), ("2027-06-01", None, "Hari Lahir Pancasila", "libur"),
    ("2027-06-07", None, "Tahun Baru Islam*", "libur"), ("2027-08-17", None, "HUT RI", "libur"),
    ("2027-08-16", None, "Maulid Nabi*", "libur"), ("2027-12-12", None, "Harbolnas 12.12", "belanja"),
    ("2027-12-25", None, "Natal", "libur"),
]


def moments_between(start: date, end: date, settings: dict):
    out = []
    d = date(start.year, start.month, 1)
    while d <= end:
        y, m = d.year, d.month
        twin = date(y, m, m) if m <= 28 or m in (1, 3, 5, 7, 8, 10, 12) or m <= 30 else None
        if twin and start <= twin <= end and m >= 1:
            out.append({"date": twin.isoformat(), "end": None, "label": f"Tanggal kembar {m}.{m}", "type": "belanja"})
        g1 = date(y, m, 25)
        g2 = date(y, m, 28)
        if g2 >= start and g1 <= end:
            out.append({"date": g1.isoformat(), "end": g2.isoformat(), "label": "Gajian", "type": "gajian"})
        d = date(y + (m == 12), m % 12 + 1, 1)
    for a, b, label, typ in HOLIDAYS:
        da, db_ = date.fromisoformat(a), date.fromisoformat(b or a)
        if db_ >= start and da <= end:
            out.append({"date": a, "end": b, "label": label, "type": typ})
    for mo in settings.get("moments") or []:
        try:
            da, db_ = date.fromisoformat(mo["date"]), date.fromisoformat(mo.get("end") or mo["date"])
        except Exception:
            continue
        if db_ >= start and da <= end:
            out.append({"date": mo["date"], "end": mo.get("end"), "label": mo.get("label", "Momen"), "type": mo.get("type", "momen"),
                        "custom": True, "id": mo.get("id")})
    seen, uniq = set(), []
    for x in sorted(out, key=lambda x: x["date"]):
        k = (x["date"], x["label"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


@app.get("/api/calendar")
def calendar(start: str = "", end: str = "", user=Depends(current_user)):
    try:
        ds = date.fromisoformat(start) if start else date(today().year, today().month, 1)
        de = date.fromisoformat(end) if end else ds.replace(day=28)
    except ValueError:
        err(400, "Format tanggal harus YYYY-MM-DD.")
    if de < ds:
        ds, de = de, ds
    if (de - ds).days > 400:
        err(400, "Rentang kalender maksimal 400 hari.")
    s = get_settings()
    P = products_map()
    profs = profiles_map()
    rows = []
    for p in db.promos.find({}):
        try:
            a, b = date.fromisoformat(p.get("periodStart")), date.fromisoformat(p.get("periodEnd"))
        except Exception:
            continue
        if b < a:
            a, b = b, a
        st, waiting = effective_status(p)
        sm = next(iter((p.get("summary") or {}).values()), {})
        prof = profs.get(p.get("platformProfileId"), {})
        rows.append({"id": p["id"], "kode": p.get("kode"), "nama": p.get("nama"), "status": p.get("status"), "effectiveStatus": st,
                     "waitingActual": waiting, "platformProfileId": p.get("platformProfileId"), "platformLabel": prof.get("label", "?"),
                     "channelType": prof.get("channelType", "offline"), "areas": p.get("areas") or ["bandung"],
                     "periodStart": a.isoformat(), "periodEnd": b.isoformat(), "mechanism": E.MECHANISMS.get(p.get("mechanism"), ""),
                     "products": sorted({i.get("productId") for i in p.get("items") or [] if i.get("productId")}),
                     "productNames": [P.get(i.get("productId"), {}).get("nama", "?") for i in p.get("items") or []],
                     "quadrant": sm.get("quadrant"), "gate": sm.get("gate"), "health": (sm.get("health") or {}).get("label"),
                     "_a": a, "_b": b})
    active = [r for r in rows if r["effectiveStatus"] != "rejected"]
    conflicts = []
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            x, y = active[i], active[j]
            lo, hi = max(x["_a"], y["_a"]), min(x["_b"], y["_b"])
            if lo > hi or hi < ds or lo > de:
                continue
            areas = set(x["areas"]) & set(y["areas"])
            prods = set(x["products"]) & set(y["products"])
            if not areas or not prods:
                continue
            names = ", ".join(sorted({P.get(pid, {}).get("nama", pid) for pid in prods}))
            if x["platformProfileId"] == y["platformProfileId"]:
                typ, msg = "bentrok", f"{names} dipromokan dua kali di {x['platformLabel']} pada tanggal yang sama"
            elif x["channelType"] == y["channelType"] != "event":
                typ, msg = "harga", f"{names} punya harga promo berbeda di {x['platformLabel']} dan {y['platformLabel']}"
            else:
                continue
            conflicts.append({"type": typ, "a": x["id"], "b": y["id"], "aName": x["nama"], "bName": y["nama"],
                              "from": lo.isoformat(), "to": hi.isoformat(), "areas": sorted(areas), "message": msg})
    # too many concurrent promos on one platform
    by_plat = {}
    for r in active:
        by_plat.setdefault(r["platformProfileId"], []).append(r)
    d = ds
    flagged = set()
    while d <= de:
        for pid, lst in by_plat.items():
            live = [r for r in lst if r["_a"] <= d <= r["_b"]]
            if len(live) >= 3 and pid not in flagged:
                flagged.add(pid)
                conflicts.append({"type": "padat", "a": live[0]["id"], "b": live[1]["id"], "aName": live[0]["nama"], "bName": live[1]["nama"],
                                  "from": d.isoformat(), "to": d.isoformat(), "areas": [],
                                  "message": f"{len(live)} promo berjalan bersamaan di {live[0]['platformLabel']} — crew dan customer bisa bingung"})
        d = d.fromordinal(d.toordinal() + 1)
    for r in rows:
        r.pop("_a"), r.pop("_b")
    vis = [r for r in rows if r["periodEnd"] >= ds.isoformat() and r["periodStart"] <= de.isoformat()]
    return {"start": ds.isoformat(), "end": de.isoformat(), "promos": vis, "conflicts": conflicts,
            "moments": moments_between(ds, de, s)}


def promo_rows():
    profs = profiles_map()
    rows = []
    for p in db.promos.find({}):
        try:
            a, b = date.fromisoformat(p.get("periodStart")), date.fromisoformat(p.get("periodEnd"))
        except Exception:
            continue
        st, _ = effective_status(p)
        prof = profs.get(p.get("platformProfileId"), {})
        rows.append({"id": p["id"], "nama": p.get("nama"), "effectiveStatus": st, "platformProfileId": p.get("platformProfileId"),
                     "platformLabel": prof.get("label", "?"), "channelType": prof.get("channelType", "offline"),
                     "areas": p.get("areas") or ["bandung"], "periodStart": min(a, b).isoformat(), "periodEnd": max(a, b).isoformat(),
                     "products": sorted({i.get("productId") for i in p.get("items") or [] if i.get("productId")})})
    return rows


def timing_history():
    return learning_records()


def duration_history(mechanism: str):
    return [(r["days"], r["perf"]) for r in learning_records() if r["mechanism"] == mechanism]


def advice_for(promo: dict, o: dict, ch: str) -> dict:
    u = o["unit"]
    cur = None
    try:
        cur = (date.fromisoformat(promo["periodEnd"]) - date.fromisoformat(promo["periodStart"])).days + 1
        cur = cur if cur > 0 else None
    except Exception:
        pass
    t = o["scenarios"]["target"]
    days = o["scenarios"]["meta"].get("days") or 1
    ev = (o["scenarios"]["meta"].get("event") or {}).get("days")
    strat = promo.get("strategic") or {}
    return T.duration_advice(promo.get("mechanism"), promo.get("objective"), ch, pct_of(u), o["health"]["label"],
                             (promo.get("params") or {}).get("n"), ev, (t.get("merchantDiscount") or 0) / days,
                             float(strat["maxInvestment"]) if strat.get("isStrategic") and strat.get("maxInvestment") else None,
                             duration_history(promo.get("mechanism")), cur)


def pct_of(u: dict) -> float:
    return (u.get("perceivedSaving", u.get("discountTotal", 0)) / u["listPrice"] * 100) if u.get("listPrice") else 0


def clean_ctx(ctx: dict) -> dict:
    """Drop or coerce anything that is not a valid timing input so bad values never crash the bot."""
    out = dict(ctx or {})
    for k in ("from", "to", "checkStart", "checkEnd"):
        if out.get(k) is not None:
            try:
                date.fromisoformat(str(out[k]))
            except ValueError:
                out.pop(k)
    if out.get("from") and out.get("to") and out["from"] > out["to"]:
        out["from"], out["to"] = out["to"], out["from"]
    if out.get("checkStart") and out.get("checkEnd") and out["checkEnd"] < out["checkStart"]:
        out.pop("checkEnd")
    if out.get("duration") is not None:
        try:
            out["duration"] = max(1, min(int(float(out["duration"])), 60))
        except (TypeError, ValueError):
            out.pop("duration")
    if out.get("objective") not in T.OBJ_LABEL:
        out.pop("objective", None)
    for k in ("products", "areas"):
        if out.get(k) is not None and not isinstance(out[k], list):
            out.pop(k)
    if out.get("areas"):
        out["areas"] = [a for a in out["areas"] if a in ("bandung", "jakarta")] or None
        if not out["areas"]:
            out.pop("areas")
    for k in ("discountPct", "stampN"):
        if out.get(k) is not None:
            try:
                out[k] = float(out[k])
            except (TypeError, ValueError):
                out.pop(k)
    if out.get("mechanism") not in E.MECHANISMS:
        out.pop("mechanism", None)
    return out


def run_timing(ctx: dict):
    ctx = clean_ctx(ctx)
    profs = profiles_map()
    prof = profs.get(ctx.get("platformProfileId"))
    if not prof:
        err(400, "Pilih platform/channel dulu.")
    t0 = today()
    req = {**ctx, "channelType": prof["channelType"]}
    h_to = date.fromisoformat(ctx["to"]) if ctx.get("to") else t0 + timedelta(days=120)
    mo = moments_between(t0, h_to + timedelta(days=70), get_settings())
    res = T.recommend_timing(req, promo_rows(), mo, t0, timing_history())
    res["platformLabel"] = prof["label"]
    return res


@app.post("/api/timing")
def api_timing(body: dict, user=Depends(current_user)):
    return run_timing(body)


def ctx_from_promo(pid: str) -> dict:
    p = db.promos.find_one({"id": pid})
    if not p:
        return {}
    try:
        dur = (date.fromisoformat(p["periodEnd"]) - date.fromisoformat(p["periodStart"])).days + 1
    except Exception:
        dur = None
    return {"platformProfileId": p.get("platformProfileId"), "objective": p.get("objective"), "areas": p.get("areas"),
            "products": sorted({i.get("productId") for i in p.get("items") or [] if i.get("productId")}),
            "duration": dur, "excludeId": p["id"], "promoName": p.get("nama"), "mechanism": p.get("mechanism"),
            "discountPct": round((next(iter((p.get("summary") or {}).values()), {}).get("discountPct") or 0) * 100, 1),
            "health": (next(iter((p.get("summary") or {}).values()), {}).get("health") or {}).get("label"),
            "stampN": (p.get("params") or {}).get("n"),
            "checkStart": p.get("periodStart"), "checkEnd": p.get("periodEnd")}


@app.post("/api/bot")
def api_bot(body: dict, user=Depends(current_user)):
    P = products_map()
    profs = profiles_map()
    ctx = dict(body.get("context") or {})
    if body.get("promoId"):
        ctx.update({k: v for k, v in ctx_from_promo(body["promoId"]).items() if v})
    if body.get("prefill"):
        ctx.update({k: v for k, v in body["prefill"].items() if v not in (None, "", [])})
    msg = body.get("message") or ""
    if ctx.pop("durationAuto", None):
        ctx.pop("duration", None)
    if msg:
        ctx = T.parse_message(msg, ctx, P, profs, today())
        mech, dpct = T.parse_mechanism(msg)
        if mech:
            ctx["mechanism"] = mech
        if dpct is not None:
            ctx["discountPct"] = dpct
    if body.get("set"):
        for k, v in body["set"].items():
            if v is None:
                ctx.pop(k, None)
            else:
                ctx[k] = v
    ctx = clean_ctx(ctx)
    if ctx.get("platformProfileId") not in profs:
        ctx.pop("platformProfileId", None)
    need = T.missing(ctx)
    if need:
        if "platform" in need:
            return {"context": ctx, "reply": "Promo ini mau dijalankan di channel mana?",
                    "chips": [{"label": p["label"], "set": {"platformProfileId": p["id"]}} for p in profs.values()
                              if not p["label"].endswith("(lama)")]}
        return {"context": ctx, "reply": "Tujuan utamanya apa? Ini menentukan apakah saya cari hari ramai atau hari sepi.",
                "chips": [{"label": T.OBJ_LABEL[k].capitalize(), "set": {"objective": k}} for k in T.OBJ_LABEL]}
    prof_b = profs.get(ctx["platformProfileId"]) or {}
    adv = T.duration_advice(ctx.get("mechanism"), ctx.get("objective"), prof_b.get("channelType"), ctx.get("discountPct"),
                            ctx.get("health"), ctx.get("stampN"),
                            (prof_b.get("eventDefaults") or {}).get("days") if prof_b.get("channelType") == "event" else None,
                            hist=duration_history(ctx.get("mechanism")) if ctx.get("mechanism") else None,
                            current=ctx.get("duration"))
    if not ctx.get("duration"):
        ctx["duration"] = adv["rec"]
        ctx["durationAuto"] = True
    res = run_timing(ctx)
    if res.get("error"):
        return {"context": ctx, "reply": res["error"], "chips": []}
    res["durationAdvice"] = adv
    prod = ", ".join(P[x]["nama"] for x in (ctx.get("products") or [])[:3] if x in P)
    who = f" untuk {prod}" if prod else ""
    lines = []
    if res.get("check"):
        c = res["check"]
        nm = f" untuk {ctx['promoName']}" if ctx.get("promoName") else ""
        lines.append(f"Tanggal **{c['range']}**{nm} mendapat skor **{c['score']}/100** ({c['verdict']}).")
        if c["reasons"]:
            lines.append("Alasannya: " + "; ".join(c["reasons"]) + ".")
        if c["cautions"]:
            lines.append("Perhatian: " + "; ".join(c["cautions"]) + ".")
        best = res["recommendations"][0] if res["recommendations"] else None
        if best and c["gapToBest"] >= 10:
            lines.append(f"Ada pilihan lebih baik: **{best['range']}** (skor {best['score']}).")
    else:
        best = res["recommendations"][0]
        lines.append(f"Untuk {T.OBJ_LABEL.get(res['objective'], res['objective'])} di {res['platformLabel']}{who}, waktu terbaik "
                     f"**{best['range']}** (mulai {best['startDay']}), skor **{best['score']}/100**.")
        lines.append("Alasannya: " + "; ".join(best["reasons"]) + ".")
        if best["cautions"]:
            lines.append("Perhatian: " + "; ".join(best["cautions"]) + ".")
        alts = res["recommendations"][1:]
        if alts:
            lines.append("Alternatif: " + ", ".join(f"{a['range']} (skor {a['score']})" for a in alts) + ".")
        av = res["avoid"]
        lines.append(f"Sebaiknya hindari {av['range']} (skor {av['score']}): {av['whyLow']}.")
    mech_l = f" untuk {E.MECHANISMS[ctx['mechanism']].lower()}" if ctx.get("mechanism") in E.MECHANISMS else ""
    if ctx.get("durationAuto"):
        dl = f"Durasi yang saya sarankan{mech_l}: **{adv['rec']} hari** (rentang wajar {adv['min']}–{adv['max']} hari)."
    elif adv["status"] == "pas":
        dl = f"Durasi {res['duration']} hari sudah pas{mech_l} (rentang wajar {adv['min']}–{adv['max']} hari)."
    else:
        dl = f"Durasi {res['duration']} hari **{adv['status']}**{mech_l}; saran saya **{adv['rec']} hari** (rentang {adv['min']}–{adv['max']} hari)."
    lines.append(dl + " " + "; ".join(adv["reasons"]) + "." + (f" {adv['checkpoint']}." if adv.get("checkpoint") else ""))
    lines.append(f"{res['method']} Skor 100 = pilihan terbaik dalam rentang yang dinilai. Persiapan minimal H-{res['leadDays']}.")
    if res.get("historyNote"):
        lines.append(res["historyNote"])
    recs_l = learning_records()
    sim = [r for r in recs_l if r["platformProfileId"] == ctx["platformProfileId"]
           and (r["mechanism"] == ctx.get("mechanism") if ctx.get("mechanism") else r["objective"] == ctx.get("objective"))][:2]
    if sim:
        def how(r):
            if r["achievement"] is not None:
                return f"{r['achievement']*100:.0f}% target"
            return T.RATING_LABEL.get(r["rating"] or 0, "hasil tercatat").lower()
        lines.append("Promo serupa sebelumnya: " + "; ".join(
            f"{r['nama']} ({T.fmt_range(date.fromisoformat(r['periodStart']), date.fromisoformat(r['periodEnd']))}, {r['days']} hari) → {how(r)}"
            + (f", take rate {r['takeRate']:g}%" if r["takeRate"] is not None else "") for r in sim) + ".")
    ln = res.get("learning") or {}
    if not ln.get("active"):
        lines.append(f"Catatan: baru ada {ln.get('n', 0)} hasil promo untuk channel ini, jadi saya masih memakai asumsi awal. "
                     "Tambahkan hasil promo lama di menu Data belajar (minimal 3) supaya saran mengikuti data CRK.")
    chips = ([] if ctx.get("durationAuto") or adv["status"] == "pas" else
             [{"label": f"Pakai saran {adv['rec']} hari", "set": {"duration": adv["rec"]}}]) + [
             {"label": "7 hari", "set": {"duration": 7}}, {"label": "14 hari", "set": {"duration": 14}},
             {"label": "30 hari", "set": {"duration": 30}}, {"label": "Bulan depan", "message": "bulan depan"},
             {"label": "Ganti objective", "set": {"objective": None}}, {"label": "Ganti channel", "set": {"platformProfileId": None}}]
    return {"context": ctx, "reply": "\n\n".join(lines), "result": res, "chips": chips}


LEARN_FIELDS = ("nama", "platformProfileId", "mechanism", "objective", "areas", "periodStart", "periodEnd", "rating", "takeRate",
                "upliftPct", "achievement", "note", "discountPct")


def clean_learning(body: dict, profs: dict) -> dict:
    d = {k: body.get(k) for k in LEARN_FIELDS}
    if not (d["nama"] or "").strip():
        raise ValueError("Isi nama promo.")
    if d["platformProfileId"] not in profs:
        raise ValueError("Pilih channel/platform yang tersedia.")
    if d["mechanism"] not in E.MECHANISMS:
        raise ValueError("Pilih jenis promo.")
    if d["objective"] not in E.OBJECTIVES:
        d["objective"] = None
    try:
        ds, de = date.fromisoformat(str(d["periodStart"])), date.fromisoformat(str(d["periodEnd"]))
    except ValueError:
        raise ValueError("Isi tanggal mulai dan selesai (YYYY-MM-DD).")
    if de < ds:
        raise ValueError("Tanggal selesai harus setelah tanggal mulai.")
    if ds > today():
        raise ValueError("Data belajar hanya untuk promo yang sudah berjalan.")
    def num(k, lo, hi):
        v = d.get(k)
        if v in (None, ""):
            return None
        v = float(str(v).replace(",", "."))
        if not lo <= v <= hi:
            raise ValueError(f"Nilai {k} di luar batas.")
        return v
    try:
        d["rating"] = int(num("rating", 1, 5)) if d.get("rating") not in (None, "") else None
        d["takeRate"] = num("takeRate", 0, 100)
        d["upliftPct"] = num("upliftPct", -100, 1000)
        ach = num("achievement", 0, 1000)
        d["achievement"] = (ach / 100 if ach is not None and ach > 5 else ach)
        d["discountPct"] = num("discountPct", 0, 100)
    except (TypeError, ValueError) as e:
        raise ValueError(str(e) if "batas" in str(e) else "Ada angka yang tidak valid.")
    if d["rating"] is None and d["achievement"] is None and d["upliftPct"] is None:
        raise ValueError("Isi minimal satu ukuran hasil: penilaian, pencapaian vs target, atau kenaikan revenue.")
    d["areas"] = [a for a in (d.get("areas") or []) if a in ("bandung", "jakarta")] or ["bandung"]
    d["nama"] = d["nama"].strip()[:80]
    d["note"] = (d.get("note") or "")[:400]
    return d


def learning_insights(recs):
    by_ch = {}
    for ch in ("offline", "online_food", "marketplace", "event"):
        L = T.learn(recs, ch)
        by_ch[ch] = {"n": L["n"], "active": L["n"] >= 3, "notes": L["notes"]}
    groups = {}
    for r in recs:
        if r["perf"] is None:
            continue
        groups.setdefault((r["mechanism"], r["platformLabel"]), []).append(r)
    mech = []
    for (m, pl), xs in groups.items():
        tr = [x["takeRate"] for x in xs if x["takeRate"] is not None]
        good = [x["days"] for x in xs if x["perf"] >= 1]
        mech.append({"mechanism": m, "label": E.MECHANISMS.get(m, m), "platformLabel": pl, "n": len(xs),
                     "avgPerf": sum(x["perf"] for x in xs) / len(xs), "avgTakeRate": sum(tr) / len(tr) if tr else None,
                     "bestDays": round(sum(good) / len(good)) if good else None})
    mech.sort(key=lambda x: -x["avgPerf"])
    return {"total": len(recs), "byChannel": by_ch, "mechanisms": mech}


@app.get("/api/learnings")
def list_learnings(user=Depends(current_user)):
    recs = learning_records()
    return {"records": recs, "insights": learning_insights(recs)}


@app.post("/api/learnings")
def add_learning(body: dict, user=Depends(require("head", "planner", "finance", "channel_pic"))):
    try:
        d = clean_learning(body, profiles_map())
    except ValueError as e:
        err(400, str(e))
    d.update({"id": secrets.token_hex(5), "by": user["name"], "byId": user["id"], "createdAt": now_iso()})
    db.learnings.insert_one(d)
    audit(user, "belajar", "Menambah hasil promo", d["nama"], f"{d['periodStart']} s.d. {d['periodEnd']}")
    return clean(d)


@app.delete("/api/learnings/{lid}")
def del_learning(lid: str, user=Depends(require("head", "planner", "finance", "channel_pic"))):
    r = db.learnings.find_one({"id": lid})
    if not r:
        err(404, "Data tidak ditemukan.")
    if not (user.get("isAdmin") or user["perm"] == "head" or r.get("byId") == user["id"]):
        err(403, "Hanya pembuat data atau Marketing Manager yang bisa menghapus.")
    db.learnings.delete_one({"id": lid})
    audit(user, "belajar", "Menghapus hasil promo", r.get("nama", ""))
    return {"ok": True}


@app.post("/api/learnings/import")
async def import_learnings(request: Request, user=Depends(require("head", "planner", "finance", "channel_pic"))):
    text = (await request.body()).decode("utf-8-sig")
    profs = profiles_map()
    sample = text.splitlines()[0] if text.strip() else ""
    delim = ";" if sample.count(";") > sample.count(",") else ","
    mech_by_label = {v.lower(): k for k, v in E.MECHANISMS.items()}
    obj_by_label = {v.lower(): k for k, v in E.OBJECTIVES.items()}
    ok, errors = 0, []
    for i, row in enumerate(csv.DictReader(io.StringIO(text), delimiter=delim), start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not any(row.values()):
            continue
        plat = row.get("platform", "").lower()
        pid = next((p["id"] for p in profs.values() if plat and (plat == p["id"] or plat in p["label"].lower())), None)
        mech = row.get("jenis_promo", "").lower()
        mid = mech if mech in E.MECHANISMS else mech_by_label.get(mech) or (T.parse_mechanism(mech)[0] if mech else None)
        obj = row.get("tujuan", "").lower()
        area = row.get("area", "").lower()
        body = {"nama": row.get("nama"), "platformProfileId": pid, "mechanism": mid,
                "objective": obj if obj in E.OBJECTIVES else obj_by_label.get(obj),
                "areas": ["jakarta"] if "jak" in area or "jabo" in area else ["bandung"],
                "periodStart": row.get("mulai"), "periodEnd": row.get("selesai"), "rating": row.get("hasil_1_5"),
                "takeRate": row.get("take_rate_pct"), "upliftPct": row.get("kenaikan_revenue_pct"),
                "achievement": row.get("pencapaian_target_pct"), "discountPct": row.get("diskon_pct"), "note": row.get("catatan")}
        if body["achievement"] not in (None, ""):
            try:
                body["achievement"] = float(str(body["achievement"]).replace(",", ".")) / 100
            except ValueError:
                pass
        try:
            d = clean_learning(body, profs)
        except ValueError as e:
            errors.append(f"Baris {i}: {e}")
            continue
        d.update({"id": secrets.token_hex(5), "by": user["name"], "byId": user["id"], "createdAt": now_iso()})
        db.learnings.insert_one(d)
        ok += 1
    audit(user, "file", "Mengimport file hasil promo", f"{ok} hasil promo", f"{len(errors)} baris ditolak" if errors else "",
          request.headers.get("x-filename"))
    return {"imported": ok, "errors": errors[:20]}


@app.get("/api/backup")
def backup(user=Depends(require("head"))):
    data = {"exportedAt": now_iso(), "app": "CRK Promo Calculator"}
    for col in ("products", "profiles", "promos", "promo_logs", "comments", "learnings", "price_versions", "profile_versions", "invites"):
        data[col] = clean(list(db[col].find({})))
    data["settings"] = public_settings(get_settings())
    data["members"] = [{k: v for k, v in clean(m).items() if k not in ("pinHash", "setupToken")} for m in db.members.find({})]
    data["audit"] = clean(list(db.audit.find({})))
    audit(user, "file", "Mengunduh backup data", "Backup")
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="crk-promo-backup-{today().isoformat()}.json"'})


@app.post("/api/moments")
def add_moment(body: dict, user=Depends(require("head", "planner", "finance"))):
    try:
        date.fromisoformat(body.get("date") or "")
        if body.get("end"):
            date.fromisoformat(body["end"])
    except ValueError:
        err(400, "Isi tanggal momen dengan benar.")
    if body.get("end") and body["end"] < body["date"]:
        err(400, "Tanggal selesai momen harus setelah tanggal mulai.")
    if not (body.get("label") or "").strip():
        err(400, "Isi nama momen.")
    mo = {"id": secrets.token_hex(4), "date": body["date"], "end": body.get("end") or None, "label": body["label"].strip()[:60],
          "type": body.get("type") or "momen", "by": user["name"]}
    db.settings.update_one({"_id": "main"}, {"$push": {"moments": mo}})
    audit(user, "kalender", "Menambah momen", mo["label"], mo["date"] + (f" s.d. {mo['end']}" if mo.get("end") else ""))
    return mo


@app.delete("/api/moments/{mid}")
def del_moment(mid: str, user=Depends(require("head", "planner", "finance"))):
    old_m = next((x for x in get_settings().get("moments") or [] if x.get("id") == mid), {})
    db.settings.update_one({"_id": "main"}, {"$pull": {"moments": {"id": mid}}})
    audit(user, "kalender", "Menghapus momen", old_m.get("label", ""))
    return {"ok": True}


# ---------------------------------------------------------------------------
# seed, report, export, metrics
# ---------------------------------------------------------------------------

@app.post("/api/seed/crk")
def seed_crk(user=Depends(require("head"))):
    if db.products.count_documents({}) > 0:
        err(400, "Data sudah ada. Import hanya untuk database kosong.")
    db.products.insert_many(copy.deepcopy(S.PRODUCTS))
    db.profiles.insert_many(copy.deepcopy(S.PROFILES))
    db.settings.update_one({"_id": "main"}, {"$set": {"baselines": copy.deepcopy(S.BASELINES), "priceVersion": 1}})
    db.price_versions.insert_one({"version": 1, "at": now_iso(), "by": user["name"], "note": "Price Structure v2 (10 Nov 2026)",
                                  "products": copy.deepcopy(S.PRODUCTS)})
    for h in S.history_promos():
        h.update({"createdBy": user["name"], "createdById": user["id"], "createdAt": now_iso(), "updatedAt": now_iso()})
        save_results(h)
        db.promos.insert_one(h)
        log_promo(h["id"], user, "create", "Import data CRK")
    audit(user, "file", "Mengimport data awal CRK", f"{len(S.PRODUCTS)} produk, {len(S.PROFILES)} profil platform", "Price Structure v2")
    return {"ok": True, "products": len(S.PRODUCTS), "profiles": len(S.PROFILES)}


@app.get("/api/report")
def report(t: str = ""):
    s = get_settings()
    if not t or t != s.get("shareToken"):
        err(404, "Link laporan tidak valid.")
    P = products_map()
    profs = profiles_map()
    out = []
    for p in db.promos.find({"status": {"$in": ["approved", "running", "done"]}}).sort("periodStart", -1):
        st, waiting = effective_status(p)
        sm = p.get("summary") or {}
        items = " + ".join(f"{i.get('qty',1)}× {P.get(i['productId'], {}).get('nama','?')}" + (" (gratis)" if i.get("role") == "free" else "")
                           for i in p.get("items") or [])
        areas = {}
        for a, x in sm.items():
            areas[a] = {"listPrice": x["listPrice"], "customerPays": x["customerPays"], "discountPct": x["discountPct"],
                        "health": x["health"]["label"], "margin": x["margin"]["label"], "menarik": x["menarik"]["label"],
                        "quadrant": x["quadrant"], "gate": x["gate"]}
        act = p.get("actual") or {}
        out.append({"kode": p.get("kode"), "nama": p.get("nama"), "status": st, "mechanism": E.MECHANISMS.get(p.get("mechanism")),
                    "platform": profs.get(p.get("platformProfileId"), {}).get("label"), "periodStart": p.get("periodStart"),
                    "periodEnd": p.get("periodEnd"), "items": items, "areas": areas,
                    "achievement": act.get("achievementDetail"), "learningHeadline": act.get("learningHeadline"),
                    "learning": act.get("learning"), "nextAction": act.get("nextAction")})
    return {"appName": s.get("appName"), "generatedAt": now_iso(), "promos": out}


def csv_response(rows, name):
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@app.get("/api/export/{kind}.csv")
def export(kind: str, token: str = "", authorization: Optional[str] = Header(None)):
    user = current_user(authorization or f"Bearer {token}")
    if not (user.get("isAdmin") or user["perm"] in ("head", "finance")):
        err(403, "Export hanya untuk Marketing Manager, Finance, atau Revenue Growth.")
    if kind == "products":
        rows = [{"id": p["id"], "sku": p.get("sku"), "nama": p["nama"], "kategori": p.get("kategori"), "porsi": p.get("porsi"),
                 "hpp": p["hpp"], "harga_bandung": (p.get("prices") or {}).get("bandung"),
                 "harga_jakarta": (p.get("prices") or {}).get("jakarta"), "channels": "|".join(p.get("channels") or [])}
                for p in products_map().values()]
    elif kind == "promos":
        rows = []
        for p in db.promos.find({}):
            for a, x in (p.get("summary") or {}).items():
                rows.append({"kode": p.get("kode"), "nama": p.get("nama"), "status": p.get("status"), "area": a,
                             "platform": p.get("platformProfileId"), "mekanisme": p.get("mechanism"),
                             "harga_normal": x["listPrice"], "harga_promo": x["customerPays"], "hemat_pct": round(x["discountPct"] * 100, 1),
                             "cm": x["cm"], "cm_pct": round(x["cmPct"] * 100, 1), "sehat": x["health"]["label"],
                             "margin": x["margin"]["label"], "menarik": x["menarik"]["label"], "kuadran": x["quadrant"],
                             "gate": x["gate"], "contribution_target": x["targetContribution"]})
    elif kind == "platforms":
        rows = []
        for p in profiles_map().values():
            for c in p.get("feeComponents") or []:
                rows.append({"profil": p["label"], "komponen": c.get("label"), "tipe": c.get("type"), "rate": c.get("rate"),
                             "amount": c.get("amount"), "base": c.get("base"), "berlaku": c.get("appliesWhen"),
                             "terverifikasi": p.get("verified")})
    else:
        err(404, "Jenis export tidak dikenal.")
    return csv_response(rows, kind)


@app.get("/api/public-metrics")
def public_metrics(key: str = ""):
    if key != METRICS_API_KEY:
        err(403, "Key salah.")
    promos = list(db.promos.find({}))
    running = [p for p in promos if effective_status(p)[0] == "running"]
    sums = [x for p in promos for x in (p.get("summary") or {}).values()]
    month = today().strftime("%Y-%m")
    return {"running": len(running),
            "avgHealthScore": round(sum(x["health"]["score"] for x in sums) / len(sums)) if sums else None,
            "stars": sum(1 for x in sums if x["quadrant"] == "Star"),
            "marginTraps": sum(1 for x in sums if x["quadrant"] == "Margin Trap"),
            "contributionMtd": sum((p.get("actual") or {}).get("contribution") or 0 for p in promos
                                   if ((p.get("actual") or {}).get("at") or "").startswith(month)),
            "pendingApproval": sum(1 for p in promos if p.get("status") in ("review_finance", "review_head")),
            "unverifiedPlatforms": db.profiles.count_documents({"verified": False})}


# ---------------------------------------------------------------------------
# static frontend
# ---------------------------------------------------------------------------
STATIC = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
