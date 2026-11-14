from datetime import date
from app import timing as T

TODAY = date(2026, 11, 12)
MOMENTS = [{"date": "2026-12-12", "end": None, "label": "Harbolnas 12.12", "type": "belanja"},
           {"date": "2026-12-12", "end": None, "label": "Tanggal kembar 12.12", "type": "belanja"},
           {"date": "2026-12-24", "end": "2026-12-26", "label": "Natal", "type": "libur"}]


def test_marketplace_prefers_twin_date():
    r = T.recommend_timing({"channelType": "marketplace", "platformProfileId": "shopee", "objective": "online", "duration": 3},
                           [], MOMENTS, TODAY)
    best = r["recommendations"][0]
    assert best["start"] <= "2026-12-12" <= best["end"]


def test_jam_sepi_prefers_weekdays_and_avoids_holiday():
    r = T.recommend_timing({"channelType": "offline", "platformProfileId": "offline_gerobak", "objective": "jam_sepi", "duration": 5,
                            "from": "2026-12-01", "to": "2026-12-31"}, [], MOMENTS, TODAY)
    best = r["recommendations"][0]
    d0 = date.fromisoformat(best["start"])
    assert all(date.fromordinal(d0.toordinal() + i).weekday() < 5 for i in range(5))  # Mon–Fri block
    assert not (best["start"] <= "2026-12-25" <= best["end"])


def test_conflict_and_cooldown_penalty():
    promos = [{"id": "x", "nama": "Promo X", "effectiveStatus": "approved", "platformProfileId": "gofood", "platformLabel": "GoFood",
               "channelType": "online_food", "areas": ["bandung"], "periodStart": "2026-12-01", "periodEnd": "2026-12-20",
               "products": ["mozza-b"]}]
    req = {"channelType": "online_food", "platformProfileId": "gofood", "objective": "aov", "duration": 7, "products": ["mozza-b"],
           "areas": ["bandung"], "from": "2026-11-20", "to": "2027-01-31"}
    r = T.recommend_timing(req, promos, MOMENTS, TODAY)
    for rec in r["recommendations"]:
        assert not (rec["start"] <= "2026-12-20" and rec["end"] >= "2026-12-01")  # never overlaps the same promo
    chk = T.recommend_timing({**req, "checkStart": "2026-12-05", "checkEnd": "2026-12-11"}, promos, MOMENTS, TODAY)["check"]
    assert any("Bentrok" in c for c in chk["cautions"])


def test_lead_time_respected():
    r = T.recommend_timing({"channelType": "offline", "platformProfileId": "offline_kios", "objective": "trial", "duration": 7}, [], MOMENTS, TODAY)
    assert all(rec["start"] >= "2026-11-19" for rec in r["recommendations"])


def test_parse_message():
    profiles = {"gofood": {"id": "gofood", "productChannel": "online_food"}, "shopee": {"id": "shopee", "productChannel": "marketplace"}}
    products = {"mozza-b": {"id": "mozza-b", "nama": "Cimol Mozza Besar", "kategori": "reguler", "channels": ["online_food"]},
                "fz-mozza-asin": {"id": "fz-mozza-asin", "nama": "Frozen Mozza Asin", "kategori": "frozen", "channels": ["marketplace"]}}
    c = T.parse_message("kapan promo aov mozza di gofood 2 minggu bulan depan bandung", {}, products, profiles, TODAY)
    assert c["platformProfileId"] == "gofood" and c["objective"] == "aov" and c["duration"] == 14
    assert c["products"] == ["mozza-b"] and c["areas"] == ["bandung"] and c["from"] == "2026-12-01"
    c = T.parse_message("cek 1-14 des", c, products, profiles, TODAY)
    assert c["checkStart"] == "2026-12-01" and c["checkEnd"] == "2026-12-14"


def test_duration_advice_rules():
    a = T.duration_advice("flash_sale", "trial", "offline")
    assert (a["min"], a["rec"], a["max"]) == (1, 2, 3)
    a = T.duration_advice("diskon_persen", "aov", "offline", discount_pct=30, current=21)
    assert a["max"] <= 7 and a["status"] == "terlalu panjang"
    a = T.duration_advice("bundle", "aov", "offline", discount_pct=10, health="Sehat", current=21)
    assert a["rec"] == 21 and a["status"] == "pas" and a["checkpoint"]
    a = T.duration_advice("stamp_card", "repeat", "offline", stamp_n=8)
    assert a["min"] >= 40 and a["rec"] <= 60
    assert T.duration_advice("voucher_platform", "online", "marketplace")["rec"] == 3
    assert T.duration_advice("bundle", "awareness", "event", event_days=3)["rec"] == 3
    w = T.duration_advice("bundle", "aov", "offline", health="Waspada")
    assert w["rec"] < 21
    h = T.duration_advice("bundle", "aov", "offline", hist=[(14, 1.2), (14, 1.1), (28, 0.6)])
    assert h["rec"] in (14, 21) and any("Histori" in r for r in h["reasons"])
    assert T.parse_mechanism("diskon 25% mozza") == ("diskon_persen", 25.0)
    d = T.duration_advice("diskon_persen", "aov", "offline", discount_pct=30, health="Waspada", current=21)
    assert d["min"] <= d["rec"] <= d["max"] <= 7
