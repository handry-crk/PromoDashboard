from fastapi.testclient import TestClient
from app.main import app, db

c = TestClient(app)


def H(t):
    return {"Authorization": f"Bearer {t}"}


def test_flow():
    for col in db.list_collection_names():
        db[col].drop()
    r = c.post("/api/auth/register", json={"name": "Handry", "role": "viewer", "pin": "1234"})
    assert r.status_code == 200 and r.json()["user"]["isAdmin"] and r.json()["user"]["role"] == "head"
    ha = r.json()["token"]
    fi = c.post("/api/auth/register", json={"name": "Fina", "role": "finance", "pin": "2222"}).json()["token"]
    pl = c.post("/api/auth/register", json={"name": "Sinta", "role": "planner", "pin": "3333"}).json()["token"]
    assert c.post("/api/seed/crk", headers=H(ha)).status_code == 200
    st = c.get("/api/state", headers=H(ha)).json()
    assert len(st["products"]) == 39 and len(st["promos"]) == 3
    # planner cannot edit product
    assert c.put("/api/products/mozza-b", json={"hpp": 10500}, headers=H(pl)).status_code == 403
    # HOLD submit blocked
    p = c.post("/api/promos", headers=H(pl), json={"nama": "B1G1 Bojot", "mechanism": "bxgy", "objective": "trial",
               "platformProfileId": "offline_kios", "areas": ["bandung"],
               "items": [{"productId": "bojot-k"}, {"productId": "bojot-k", "role": "free"}]}).json()
    assert p["kode"].startswith("PR-")
    r = c.post(f"/api/promos/{p['id']}/submit", headers=H(pl))
    assert r.status_code == 400 and "HOLD" in r.json()["detail"]
    # healthy promo full flow
    p = c.post("/api/promos", headers=H(pl), json={"nama": "Diskon Frozen", "mechanism": "diskon_persen", "objective": "trial",
               "platformProfileId": "offline_kios", "areas": ["bandung"], "periodStart": "2026-11-01", "periodEnd": "2026-11-10",
               "items": [{"productId": "fz-ayam-bbq"}], "params": {"discountPct": 15}}).json()
    assert c.post(f"/api/promos/{p['id']}/submit", headers=H(pl)).status_code == 200
    assert c.post(f"/api/promos/{p['id']}/approve", headers=H(pl), json={"decision": "approve"}).status_code == 403
    assert c.post(f"/api/promos/{p['id']}/review", headers=H(fi), json={"decision": "approve"}).json()["status"] == "review_head"
    v = c.post(f"/api/promos/{p['id']}/approve", headers=H(ha), json={"decision": "approve"}).json()
    assert v["effectiveStatus"] == "running" and v["waitingActual"]
    v = c.post(f"/api/promos/{p['id']}/actual", headers=H(pl), json={"units": 900, "takeRate": 12, "incRevenue": 5000000, "finish": True}).json()
    assert v["status"] == "done" and v["actual"]["achievement"]
    # compare & recommend
    r = c.post("/api/calc/compare-platforms", headers=H(pl), json={"area": "jakarta", "promo": {"mechanism": "diskon_persen",
               "items": [{"productId": "mix-mozza-ayam"}], "params": {"discountPct": 20},
               "overrides": {"avgUnitsPerOrder": 1, "extraPackagingPerOrder": 0}}}).json()
    cms = {x["platformId"]: x["cm"] for x in r["rows"]}
    assert cms["offline_kios"] == 7891 and cms["gofood"] == 3371 and cms["grabfood"] == 4371
    assert [x for x in r["rows"] if x["bestMargin"]][0]["platformId"] in ("offline_kios", "offline_gerobak", "event")
    r = c.post("/api/recommend", headers=H(pl), json={"platformProfileId": "gofood", "objective": "online", "area": "jakarta",
               "maxDiscountPct": 25, "allowCofunding": True, "maxPlatformPct": 50}).json()
    assert len(r["results"]) == 5
    # profile edit permission & version
    assert c.put("/api/platform-profiles/gofood", headers=H(pl), json={"ppnPct": 11}).status_code == 403
    pr = c.put("/api/platform-profiles/gofood", headers=H(fi), json={"ppnPct": 11}).json()
    assert pr["version"] == 2 and pr["verified"] is False
    assert c.post("/api/platform-profiles/gofood/verify", headers=H(fi), json={}).json()["verified"]
    # report
    tok = c.get("/api/state", headers=H(ha)).json()["settings"]["shareToken"]
    rep = c.get(f"/api/report?t={tok}").json()
    assert rep["promos"] and "hpp" not in str(rep).lower() and "cm" not in rep["promos"][0]["areas"].get("bandung", {})
    assert c.get("/api/report?t=salah").status_code == 404
    # PIN lock
    mid = [m for m in c.get("/api/public/members").json()["members"] if m["name"] == "Sinta"][0]["id"]
    for _ in range(5):
        c.post("/api/auth/login", json={"memberId": mid, "pin": "0000"})
    assert c.post("/api/auth/login", json={"memberId": mid, "pin": "3333"}).status_code == 429
    assert c.get("/api/health").json()["ok"]
