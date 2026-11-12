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
