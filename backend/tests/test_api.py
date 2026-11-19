from fastapi.testclient import TestClient
from app.main import app, db

c = TestClient(app)


def H(t):
    return {"Authorization": f"Bearer {t}"}


def invite(ha, role):
    return c.post("/api/invites", headers=H(ha), json={"role": role}).json()["token"]


def test_flow():
    for col in db.list_collection_names():
        db[col].drop()
    assert c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "h@gmail.com"}).status_code == 400
    r = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"})
    assert r.status_code == 200 and r.json()["user"]["isAdmin"] and r.json()["user"]["role"] == "head"
    ha = r.json()["token"]
    # without invite nobody can register
    assert c.post("/api/auth/register", json={"name": "X", "role": "team_leader", "pin": "1111", "email": "x@citarasakuliner.com"}).status_code == 403
    assert c.post("/api/auth/register", json={"name": "X", "pin": "1111", "email": "x@citarasakuliner.com", "invite": "palsu"}).status_code == 403
    inv_rg, inv_tl = invite(ha, "revenue_growth"), invite(ha, "team_leader")
    assert c.post("/api/invites", headers=H(ha), json={"role": "team_leader"}).status_code == 400  # already an active invite
    assert c.get(f"/api/public/invite/{inv_tl}").json()["label"] == "Marketing Team Leader"
    r = c.post("/api/auth/register", json={"name": "Fina", "pin": "2222", "email": "fina@citarasakuliner.com", "invite": inv_rg}).json()
    assert r["pending"]
    r = c.post("/api/auth/register", json={"name": "Sinta", "pin": "3333", "email": "sinta@citarasakuliner.com", "invite": inv_tl}).json()
    assert r["pending"]
    # invite is single use
    assert c.post("/api/auth/register", json={"name": "Budi", "pin": "4444", "email": "budi@citarasakuliner.com", "invite": inv_tl}).status_code == 403
    pub = c.get("/api/public/members").json()
    assert "members" not in pub and pub["hasAny"]
    ids = {m["name"]: m["id"] for m in c.get("/api/state", headers=H(ha)).json()["members"]}
    assert c.post("/api/auth/login", json={"identifier": "Sinta", "pin": "3333"}).status_code == 403
    assert c.post("/api/auth/login", json={"identifier": "orang-luar", "pin": "3333"}).status_code == 401
    for n in ("Fina", "Sinta"):
        assert c.post(f"/api/members/{ids[n]}/approve", headers=H(ha), json={"decision": "approve"}).status_code == 200
    fi = c.post("/api/auth/login", json={"identifier": "fina@citarasakuliner.com", "pin": "2222"}).json()["token"]
    pl = c.post("/api/auth/login", json={"identifier": "sinta", "pin": "3333"}).json()["token"]
    assert c.post("/api/auth/admin-login", json={"pin": "1234"}).status_code == 404
    assert c.get("/api/state", headers=H(pl)).json()["user"]["perm"] == "planner"
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
    for _ in range(5):
        c.post("/api/auth/login", json={"identifier": "Sinta", "pin": "0000"})
    assert c.post("/api/auth/login", json={"identifier": "Sinta", "pin": "3333"}).status_code == 429
    mid = ids["Sinta"]
    assert c.post(f"/api/members/{mid}/reset-pin", headers=H(ha), json={"pin": "5555"}).status_code == 200
    assert c.post("/api/auth/login", json={"identifier": "Sinta", "pin": "5555"}).status_code == 200
    assert c.get("/api/health").json()["ok"]


def test_status_rules_and_multi_area():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "h@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    tok = c.post("/api/invites", headers=H(ha), json={"role": "team_leader"}).json()["token"]
    assert c.post("/api/auth/register", json={"name": ".*", "pin": "1234", "email": "a@citarasakuliner.com", "invite": tok}).status_code == 200
    P = {p["nama"]: p for p in c.get("/api/state", headers=H(ha)).json()["promos"]}
    assert c.post(f"/api/promos/{P['Braga Pairing']['id']}/submit", headers=H(ha)).status_code == 400
    r = c.put(f"/api/promos/{P['Paket AA 30 Ribu']['id']}", headers=H(ha), json={"params": {"packagePrice": 36000}}).json()
    assert r["status"] == "draft"
    md = c.get(f"/api/promos/{P['Mozza Duo']['id']}", headers=H(ha)).json()
    days = {a: o["scenarios"]["meta"]["outletDays"] for a, o in md["results"].items()}
    fixed = sum(o["scenarios"]["target"]["fixedCosts"] for o in md["results"].values())
    assert 22000 < sum(days.values()) < 22400 and fixed == 74700000
    assert md["targets"]["targetUnits"] == sum(o["scenarios"]["target"]["totalUnits"] for o in md["results"].values())
    assert c.post("/api/calc", headers=H(ha), json={"promo": {"mechanism": "diskon_persen", "platformProfileId": "offline_kios",
                  "items": [{"productId": "ayam-b"}], "params": {"discountPct": "x"}}}).status_code == 400


def test_calendar_conflicts_and_moments():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "h@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    base = {"mechanism": "diskon_persen", "objective": "trial", "areas": ["bandung"], "params": {"discountPct": 10}}
    c.post("/api/promos", headers=H(ha), json={**base, "nama": "A", "platformProfileId": "offline_gerobak", "periodStart": "2026-12-01",
                                               "periodEnd": "2026-12-15", "items": [{"productId": "mozza-b"}]})
    c.post("/api/promos", headers=H(ha), json={**base, "nama": "B", "platformProfileId": "gofood", "periodStart": "2026-12-10",
                                               "periodEnd": "2026-12-20", "items": [{"productId": "mozza-b"}]})
    r = c.get("/api/calendar?start=2026-11-30&end=2027-01-10", headers=H(ha)).json()
    types = {x["type"] for x in r["conflicts"]}
    assert "bentrok" in types  # A vs Mozza Duo (same product, same gerobak, same area)
    labels = {m["label"] for m in r["moments"]}
    assert {"Harbolnas 12.12", "Natal", "Gajian", "Tanggal kembar 1.1"} <= labels
    mo = c.post("/api/moments", headers=H(ha), json={"date": "2026-12-20", "label": "Anniversary CBAA"}).json()
    r = c.get("/api/calendar?start=2026-12-01&end=2026-12-31", headers=H(ha)).json()
    assert any(m.get("custom") and m["label"] == "Anniversary CBAA" for m in r["moments"])
    c.delete(f"/api/moments/{mo['id']}", headers=H(ha))
    assert c.get("/api/calendar?start=2026-12-01&end=2028-12-31", headers=H(ha)).status_code == 400


def test_audit2_guards():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "h@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    me = c.get("/api/state", headers=H(ha)).json()["user"]["id"]
    # admin cannot lock himself out
    assert c.put(f"/api/members/{me}", headers=H(ha), json={"active": False}).status_code == 400
    assert c.put(f"/api/members/{me}", headers=H(ha), json={"role": "viewer"}).status_code == 400
    assert c.get("/api/state", headers=H(ha)).status_code == 200
    # bot never 500s on bad context
    for ctx in ({"platformProfileId": "gofood", "objective": "aov", "to": "garbage"},
                {"platformProfileId": "gofood", "objective": "aov", "duration": "abc"},
                {"platformProfileId": "gofood", "objective": "zzz"}, {"platformProfileId": "nope"}):
        assert c.post("/api/bot", headers=H(ha), json={"context": ctx}).status_code == 200
    # event counted once even with two areas
    st = c.get("/api/state", headers=H(ha)).json()
    bz = next(p for p in st["profiles"] if p["id"] == "event_bazaar")
    pr = {"mechanism": "bundle", "objective": "awareness", "platformProfileId": "event_bazaar", "params": {"packagePrice": 30000},
          "items": [{"productId": "mozza-b"}, {"productId": "ayam-k"}], "fixedCosts": bz["eventFixedTemplate"], "areas": ["bandung", "jakarta"]}
    res = c.post("/api/calc", headers=H(ha), json={"promo": pr}).json()["results"]
    assert list(res) == ["bandung"] and res["bandung"]["scenarios"]["target"]["fixedCosts"] == 7050000
    # end before start rejected
    bad = {"mechanism": "diskon_persen", "platformProfileId": "offline_kios", "items": [{"productId": "ayam-b"}], "params": {"discountPct": 10},
           "periodStart": "2026-12-10", "periodEnd": "2026-12-01"}
    assert c.post("/api/calc", headers=H(ha), json={"promo": bad}).status_code == 400
    assert c.post("/api/moments", headers=H(ha), json={"date": "2026-12-10", "end": "2026-12-01", "label": "X"}).status_code == 400
    # viewer does not get the report token
    tok = c.post("/api/invites", headers=H(ha), json={"role": "viewer"}).json()["token"]
    c.post("/api/auth/register", json={"name": "Vi", "pin": "1234", "email": "vi@citarasakuliner.com", "invite": tok})
    vid = next(m["id"] for m in c.get("/api/state", headers=H(ha)).json()["members"] if m["name"] == "Vi")
    c.post(f"/api/members/{vid}/approve", headers=H(ha), json={"decision": "approve"})
    tv = c.post("/api/auth/login", json={"identifier": "Vi", "pin": "1234"}).json()["token"]
    assert "shareToken" not in c.get("/api/state", headers=H(tv)).json()["settings"]


def test_viewer_never_gets_hpp():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "h@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    tok = c.post("/api/invites", headers=H(ha), json={"role": "viewer"}).json()["token"]
    c.post("/api/auth/register", json={"name": "Vi", "pin": "1234", "email": "vi@citarasakuliner.com", "invite": tok})
    vid = next(m["id"] for m in c.get("/api/state", headers=H(ha)).json()["members"] if m["name"] == "Vi")
    c.post(f"/api/members/{vid}/approve", headers=H(ha), json={"decision": "approve"})
    tv = c.post("/api/auth/login", json={"identifier": "Vi", "pin": "1234"}).json()["token"]
    import json as _j
    banned = ('"hpp"', '"cm"', '"cmPct"', '"gmPct"', '"grossProfit"', '"normalCM"', '"merchantNet"', '"targetContribution"',
              '"targetIncCM"', '"contribution"', '"hppBreakdown"', '"feeLines"')
    for path in ("/api/state", "/api/promos/PR-2611-01", "/api/calendar?start=2026-11-01&end=2026-12-31"):
        r = c.get(path, headers=H(tv))
        assert r.status_code == 200
        txt = _j.dumps(r.json())
        for b in banned:
            assert b not in txt, (path, b)
        assert "15084" not in txt and "11916" not in txt  # HPP & CM Mozza Duo
    promo = {"mechanism": "diskon_persen", "platformProfileId": "offline_kios", "items": [{"productId": "ayam-b"}], "params": {"discountPct": 10}}
    assert c.post("/api/calc", headers=H(tv), json={"promo": promo}).status_code == 403
    assert c.post("/api/calc/compare-platforms", headers=H(tv), json={"promo": promo}).status_code == 403
    assert c.post("/api/recommend", headers=H(tv), json={"platformProfileId": "offline_kios"}).status_code == 403
    assert c.post("/api/calc/settlement", headers=H(tv), json={"profileId": "gofood"}).status_code == 403
    assert c.get("/api/price-versions", headers=H(tv)).status_code == 403
    assert c.get("/api/export/products.csv", headers=H(tv)).status_code == 403
    r = c.post("/api/promos/PR-2611-01/comments", headers=H(tv), json={"text": "ok"})
    assert r.status_code == 200 and '"hpp"' not in _j.dumps(r.json())
    # manager still sees everything
    assert '"hpp"' in _j.dumps(c.get("/api/promos/PR-2611-01", headers=H(ha)).json())


def test_learning_data_feeds_bot():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "h@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    base = {"platformProfileId": "gofood", "mechanism": "diskon_persen", "objective": "online", "areas": ["jakarta"]}
    assert c.post("/api/learnings", headers=H(ha), json={**base, "nama": "X", "periodStart": "2026-08-01", "periodEnd": "2026-08-07"}).status_code == 400  # no result
    assert c.post("/api/learnings", headers=H(ha), json={**base, "nama": "X", "periodStart": "2027-08-01", "periodEnd": "2027-08-07", "rating": 4}).status_code == 400  # future
    before = c.post("/api/bot", headers=H(ha), json={"context": {"platformProfileId": "gofood", "objective": "online", "mechanism": "diskon_persen"}}).json()
    assert "asumsi awal" in before["reply"] and not before["result"]["learning"]["active"]
    rows = [("Gajian Agu", "2026-08-25", "2026-08-31", 5, 18), ("Gajian Sep", "2026-09-25", "2026-10-01", 4, 15),
            ("Tengah Agu", "2026-08-10", "2026-08-16", 2, 6), ("Tengah Sep", "2026-09-10", "2026-09-16", 2, 5)]
    for nama, a, b, rating, tr in rows:
        r = c.post("/api/learnings", headers=H(ha), json={**base, "nama": nama, "periodStart": a, "periodEnd": b, "rating": rating, "takeRate": tr})
        assert r.status_code == 200
    data = c.get("/api/learnings", headers=H(ha)).json()
    assert data["insights"]["total"] == 4 and data["insights"]["byChannel"]["online_food"]["active"]
    assert any("gajian" in n for n in data["insights"]["byChannel"]["online_food"]["notes"])
    after = c.post("/api/bot", headers=H(ha), json={"context": {"platformProfileId": "gofood", "objective": "online", "mechanism": "diskon_persen"}}).json()
    assert after["result"]["learning"]["active"] and "Belajar dari 4 hasil" in after["reply"] and "Promo serupa sebelumnya" in after["reply"]
    assert "asumsi awal" not in after["reply"]
    best = after["result"]["recommendations"][0]
    assert any("gajian" in x.lower() for x in best["reasons"])
    # CSV import with ; delimiter and label names
    csv_text = ("nama;platform;jenis_promo;tujuan;area;mulai;selesai;hasil_1_5;take_rate_pct;kenaikan_revenue_pct;pencapaian_target_pct;diskon_pct;catatan\n"
                "Bundle Juli;gerobak;Bundle / paket;aov;bandung;2026-07-01;2026-07-21;;9;;110;10;ok\n"
                "Rusak;;bundle;aov;bandung;2026-07-01;2026-07-21;3;;;;;\n")
    r = c.post("/api/learnings/import", headers=H(ha), content=csv_text).json()
    assert r["imported"] == 1 and len(r["errors"]) == 1
    rec = next(x for x in c.get("/api/learnings", headers=H(ha)).json()["records"] if x["nama"] == "Bundle Juli")
    assert rec["platformProfileId"] == "offline_gerobak" and rec["mechanism"] == "bundle" and abs(rec["perf"] - 1.1) < 1e-9 and rec["days"] == 21
    assert c.delete(f"/api/learnings/{rec['id']}", headers=H(ha)).status_code == 200
    assert c.get("/api/backup", headers=H(ha)).status_code == 200 and "pinHash" not in c.get("/api/backup", headers=H(ha)).text


def test_audit_and_direct_member():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    # direct add → activation link
    assert c.post("/api/members", headers=H(ha), json={"name": "Luar", "email": "luar@gmail.com", "role": "viewer"}).status_code == 400
    r = c.post("/api/members", headers=H(ha), json={"name": "Galuh Yusnindar", "email": "galuh.yusnindar@citarasakuliner.com", "role": "revenue_growth"})
    assert r.status_code == 200
    tok = r.json()["setupToken"]
    assert c.post("/api/members", headers=H(ha), json={"name": "Lain", "email": "lain@citarasakuliner.com", "role": "revenue_growth"}).status_code == 400  # slot terisi
    assert c.post("/api/auth/login", json={"identifier": "galuh.yusnindar@citarasakuliner.com", "pin": "1234"}).status_code == 403
    assert c.get("/api/public/setup/salah").status_code == 404
    assert c.get(f"/api/public/setup/{tok}").json()["label"] == "Revenue Growth Specialist"
    assert c.post("/api/auth/setup", json={"token": tok, "pin": "12"}).status_code == 400
    r = c.post("/api/auth/setup", json={"token": tok, "pin": "5678"})
    assert r.status_code == 200 and "pinHash" not in r.json()["user"] and "setupToken" not in r.json()["user"]
    tg = r.json()["token"]
    assert c.post("/api/auth/setup", json={"token": tok, "pin": "5678"}).status_code == 404  # sekali pakai
    assert c.post("/api/auth/login", json={"identifier": "galuh.yusnindar@citarasakuliner.com", "pin": "5678"}).status_code == 200
    # edits are recorded with who + when
    st = c.get("/api/state", headers=H(tg)).json()
    p = st["products"][0]
    assert c.put(f"/api/products/{p['id']}", headers=H(tg), json={"hpp": p["hpp"] + 100}).status_code == 200
    assert c.post("/api/products/import", headers={**H(tg), "X-Filename": "hpp-nov.csv"}, content="nama,hpp,bandung,jakarta\nTes Audit,5000,12000,13000\n").status_code == 200
    a = c.get("/api/audit", headers=H(tg)).json()
    acts = [(x["action"], x["byName"]) for x in a["rows"]]
    assert ("Mengubah produk", "Galuh Yusnindar") in acts and ("Mengaktifkan akun", "Galuh Yusnindar") in acts
    assert ("Menambah anggota", "Handry") in acts
    f = [x for x in a["rows"] if x["category"] == "file" and x.get("file") == "hpp-nov.csv"]
    assert f and f[0]["at"]
    e = next(x for x in a["rows"] if x["action"] == "Mengubah produk")
    assert "HPP" in e["detail"] and "→" in e["detail"]
    assert all(x["category"] == "produk" for x in c.get("/api/audit?category=produk", headers=H(tg)).json()["rows"])
    # viewer cannot read the log
    r = c.post("/api/members", headers=H(ha), json={"name": "Vina", "email": "vina@citarasakuliner.com", "role": "viewer"}).json()
    tv = c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": "9999"}).json()["token"]
    assert c.get("/api/audit", headers=H(tv)).status_code == 403


def test_preset_members_seed():
    from app.main import seed_preset_members
    for col in db.list_collection_names():
        db[col].drop()
    seed_preset_members()
    assert db.members.count_documents({}) == 0  # belum ada admin → tidak jalan
    c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"})
    seed_preset_members(); seed_preset_members()
    m = {x["email"]: x for x in db.members.find({"status": "invited"})}
    assert m["galuh.yusnindar@citarasakuliner.com"]["role"] == "revenue_growth"
    assert m["kintan.asokawati@citarasakuliner.com"]["role"] == "team_leader"
    assert len(m) == 2


def test_state_hides_own_pin_hash():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    st = c.get("/api/state", headers=H(ha)).json()
    assert "pinHash" not in st["user"] and all("pinHash" not in m for m in st["members"])


def test_run_now_from_recommendation():
    from datetime import date, timedelta
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    r = c.post("/api/members", headers=H(ha), json={"name": "Kintan", "email": "kintan@citarasakuliner.com", "role": "team_leader"}).json()
    tk = c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": "5678"}).json()["token"]
    rec = c.post("/api/recommend", headers=H(ha), json={"platformProfileId": "offline_kios", "objective": "aov", "area": "bandung"}).json()["results"]
    x = rec[0]["promo"]
    today = date.today().isoformat()
    n0 = db.promos.count_documents({})
    pre = c.post("/api/promos/run-now", headers=H(ha), json={"promo": x, "days": 10, "dryRun": True}).json()
    assert pre["resultStatus"] == "running" and pre["periodStart"] == today and db.promos.count_documents({}) == n0
    out = c.post("/api/promos/run-now", headers=H(ha), json={"promo": x, "days": 10}).json()
    assert out["promo"]["effectiveStatus"] == "running" and out["promo"]["status"] == "approved"
    assert out["promo"]["periodEnd"] == (date.today() + timedelta(days=9)).isoformat()
    assert any(t["action"] == "run_direct" for t in out["promo"]["timeline"])
    assert any(a["action"].startswith("Menjalankan promo langsung") and a["byName"] == "Handry" for a in c.get("/api/audit", headers=H(ha)).json()["rows"])
    # same promo again → bentrok warning
    pre = c.post("/api/promos/run-now", headers=H(ha), json={"promo": x, "days": 5, "dryRun": True}).json()
    assert any("Bentrok" in w for w in pre["warnings"])
    # future start → approved (scheduled)
    fut = (date.today() + timedelta(days=40)).isoformat()
    out = c.post("/api/promos/run-now", headers=H(ha), json={"promo": rec[1]["promo"], "startDate": fut, "days": 7}).json()
    assert out["promo"]["effectiveStatus"] == "approved"
    # team leader cannot skip review
    out = c.post("/api/promos/run-now", headers=H(tk), json={"promo": rec[2]["promo"], "startDate": fut, "days": 7}).json()
    assert out["resultStatus"] == "review_finance" and out["promo"]["status"] == "review_finance"
    # guards
    assert c.post("/api/promos/run-now", headers=H(ha), json={"promo": x, "startDate": "2020-01-01"}).status_code == 400
    assert c.post("/api/promos/run-now", headers=H(ha), json={"promo": x, "days": 500}).status_code == 400
    assert c.post("/api/promos/run-now", headers=H(ha), json={"promo": {}}).status_code == 400


def test_primary_and_supporting_objective():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    base = {"nama": "Tes Obj", "mechanism": "bundle", "platformProfileId": "offline_kios", "areas": ["bandung"], "objective": "repeat",
            "periodStart": "2026-12-01", "periodEnd": "2026-12-14", "items": [{"productId": "mix-mozza-ayam", "qty": 2}], "params": {"discountPct": 10}}
    fit = lambda p: next(x for x in p["results"]["bandung"]["menarik"]["components"] if x["key"] == "fit")
    p1 = c.post("/api/promos", headers=H(ha), json=base).json()
    p2 = c.post("/api/promos", headers=H(ha), json={**base, "objective2": "aov"}).json()
    assert fit(p1)["score"] == 60                       # bundle: "bisa" untuk repeat
    assert fit(p2)["score"] == round(0.7 * 60 + 0.3 * 100) and "pendukung" in fit(p2)["note"]
    assert p2["objective2"] == "aov" and p1.get("objective2") is None
    # same as primary or unknown → ignored
    assert c.post("/api/promos", headers=H(ha), json={**base, "objective2": "repeat"}).json().get("objective2") is None
    assert c.post("/api/promos", headers=H(ha), json={**base, "objective2": "ngawur"}).json().get("objective2") is None
    # recommend carries it and widens mechanisms with the supporting objective's best-fit ones
    r1 = c.post("/api/recommend", headers=H(ha), json={"platformProfileId": "offline_kios", "objective": "repeat", "area": "bandung"}).json()["results"]
    r2 = c.post("/api/recommend", headers=H(ha), json={"platformProfileId": "offline_kios", "objective": "repeat", "objective2": "aov", "area": "bandung"}).json()["results"]
    assert r2 and all(x["promo"]["objective2"] == "aov" and x["result"]["menarik"]["fit2"] for x in r2)
    assert all(not x["promo"].get("objective2") for x in r1)
    # bot reads two objectives from one sentence
    b = c.post("/api/bot", headers=H(ha), json={"message": "kapan promo gofood untuk trial dan naikkan aov"}).json()
    assert b["context"]["objective"] and b["context"].get("objective2") and b["context"]["objective"] != b["context"]["objective2"]
    # learning data keeps it
    l = c.post("/api/learnings", headers=H(ha), json={"nama": "Lama", "platformProfileId": "gofood", "mechanism": "bundle", "objective": "aov",
               "objective2": "trial", "areas": ["jakarta"], "periodStart": "2026-08-01", "periodEnd": "2026-08-14", "rating": 4})
    assert l.status_code == 200 and l.json()["objective2"] == "trial"


def test_bot_recommends_which_promo():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    # asks for missing info first, keeping the intent
    b = c.post("/api/bot", headers=H(ha), json={"message": "promo apa yang cocok di gerobak?"}).json()
    assert b["context"]["intent"] == "what" and "promos" not in b and b["chips"]
    b = c.post("/api/bot", headers=H(ha), json={"context": b["context"], "set": {"objective": "aov"}}).json()
    assert len(b["promos"]) == 3 and "paling cocok" in b["reply"]
    top = b["promos"][0]
    assert top["result"]["gate"] != "HOLD" and top["result"]["unit"]["cm"] > 0
    assert top["timing"]["start"] == top["promo"]["periodStart"] and top["promo"]["platformProfileId"] == "offline_gerobak"
    assert top["promo"]["nama"] in b["reply"]
    # one sentence with everything
    b2 = c.post("/api/bot", headers=H(ha), json={"message": "rekomendasi promo gofood jakarta untuk trial dan naikkan aov, diskon maks 30%"}).json()
    assert b2["promos"] and b2["context"]["maxDiscountPct"] == 30 and b2["promos"][0]["promo"]["objective2"]
    assert all(x["promo"]["areas"] == ["jakarta"] for x in b2["promos"])
    # switching back to timing works and offers the promo question again
    w = c.post("/api/bot", headers=H(ha), json={"context": b["context"], "set": {"intent": "when", "mechanism": top["promo"]["mechanism"]}}).json()
    assert w["result"]["recommendations"] and any(ch["label"] == "Promo apa yang cocok?" for ch in w["chips"])
    # plain timing question still answers timing
    k = c.post("/api/bot", headers=H(ha), json={"message": "kapan promo aov di gofood 2 minggu?"}).json()
    assert k["context"]["intent"] == "when" and k["result"]["recommendations"] and "promos" not in k
    # viewer gets no margin numbers
    r = c.post("/api/members", headers=H(ha), json={"name": "Vina", "email": "vina@citarasakuliner.com", "role": "viewer"}).json()
    tv = c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": "9999"}).json()["token"]
    v = c.post("/api/bot", headers=H(tv), json={"message": "promo apa yang cocok di gerobak untuk aov"}).json()
    assert "promos" not in v and "CM" not in v["reply"]


def test_finance_cost_control_pricing_approval():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    def member(name, role, pin):
        r = c.post("/api/members", headers=H(ha), json={"name": name, "email": f"{name.lower()}@citarasakuliner.com", "role": role}).json()
        return c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": pin}).json()["token"]
    fi, pl, vw = member("Fikri", "finance", "1111"), member("Kintan", "team_leader", "2222"), member("Vina", "viewer", "3333")
    assert c.get("/api/state", headers=H(fi)).json()["roles"]["finance"] == "Finance / Cost Control"
    p = c.post("/api/promos", headers=H(pl), json={"nama": "Tes Pricing", "objective": "aov", "mechanism": "diskon_persen", "platformProfileId": "offline_kios",
               "areas": ["bandung"], "periodStart": "2026-12-01", "periodEnd": "2026-12-14", "items": [{"productId": "mix-mozza-ayam", "qty": 1}],
               "params": {"discountPct": 10}}).json()
    pid = p["id"]
    assert c.post(f"/api/promos/{pid}/submit", headers=H(pl)).json()["status"] == "review_finance"
    # planner and viewer cannot approve pricing; finance cannot give the final decision
    assert c.post(f"/api/promos/{pid}/review", headers=H(pl), json={"decision": "approve"}).status_code == 403
    assert c.post(f"/api/promos/{pid}/review", headers=H(vw), json={"decision": "approve"}).status_code == 403
    # return needs a note and clears nothing yet
    assert c.post(f"/api/promos/{pid}/review", headers=H(fi), json={"decision": "return"}).status_code == 400
    v = c.post(f"/api/promos/{pid}/review", headers=H(fi), json={"decision": "approve", "note": "HPP sesuai"}).json()
    a = v["pricingApproval"]
    assert v["status"] == "review_head" and a["byName"] == "Fikri" and a["byRole"] == "Finance / Cost Control" and a["at"]
    assert a["pricing"]["bandung"]["cm"] == v["results"]["bandung"]["unit"]["cm"] and a["pricing"]["bandung"]["hpp"]
    assert c.post(f"/api/promos/{pid}/approve", headers=H(fi), json={"decision": "approve"}).status_code == 403
    # viewer sees who approved but no HPP/CM
    vv = c.get(f"/api/promos/{pid}", headers=H(vw)).json()
    assert vv["pricingApproval"]["byName"] == "Fikri" and "pricing" not in vv["pricingApproval"]
    assert all("pricing" not in (x.get("pricingApproval") or {}) for x in c.get("/api/state", headers=H(vw)).json()["promos"])
    # recorded in change history
    rows = c.get("/api/audit?category=promo", headers=H(fi)).json()["rows"]
    assert any(r["action"] == "Menyetujui pricing promo" and r["byName"] == "Fikri" and "CM" in r["detail"] for r in rows)
    assert c.post(f"/api/promos/{pid}/approve", headers=H(ha), json={"decision": "approve"}).json()["status"] == "approved"
    # changing the price after approval sends it back and drops the pricing approval
    v = c.put(f"/api/promos/{pid}", headers=H(pl), json={"params": {"discountPct": 25}}).json()
    assert v["status"] == "draft" and not v.get("pricingApproval")


def test_audit_filters_by_kind_name_date():
    from datetime import date, timedelta
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    r = c.post("/api/members", headers=H(ha), json={"name": "Galuh", "email": "galuh@citarasakuliner.com", "role": "revenue_growth"}).json()
    tg = c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": "5678"}).json()["token"]
    st = c.get("/api/state", headers=H(ha)).json()
    p = st["products"][0]
    c.put(f"/api/products/{p['id']}", headers=H(tg), json={"hpp": p["hpp"] + 50})                      # ubah (Galuh)
    c.post("/api/products", headers=H(tg), json={"nama": "Produk Baru", "hpp": 4000, "prices": {"bandung": 10000, "jakarta": 11000}})  # tambah
    pid = st["promos"][0]["id"]
    c.post(f"/api/promos/{pid}/comments", headers=H(tg), json={"text": "cek HPP"})
    assert c.delete(f"/api/promos/{pid}", headers=H(ha)).status_code == 200                          # hapus (Handry)
    a = c.get("/api/audit", headers=H(ha)).json()
    assert all(x["kind"] in a["kinds"] and len(x["tanggal"]) == 10 and len(x["jam"]) == 8 for x in a["rows"])
    hapus = c.get("/api/audit?kind=hapus", headers=H(ha)).json()["rows"]
    assert hapus and all(x["kind"] == "hapus" for x in hapus) and hapus[0]["byName"] == "Handry" and "Status" in hapus[0]["detail"]
    gid = next(x["id"] for x in a["people"] if x["name"] == "Galuh")
    g = c.get(f"/api/audit?by={gid}&kind=ubah", headers=H(ha)).json()
    assert g["rows"] and all(x["byName"] == "Galuh" and x["kind"] == "ubah" for x in g["rows"])
    assert any(x["action"] == "Menambah komentar" for x in c.get(f"/api/audit?by={gid}&kind=tambah", headers=H(ha)).json()["rows"])
    sm = {x["name"]: x for x in a["summary"]}
    assert sm["Handry"]["hapus"] == 1 and sm["Galuh"]["ubah"] >= 1 and sm["Galuh"]["tambah"] >= 2
    today = a["rows"][0]["tanggal"]
    assert c.get(f"/api/audit?date_from={today}&date_to={today}", headers=H(ha)).json()["total"] == a["total"]
    y = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    assert c.get(f"/api/audit?date_to={y}", headers=H(ha)).json()["total"] == 0
    assert c.get("/api/audit?date_from=ngawur", headers=H(ha)).status_code == 400


def test_three_month_plan():
    from datetime import date, timedelta
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    d = c.post("/api/plan", headers=H(ha), json={"platformProfileId": "gofood"}).json()
    items = d["items"]
    assert len(items) >= 4 and {x["area"] for x in items} == {"bandung", "jakarta"}
    D = date.fromisoformat
    for x in items:
        assert x["result"]["gate"] != "HOLD" and x["result"]["unit"]["cm"] > 0 and x["promo"]["platformProfileId"] == "gofood"
        assert D(x["promo"]["periodStart"]) >= date.today() + timedelta(days=7) and D(x["promo"]["periodStart"]) <= D(d["to"])
    # one main promo per area at a time; same product at least 14 days apart
    for area in ("bandung", "jakarta"):
        lst = sorted((x for x in items if x["area"] == area), key=lambda x: x["promo"]["periodStart"])
        for a, b in zip(lst, lst[1:]):
            assert D(b["promo"]["periodStart"]) > D(a["promo"]["periodEnd"])
        for i, a in enumerate(lst):
            pa = {it["productId"] for it in a["promo"]["items"]}
            for b in lst[i + 1:]:
                if pa & {it["productId"] for it in b["promo"]["items"]}:
                    assert (D(b["promo"]["periodStart"]) - D(a["promo"]["periodEnd"])).days >= 14
    # does not overwrite a scheduled promo (Mozza Duo on gerobak until 31 Dec)
    g = c.post("/api/plan", headers=H(ha), json={"platformProfileId": "offline_gerobak"}).json()
    busy = [(D(e["periodStart"]), D(e["periodEnd"]), e["area"]) for e in g["existing"]]
    assert busy
    for x in g["items"]:
        for a, b, ar in busy:
            assert ar != x["area"] or D(x["promo"]["periodStart"]) > b or D(x["promo"]["periodEnd"]) < a
    # marketplace is national: one track
    assert {x["areaLabel"] for x in c.post("/api/plan", headers=H(ha), json={"platformProfileId": "shopee"}).json()["items"]} == {"Nasional"}
    # a plan item can be saved as a draft as-is
    p = c.post("/api/promos", headers=H(ha), json=items[0]["promo"]).json()
    assert p["status"] == "draft" and p["periodStart"] == items[0]["promo"]["periodStart"]
    # guards
    assert c.post("/api/plan", headers=H(ha), json={"platformProfileId": "event_konser"}).status_code == 400
    assert c.post("/api/plan", headers=H(ha), json={}).status_code == 400
    r = c.post("/api/members", headers=H(ha), json={"name": "Vina", "email": "vina@citarasakuliner.com", "role": "viewer"}).json()
    tv = c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": "9999"}).json()["token"]
    assert c.post("/api/plan", headers=H(tv), json={"platformProfileId": "gofood"}).status_code == 403
    # bot
    b = c.post("/api/bot", headers=H(ha), json={"message": "buatkan rencana promo 3 bulan ke depan"}).json()
    assert b["context"]["intent"] == "plan" and b["chips"] and "link" not in b
    b = c.post("/api/bot", headers=H(ha), json={"message": "rencana promo 3 bulan ke depan untuk gofood"}).json()
    assert b["link"]["to"] == "/rencana" and b["link"]["platformProfileId"] == "gofood" and "promo**" in b["reply"]
    assert "link" not in c.post("/api/bot", headers=H(tv), json={"message": "rencana promo 3 bulan ke depan untuk gofood"}).json()


def test_product_csv_import_is_tolerant():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    before = {p["id"]: p for p in c.get("/api/state", headers=H(ha)).json()["products"]}["mix-mozza-ayam"]
    # Excel Indonesia: titik koma, pemisah ribuan titik, nama kolom tanpa "harga_"
    csv_text = "Nama;HPP;Bandung;Jakarta\nCimol Keju Uji;5.000;12.000;Rp13.000\n"
    assert c.post("/api/products/import", headers=H(ha), content=csv_text.encode()).json()["imported"] == 1
    # hanya HPP untuk produk lama → harga dan kategori lama tetap
    assert c.post("/api/products/import", headers=H(ha), content=b"id,nama,hpp\nmix-mozza-ayam,Mix Mozza Ayam,9900\n").json()["imported"] == 1
    P = {p["id"]: p for p in c.get("/api/state", headers=H(ha)).json()["products"]}
    assert P["cimol-keju-uji"]["hpp"] == 5000 and P["cimol-keju-uji"]["prices"] == {"bandung": 12000, "jakarta": 13000}
    assert P["mix-mozza-ayam"]["hpp"] == 9900 and P["mix-mozza-ayam"]["prices"] == before["prices"] and P["mix-mozza-ayam"]["kategori"] == before["kategori"]
    # format lama tetap jalan
    assert c.post("/api/products/import", headers=H(ha), content=b"nama,hpp,harga_bandung,harga_jakarta\nUji Dua,4000,10000,11000\n").json()["imported"] == 1


def test_cannot_submit_promo_without_customer_benefit():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    base = {"objective": "aov", "platformProfileId": "offline_kios", "areas": ["bandung"], "periodStart": "2026-12-01", "periodEnd": "2026-12-14",
            "items": [{"productId": "mix-mozza-ayam", "qty": 1}]}
    p0 = c.post("/api/promos", headers=H(ha), json={**base, "nama": "Nol", "mechanism": "diskon_persen", "params": {"discountPct": 0}}).json()
    r = c.post(f"/api/promos/{p0['id']}/submit", headers=H(ha))
    assert r.status_code == 400 and "hemat Rp0" in r.json()["detail"]
    for nama, mech, params in (("Diskon", "diskon_persen", {"discountPct": 10}), ("Stamp", "stamp_card", {"n": 5}),
                               ("Voucher", "voucher_next_visit", {"voucherRp": 5000})):
        p = c.post("/api/promos", headers=H(ha), json={**base, "nama": nama, "mechanism": mech, "params": params}).json()
        assert c.post(f"/api/promos/{p['id']}/submit", headers=H(ha)).status_code == 200, nama
    # event tanpa diskon tetap boleh (pricing event)
    pe = c.post("/api/promos", headers=H(ha), json={**base, "nama": "Event", "platformProfileId": "event_bazaar", "mechanism": "diskon_persen",
                "objective": "awareness", "params": {"discountPct": 0}, "trackingReady": True}).json()
    r = c.post(f"/api/promos/{pe['id']}/submit", headers=H(ha))
    assert r.status_code == 200 or "hemat Rp0" not in r.json()["detail"]


def test_edit_learning_record():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    def member(name, role, pin):
        r = c.post("/api/members", headers=H(ha), json={"name": name, "email": f"{name.lower()}@citarasakuliner.com", "role": role}).json()
        return c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": pin}).json()["token"]
    tl, fi = member("Kintan", "team_leader", "2222"), member("Fikri", "finance", "4444")
    base = {"nama": "Combo Kesegaran", "platformProfileId": "offline_kios", "mechanism": "bundle", "objective": "aov", "areas": ["bandung"],
            "periodStart": "2026-10-31", "periodEnd": "2026-11-08", "takeRate": 24.91, "achievement": 31.65, "note": "catatan lama"}
    lid = c.post("/api/learnings", headers=H(tl), json=base).json()["id"]
    long_note = "Dasar perhitungan: " + "x" * 900
    r = c.put(f"/api/learnings/{lid}", headers=H(tl), json={**base, "upliftPct": 1.14, "takeRate": 25, "note": long_note})
    assert r.status_code == 200 and r.json()["editedBy"] == "Kintan"
    rec = next(x for x in c.get("/api/learnings", headers=H(ha)).json()["records"] if x["id"] == lid)
    assert rec["takeRate"] == 25 and rec["upliftPct"] == 1.14 and rec["note"] == long_note and abs(rec["achievement"] - 0.3165) < 1e-9
    # someone else (not creator, not manager) cannot edit; manager can; invalid data rejected
    assert c.put(f"/api/learnings/{lid}", headers=H(fi), json=base).status_code == 403
    assert c.put(f"/api/learnings/{lid}", headers=H(ha), json={**base, "nama": "Combo Kesegaran NPL"}).status_code == 200
    assert c.put(f"/api/learnings/{lid}", headers=H(ha), json={**base, "nama": ""}).status_code == 400
    assert c.put("/api/learnings/tidak-ada", headers=H(ha), json=base).status_code == 404
    rows = c.get("/api/audit?category=belajar", headers=H(ha)).json()["rows"]
    e = next(x for x in rows if x["action"] == "Mengubah hasil promo" and x["byName"] == "Kintan")
    assert "Take rate 24.91 → 25" in e["detail"] and "Catatan diubah" in e["detail"] and e["kind"] == "ubah"


def test_priority_products_in_recommendations():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    st = c.get("/api/state", headers=H(ha)).json()
    fp = st["settings"]["focusProducts"]
    assert fp["mn-dhp"] == 2 and fp["mn-butterscotch"] == 2 and fp["kuah-mozza"] == 1 and fp["mn-jasmine"] == 1 and "mozza-b" not in fp
    rec = lambda **kw: c.post("/api/recommend", headers=H(ha), json={"platformProfileId": "offline_kios", "objective": "aov", "area": "bandung", **kw}).json()["results"]
    r = rec()
    ids = lambda x: {i["productId"] for i in x["promo"]["items"]}
    assert any(x["focus"] == 2 and ids(x) & {"mn-dhp", "mn-butterscotch"} for x in r)          # Da Hong Pao terwakili
    assert any(x["focus"] == 1 for x in r) and sum(1 for x in r if x["focus"]) <= 3            # prioritas lain ada, tidak mendominasi
    P = {p["id"]: p for p in st["products"]}
    for x in r:
        u = x["result"]["unit"]
        assert u["cm"] > 0 and x["result"]["gate"] != "HOLD" and x["score"] <= 100
        if ids(x) & {"mn-dhp", "mn-butterscotch"} and x["promo"]["mechanism"] == "bundle":
            assert (u["customerPays"] - sum(P[i]["hpp"] for i in ids(x))) / u["customerPays"] >= 0.35   # margin paket tetap sehat
            assert not any(P[i]["kategori"] == "frozen" for i in ids(x))                              # minuman + cimol siap makan
    # a drink alone is still never discounted
    d = c.post("/api/calc", headers=H(ha), json={"nama": "x", "objective": "trial", "mechanism": "diskon_persen", "platformProfileId": "offline_kios",
               "areas": ["bandung"], "periodStart": "2026-12-01", "periodEnd": "2026-12-07", "items": [{"productId": "mn-dhp", "qty": 1}], "params": {"discountPct": 20}}).json()
    o = (d.get("results") or d)["bandung"]
    assert next(x for x in o["health"]["components"] if x["key"] == "safety")["score"] == 0
    # manager can change priorities; cleared list → no forced picks
    assert c.put("/api/settings", headers=H(ha), json={"focusProducts": {"mozza-b": 2, "tidak-ada": 1, "mn-dhp": 5}}).status_code == 200
    assert c.get("/api/state", headers=H(ha)).json()["settings"]["focusProducts"] == {"mozza-b": 2}
    assert any("mozza-b" in ids(x) and x["focus"] == 2 for x in rec())
    c.put("/api/settings", headers=H(ha), json={"focusProducts": {}})
    assert all(x["focus"] == 0 for x in rec())
    assert any(r_["action"] == "Mengubah settings" and "Produk prioritas" in r_["detail"] for r_ in c.get("/api/audit?category=settings", headers=H(ha)).json()["rows"])


def test_kios_only_products():
    from app.main import migrate_kios_only_products
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    P = {p["id"]: p for p in c.get("/api/state", headers=H(ha)).json()["products"]}
    for pid in ("ns-beef-mentai", "ns-ayam-mentai", "ns-ayam-takoyaki", "ns-ayam-kare", "ns-beef-kare", "mn-dhp", "mn-jasmine"):
        assert "gerobak" not in P[pid]["channels"] and "kios" in P[pid]["channels"], pid
    assert "gerobak" in P["ns-bojot-misdasem"]["channels"] and "gerobak" in P["mozza-b"]["channels"]
    kios_only = {pid for pid, p in P.items() if "gerobak" not in p["channels"]}
    # gerobak recommendations and plans never contain them
    for obj in ("aov", "trial", "repeat"):
        r = c.post("/api/recommend", headers=H(ha), json={"platformProfileId": "offline_gerobak", "objective": obj, "area": "bandung"}).json()["results"]
        assert r and all(not ({i["productId"] for i in x["promo"]["items"]} & kios_only) for x in r)
    plan = c.post("/api/plan", headers=H(ha), json={"platformProfileId": "offline_gerobak"}).json()["items"]
    assert all(not ({i["productId"] for i in x["promo"]["items"]} & kios_only) for x in plan)
    # kios still gets Da Hong Pao
    r = c.post("/api/recommend", headers=H(ha), json={"platformProfileId": "offline_kios", "objective": "aov", "area": "bandung"}).json()["results"]
    assert any({"mn-dhp", "mn-butterscotch"} & {i["productId"] for i in x["promo"]["items"]} for x in r)
    # one-time migration fixes an older database, records it, and never overrides later manual changes
    db.products.update_one({"id": "ns-ayam-mentai"}, {"$set": {"channels": ["kios", "gerobak", "online_food", "event"]}})
    db.products.update_one({"id": "mn-dhp"}, {"$set": {"channels": ["kios", "gerobak"]}})
    migrate_kios_only_products()
    assert "gerobak" not in db.products.find_one({"id": "ns-ayam-mentai"})["channels"] and db.products.find_one({"id": "mn-dhp"})["channels"] == ["kios"]
    rows = c.get("/api/audit?category=produk", headers=H(ha)).json()["rows"]
    assert any(x["action"] == "Mengubah channel produk" and "Cimol Ayam Mentai" in x["detail"] and x["byName"] == "Sistem" for x in rows)
    db.products.update_one({"id": "mn-dhp"}, {"$set": {"channels": ["kios", "gerobak"]}})   # manager decides otherwise later
    migrate_kios_only_products()
    assert db.products.find_one({"id": "mn-dhp"})["channels"] == ["kios", "gerobak"]


def test_marketplace_fee_migration_and_dated_rate():
    from app.main import migrate_marketplace_fees
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    # simulate an older database with the old assumptions, and a TikTok profile the team already validated
    db.profiles.update_one({"id": "shopee"}, {"$set": {"label": "Shopee – Star", "feeComponents": [
        {"key": "admin", "label": "Biaya admin (Kategori A)", "type": "percent", "rate": 10, "base": "net_after_all_discount", "appliesWhen": "always", "active": True}]}})
    db.profiles.update_one({"id": "tokopedia_tiktok"}, {"$set": {"verified": True, "label": "Punya tim"}})
    migrate_marketplace_fees()
    sh = db.profiles.find_one({"id": "shopee"})
    comps = {x["key"]: x for x in sh["feeComponents"]}
    assert sh["label"] == "Shopee – Non-Mall" and comps["admin"]["rate"] == 6.75 and comps["proses"]["amount"] == 1250
    assert comps["gox"]["rate"] == 6 and comps["gox"]["nextRate"] == 9.5 and comps["gox"]["nextFrom"] == "2026-12-01" and sh["version"] == 2
    assert db.profiles.find_one({"id": "tokopedia_tiktok"})["label"] == "Punya tim"      # validated profile untouched
    assert any(r["action"] == "Mengubah biaya platform" and "6,75%" in r["detail"] for r in c.get("/api/audit?category=platform", headers=H(ha)).json()["rows"])
    # runs once: later manual edits are kept
    db.profiles.update_one({"id": "shopee"}, {"$set": {"label": "Diubah manual"}})
    migrate_marketplace_fees()
    assert db.profiles.find_one({"id": "shopee"})["label"] == "Diubah manual"
    # the fee follows the promo start date
    body = {"nama": "x", "objective": "online", "mechanism": "voucher_platform", "platformProfileId": "shopee", "areas": ["bandung"],
            "items": [{"productId": "fz-ayam-bbq", "qty": 1}], "params": {"voucherPct": 10}}
    cm = lambda a, b: (lambda d: (d.get("results") or d)["bandung"]["unit"]["cm"])(c.post("/api/calc", headers=H(ha), json={**body, "periodStart": a, "periodEnd": b}).json())
    assert cm("2026-11-20", "2026-11-26") == 4570 and cm("2026-12-01", "2026-12-07") == 3782
    # the manager can change the scheduled rate in Platform & Biaya
    prof = c.get("/api/state", headers=H(ha)).json()["profiles"]
    sp = next(p for p in prof if p["id"] == "shopee")
    for x in sp["feeComponents"]:
        if x["key"] == "gox":
            x["nextRate"], x["nextFrom"] = None, None
    assert c.put("/api/platform-profiles/shopee", headers=H(ha), json=sp).status_code == 200
    assert cm("2026-12-01", "2026-12-07") == 4570


def test_healthy_normal_price():
    for col in db.list_collection_names():
        db[col].drop()
    ha = c.post("/api/auth/register", json={"name": "Handry", "pin": "1234", "email": "handry@citarasakuliner.com"}).json()["token"]
    c.post("/api/seed/crk", headers=H(ha))
    d = c.post("/api/pricing/check", headers=H(ha), json={"productId": "mix-mozza-ayam", "tryPrice": 23000}).json()
    R = {r["platformId"]: r for r in d["rows"]}
    k = R["offline_kios"]                       # HPP 9.709, tanpa potongan: 9.709 / (1 − target)
    assert (k["breakeven"], k["minHealthy"], k["target"]) == (10000, 14000, 16500) and k["floorPct"] == 30 and k["targetPct"] == 40
    assert k["status"] == "sehat" and k["current"]["cm"] == 20000 - 9709 and k["promoRoomPct"] == 30.0
    g = R["gofood"]                             # 0,8p − 667 − 1.000 − 9.709 ≥ 20% p → p ≥ 18.960
    assert (g["breakeven"], g["minHealthy"], g["target"]) == (14500, 19000, 23000) and g["status"] == "cukup"
    assert g["trial"]["cm"] == round(23000 * 0.8) - 667 - 1000 - 9709 and g["trial"]["status"] == "sehat"
    for r in d["rows"]:                         # setiap harga saran benar-benar memenuhi marginnya
        a = r["atTarget"]
        assert a["cm"] >= r["targetPct"] / 100 * a["price"] - 1 and r["breakeven"] <= r["minHealthy"] <= r["target"]
    assert R["shopee"]["sold"] is False and R["shopee"]["current"] is None
    # produk baru dari HPP saja + target sendiri
    n = c.post("/api/pricing/check", headers=H(ha), json={"hpp": 6000, "targets": {"offline": 50}}).json()
    assert n["product"] is None and {r["platformId"]: r for r in n["rows"]}["offline_kios"]["target"] == 12000
    # semua produk di satu channel
    o = c.post("/api/pricing/overview", headers=H(ha), json={"platformProfileId": "gofood"}).json()
    assert sum(o["counts"].values()) == len(o["rows"]) and o["counts"]["rugi"] >= 1
    assert o["rows"][0]["status"] == "rugi" and o["rows"][0]["cm"] < 0 and o["rows"][0]["gapToMin"] > 0
    assert all("gerobak" not in r["id"] for r in o["rows"])
    ko = c.post("/api/pricing/overview", headers=H(ha), json={"platformProfileId": "offline_gerobak"}).json()
    assert not any(r["id"].startswith("mn-") or "mentai" in r["id"] for r in ko["rows"])       # minuman & Japanese series tidak di gerobak
    # guards
    assert c.post("/api/pricing/check", headers=H(ha), json={}).status_code == 400
    assert c.post("/api/pricing/check", headers=H(ha), json={"hpp": "abc"}).status_code == 400
    assert c.post("/api/pricing/overview", headers=H(ha), json={"platformProfileId": "event_konser"}).status_code == 400
    r = c.post("/api/members", headers=H(ha), json={"name": "Vina", "email": "vina@citarasakuliner.com", "role": "viewer"}).json()
    tv = c.post("/api/auth/setup", json={"token": r["setupToken"], "pin": "9999"}).json()["token"]
    assert c.post("/api/pricing/check", headers=H(tv), json={"productId": "mix-mozza-ayam"}).status_code == 403
    assert c.post("/api/pricing/overview", headers=H(tv), json={"platformProfileId": "gofood"}).status_code == 403
