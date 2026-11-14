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
        used = db.members.count_documents({"role": role, "status": {"$in": ["pending", "approved"]}, "active": {"$ne": False}})
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
    m["perm"] = perm_of(m["role"])
    return m


def require(*roles):
    def dep(user=Depends(current_user)):
        if user.get("isAdmin") or user["perm"] in roles:
            return user
        err(403, "Akses ditolak untuk role Anda.")
    return dep


def log_promo(pid, user, action, note=""):
    db.promo_logs.insert_one({"promoId": pid, "at": now_iso(), "byId": user["id"], "byName": user["name"],
                              "action": action, "note": note})


# ---------------------------------------------------------------------------
# data helpers
# ---------------------------------------------------------------------------

def products_map():
    return {p["id"]: clean(p) for p in db.products.find({})}


def profiles_map():
    return {p["id"]: clean(p) for p in db.profiles.find({})}


def baseline_for(settings, pid, area):
    return ((settings.get("baselines") or {}).get(pid) or {}).get(area) or {}


def history_list():
    out = []
    for p in db.promos.find({"status": "done"}):
        a = p.get("actual") or {}
        if a.get("takeRate") is not None or a.get("achievement") is not None:
            out.append({"mechanism": p.get("mechanism"), "platformId": p.get("platformProfileId"),
                        "takeRate": a.get("takeRate"), "achievement": a.get("achievement")})
    return out


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
    if not m or not m.get("active", True) or not check_pin(str(body.get("pin") or ""), m.get("pinHash", "")):
        fail(key, ip)
        err(401, "Nama/email atau PIN salah.")
    clear_fails(key)
    if m.get("status", "approved") == "pending":
        err(403, "Akun Anda masih menunggu approval Marketing Manager.")
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
    members = []
    if user.get("isAdmin"):
        members = [{**{k: v for k, v in clean(m).items() if k != "pinHash"}, "status": m.get("status", "approved")}
                   for m in db.members.find({"hidden": {"$ne": True}, "status": {"$ne": "rejected"}})]
    return {"user": user, "roles": ROLES, "slots": slot_status(), "emailDomain": EMAIL_DOMAIN, "settings": public_settings(s),
            "products": [enrich_product(p, s) for p in products_map().values()],
            "profiles": list(profiles_map().values()), "promos": promos, "members": members,
            "mechanisms": E.MECHANISMS, "objectives": E.OBJECTIVES, "empty": db.products.count_documents({}) == 0}


# ---------------------------------------------------------------------------
# calculations
# ---------------------------------------------------------------------------

@app.post("/api/calc")
def api_calc(body: dict, user=Depends(current_user)):
    promo = body.get("promo") or body
    return {"results": compute(promo, body.get("areas"))}


@app.post("/api/calc/compare-platforms")
def api_compare(body: dict, user=Depends(current_user)):
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
def api_settlement(body: dict, user=Depends(current_user)):
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
def api_recommend(body: dict, user=Depends(current_user)):
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
def price_versions(user=Depends(current_user)):
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
    return clean(new)


@app.post("/api/platform-profiles/{pid}/duplicate")
def dup_profile(pid: str, user=Depends(require("finance", "head"))):
    p = clean(db.profiles.find_one({"id": pid}))
    if not p:
        err(404, "Profil tidak ditemukan.")
    p.update({"id": f"{pid}-{secrets.token_hex(2)}", "label": p["label"] + " (salinan)", "version": 1, "verified": False})
    db.profiles.insert_one(p)
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
    db.settings.update_one({"_id": "main"}, {"$set": upd})
    return public_settings(get_settings())


@app.put("/api/baselines")
def put_baselines(body: dict, user=Depends(require("head", "finance"))):
    s = get_settings()
    b = s.get("baselines") or {}
    pid, area = body.get("platformId"), body.get("area")
    b.setdefault(pid, {})[area] = body.get("baseline") or {}
    db.settings.update_one({"_id": "main"}, {"$set": {"baselines": b}})
    return b


@app.put("/api/members/{mid}")
def put_member(mid: str, body: dict, user=Depends(require("head"))):
    upd = {k: body[k] for k in ("role", "active", "platforms", "email", "phone") if k in body}
    db.members.update_one({"id": mid}, {"$set": upd})
    return {"ok": True}


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
    db.invites.update_one({"token": token}, {"$set": {"revoked": True}})
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
    return {"ok": True}


@app.post("/api/members/{mid}/reset-pin")
def reset_pin(mid: str, body: dict, user=Depends(require("head"))):
    pin = str(body.get("pin") or "")
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        err(400, "PIN baru harus 4–6 angka.")
    db.members.update_one({"id": mid}, {"$set": {"pinHash": hash_pin(pin)}})
    clear_fails(f"m:{mid}")
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
    profs = profiles_map()
    out = []
    for p in db.promos.find({"status": "done"}):
        a = p.get("actual") or {}
        if a.get("achievement") is None:
            continue
        try:
            ds, de = date.fromisoformat(p["periodStart"]), date.fromisoformat(p["periodEnd"])
        except Exception:
            continue
        pay = any((ds + timedelta(days=i)).day >= 25 or (ds + timedelta(days=i)).day <= 3 for i in range((de - ds).days + 1))
        out.append({"channelType": profs.get(p.get("platformProfileId"), {}).get("channelType"), "achievement": a["achievement"],
                    "hasPayday": pay})
    return out


def duration_history(mechanism: str):
    out = []
    for p in db.promos.find({"status": "done", "mechanism": mechanism}):
        a = (p.get("actual") or {}).get("achievement")
        try:
            n = (date.fromisoformat(p["periodEnd"]) - date.fromisoformat(p["periodStart"])).days + 1
        except Exception:
            continue
        out.append((n, a))
    return out


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


def run_timing(ctx: dict):
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
    chips = ([] if ctx.get("durationAuto") or adv["status"] == "pas" else
             [{"label": f"Pakai saran {adv['rec']} hari", "set": {"duration": adv["rec"]}}]) + [
             {"label": "7 hari", "set": {"duration": 7}}, {"label": "14 hari", "set": {"duration": 14}},
             {"label": "30 hari", "set": {"duration": 30}}, {"label": "Bulan depan", "message": "bulan depan"},
             {"label": "Ganti objective", "set": {"objective": None}}, {"label": "Ganti channel", "set": {"platformProfileId": None}}]
    return {"context": ctx, "reply": "\n\n".join(lines), "result": res, "chips": chips}


@app.post("/api/moments")
def add_moment(body: dict, user=Depends(require("head", "planner", "finance"))):
    try:
        date.fromisoformat(body.get("date") or "")
        if body.get("end"):
            date.fromisoformat(body["end"])
    except ValueError:
        err(400, "Isi tanggal momen dengan benar.")
    if not (body.get("label") or "").strip():
        err(400, "Isi nama momen.")
    mo = {"id": secrets.token_hex(4), "date": body["date"], "end": body.get("end") or None, "label": body["label"].strip()[:60],
          "type": body.get("type") or "momen", "by": user["name"]}
    db.settings.update_one({"_id": "main"}, {"$push": {"moments": mo}})
    return mo


@app.delete("/api/moments/{mid}")
def del_moment(mid: str, user=Depends(require("head", "planner", "finance"))):
    db.settings.update_one({"_id": "main"}, {"$pull": {"moments": {"id": mid}}})
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
