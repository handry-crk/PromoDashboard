"""CRK Promo Calculator — FastAPI backend."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import logging
import os
import secrets
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import engine as E
from . import seed as S

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

ROLES = {
    "head": "Marketing Head",
    "planner": "Promo Planner / Marketing",
    "finance": "Finance",
    "channel_pic": "Channel PIC (Delivery / Marketplace)",
    "viewer": "Viewer",
}

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


FAILS: dict[str, list[float]] = {}


def guard_lock(key: str):
    arr = [t for t in FAILS.get(key, []) if time.time() - t < 900]
    FAILS[key] = arr
    if len(arr) >= 5:
        err(429, "PIN salah 5 kali. Coba lagi dalam 15 menit atau minta Admin reset PIN.")


def fail(key: str):
    FAILS.setdefault(key, []).append(time.time())


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
    m = db.members.find_one({"id": s["memberId"]})
    if not m or not m.get("active", True):
        err(401, "Akun tidak aktif. Hubungi Admin.")
    return clean(m)


def require(*roles):
    def dep(user=Depends(current_user)):
        if user.get("isAdmin") or user["role"] in roles:
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


def compute(promo, areas=None):
    s = get_settings()
    P = products_map()
    prof = profiles_map().get(promo.get("platformProfileId"))
    if not prof:
        err(400, "Pilih platform/channel promo dulu.")
    areas = areas or promo.get("areas") or ["bandung"]
    hist = history_list()
    out = {}
    for a in areas:
        try:
            out[a] = E.run(promo, P, prof, a, s, baseline_for(s, prof["id"], a), hist)
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


@app.get("/api/public/members")
def public_members():
    ms = [{"id": m["id"], "name": m["name"], "role": m["role"]} for m in db.members.find({"active": {"$ne": False}})]
    return {"members": sorted(ms, key=lambda x: x["name"]), "roles": ROLES, "hasAny": db.members.count_documents({}) > 0}


@app.post("/api/auth/register")
def register(body: dict):
    name = (body.get("name") or "").strip()
    pin = str(body.get("pin") or "")
    role = body.get("role") or "viewer"
    if not name:
        err(400, "Isi nama lengkap.")
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        err(400, "PIN harus 4–6 angka.")
    if role not in ROLES:
        err(400, "Pilih role yang tersedia.")
    if db.members.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}):
        err(400, "Nama sudah terdaftar. Pilih nama Anda di halaman login.")
    first = db.members.count_documents({}) == 0
    m = {"id": secrets.token_hex(6), "name": name, "role": "head" if first else role, "email": body.get("email", ""),
         "phone": body.get("phone", ""), "pinHash": hash_pin(pin), "active": True, "isAdmin": first,
         "platforms": body.get("platforms") or [], "createdAt": now_iso()}
    db.members.insert_one(m)
    get_settings()
    return {"token": make_session(m), "user": {k: v for k, v in clean(m).items() if k != "pinHash"}}


@app.post("/api/auth/login")
def login(body: dict):
    mid = body.get("memberId")
    key = f"m:{mid}"
    guard_lock(key)
    m = db.members.find_one({"id": mid})
    if not m or not m.get("active", True):
        err(404, "Nama tidak ditemukan.")
    if not check_pin(str(body.get("pin") or ""), m["pinHash"]):
        fail(key)
        left = 5 - len(FAILS.get(key, []))
        err(401, f"PIN salah. Sisa {max(left,0)} percobaan." if left > 0 else "PIN salah 5 kali. Coba lagi dalam 15 menit.")
    FAILS.pop(key, None)
    return {"token": make_session(m), "user": {k: v for k, v in clean(m).items() if k != "pinHash"}}


@app.post("/api/auth/admin-login")
def admin_login(body: dict):
    guard_lock("admin")
    s = get_settings()
    if not check_pin(str(body.get("pin") or ""), s["adminPinHash"]):
        fail("admin")
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
        members = [{k: v for k, v in clean(m).items() if k != "pinHash"} for m in db.members.find({"hidden": {"$ne": True}})]
    return {"user": user, "roles": ROLES, "settings": public_settings(s),
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
    res = E.recommend(body, products_map(), prof, s, baseline_for(s, prof["id"], area), history_list())
    for x in res:
        x["promo"]["platformProfileId"] = prof["id"]
        x["promo"]["areas"] = [area]
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
    if mech_changed and p["status"] in ("approved", "review_head", "review_finance", "running"):
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


@app.post("/api/promos/{pid}/actual")
def actual_promo(pid: str, body: dict, user=Depends(require("planner", "channel_pic", "head", "finance"))):
    p = db.promos.find_one({"id": pid})
    if not p:
        err(404, "Promo tidak ditemukan.")
    st, _ = effective_status(p)
    if st not in ("running", "done", "approved"):
        err(400, "Hasil aktual hanya untuk promo yang sudah berjalan.")
    sm = next(iter((p.get("summary") or {}).values()), {})
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
    if not (user.get("isAdmin") or user["role"] in ("finance", "head")):
        if user["role"] == "channel_pic" and set(body.keys()) <= {"platformPrices"}:
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
    if user.get("isAdmin") or user["role"] in ("finance", "head"):
        return True
    return user["role"] == "channel_pic" and prof["id"] in (user.get("platforms") or [])


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


@app.post("/api/members/{mid}/reset-pin")
def reset_pin(mid: str, body: dict, user=Depends(require("head"))):
    pin = str(body.get("pin") or "")
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        err(400, "PIN baru harus 4–6 angka.")
    db.members.update_one({"id": mid}, {"$set": {"pinHash": hash_pin(pin)}})
    FAILS.pop(f"m:{mid}", None)
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
    if not (user.get("isAdmin") or user["role"] in ("head", "finance")):
        err(403, "Export hanya untuk Admin/Finance.")
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
