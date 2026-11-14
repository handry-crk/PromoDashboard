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
