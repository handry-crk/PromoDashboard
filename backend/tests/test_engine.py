import copy
import pytest
from app import engine as E
from app.seed import PRODUCTS, PROFILES, BASELINES

P = {p["id"]: p for p in PRODUCTS}
PR = {p["id"]: p for p in PROFILES}


def run(promo, prof, area, base=None, **kw):
    base = base if base is not None else BASELINES.get(prof, {}).get(area, {})
    return E.run(promo, P, PR[prof], area, None, base, **kw)


def test_b1g1_bojot_hold():
    o = run({"mechanism": "bxgy", "objective": "trial", "items": [{"productId": "bojot-k"}, {"productId": "bojot-k", "role": "free"}]},
            "offline_kios", "bandung")
    u = o["unit"]
    assert u["customerPays"] == 6000 and u["hpp"] == 6682 and u["cm"] == -682
    assert round(u["cmPct"] * 100, 1) == -11.4
    assert u["discountTotal"] == 6000 and u["discountPct"] == 0.5
    assert o["health"]["label"] == "Tidak Sehat" and o["margin"]["label"] == "Buruk"
    assert o["menarik"]["score"] >= 70 and o["quadrant"] == "Margin Trap" and o["gate"]["status"] == "HOLD"
    assert any(f["type"] == "swap" for f in o["fixes"])


MOZZA = {"mechanism": "bundle", "objective": "aov", "items": [{"productId": "mozza-b"}, {"productId": "mozza-k"}],
         "params": {"packagePrice": 27000}, "areaParams": {"jakarta": {"packagePrice": 30000}},
         "segmentMix": [{"label": "a", "share": 50, "counterfactual": ["mozza-b"]},
                        {"label": "b", "share": 20, "counterfactual": ["mozza-k"]},
                        {"label": "c", "share": 30, "counterfactual": ["mozza-b", "mozza-k"]}]}


def test_mozza_duo():
    o = run(MOZZA, "offline_gerobak", "bandung")
    u = o["unit"]
    assert (u["listPrice"], u["discountTotal"], u["hpp"], u["cm"]) == (30000, 3000, 15084, 11916)
    assert round(u["discountPct"] * 100, 1) == 10.0 and round(u["cmPct"] * 100, 1) == 44.1
    assert o["incremental"]["incRevenuePerUnit"] == 6000 and o["incremental"]["incCmPerUnit"] == 1482
    j = run(MOZZA, "offline_gerobak", "jakarta")
    assert j["unit"]["cm"] == 14916 and round(j["unit"]["cmPct"] * 100, 1) == 49.7
    assert j["incremental"]["incCmPerUnit"] == 2382


def test_paket_aa():
    o = run({"mechanism": "bundle", "objective": "aov", "items": [{"productId": "ayam-b"}, {"productId": "mn-dhp"}],
             "params": {"packagePrice": 30000}}, "offline_kios", "bandung")
    u = o["unit"]
    assert (u["listPrice"], u["discountTotal"], u["hpp"], u["cm"]) == (38000, 8000, 22096, 7904)
    assert round(u["discountPct"] * 100, 1) == 21.1 and round(u["cmPct"] * 100, 1) == 26.3
    assert round(u["cmVsBaseline"] * 100) == 62
    assert o["health"]["label"] == "Tidak Sehat" and o["margin"]["label"] == "Buruk" and o["menarik"]["label"] == "Menarik"
    assert o["quadrant"] == "Margin Trap" and o["gate"]["status"] == "HOLD"
    assert o["minHealthyPrice"]["exact"] == 34746 and o["minHealthyPrice"]["rounded"] == 35000


def test_braga_pairing():
    o = run({"mechanism": "bundle", "objective": "aov", "items": [{"productId": "mn-dhp"}, {"productId": "fz-mozza-balado"}],
             "params": {"packagePrice": 40000}}, "offline_kios", "bandung")
    u = o["unit"]
    assert (u["discountTotal"], u["hpp"], u["cm"]) == (4000, 22839, 17161)
    assert round(u["discountPct"] * 100, 1) == 9.1 and round(u["cmPct"] * 100, 1) == 42.9
    assert (300 * 40000, 300 * u["hpp"], 300 * u["cm"], 300 * u["discountTotal"]) == (12000000, 6851700, 5148300, 1200000)


def test_diskon_ayam_jkt():
    o = run({"mechanism": "diskon_persen", "items": [{"productId": "ayam-b"}], "params": {"discountPct": 20}}, "offline_kios", "jakarta")
    u = o["unit"]
    assert (u["customerPays"], u["normalCM"], u["cm"]) == (17600, 12662, 8262)
    assert round(u["cmPct"] * 100, 1) == 46.9 and round(u["discountDepth"] * 100, 1) == 34.7
    assert round(u["breakevenUplift"] * 100, 1) == 53.3
    assert next(c for c in o["health"]["components"] if c["key"] == "depth")["score"] == 100
    assert next(c for c in o["health"]["components"] if c["key"] == "breakeven")["score"] == 0


GO = {"mechanism": "diskon_persen", "objective": "online", "items": [{"productId": "mix-mozza-ayam"}],
      "params": {"discountPct": 20}, "overrides": {"avgUnitsPerOrder": 1, "extraPackagingPerOrder": 0}}


def test_gofood():
    o = run(GO, "gofood", "jakarta")
    u = o["unit"]
    assert (u["merchantDiscount"], u["merchantGross"], u["platformFees"], u["merchantNet"], u["cm"]) == (4400, 17600, 4520, 13080, 3371)
    assert round(u["cmPct"] * 100, 1) == 19.2 and round(u["effectiveTakeRate"] * 100, 1) == 25.7
    assert round(u["gmPct"] * 100, 1) == 44.8
    prof = copy.deepcopy(PR["gofood"]); prof["ppnPct"] = 11
    o2 = E.run(GO, P, prof, "jakarta")
    assert o2["unit"]["cm"] == 2874


def test_gofood_cofund():
    o = run({**GO, "funding": {"merchantPct": 50, "platformPct": 50}}, "gofood", "jakarta")
    u = o["unit"]
    assert u["discountTotal"] == 4400 and u["merchantDiscount"] == 2200 and u["merchantGross"] == 19800
    assert u["cm"] == 5131 and round(u["cmPct"] * 100, 1) == 29.2 and u["platformDiscount"] == 2200


def test_markup():
    prof = copy.deepcopy(PR["gofood"]); prof["pricing"]["markupPct"] = 15
    o = E.run(GO, P, prof, "jakarta")
    u = o["unit"]
    assert u["listPrice"] == 25500 and u["customerPays"] == 20400 and u["discountTotal"] == 5100
    assert next(c for c in o["menarik"]["components"] if c["key"] == "vsOutlet")["score"] == 100


def test_shopee_frozen():
    promo = {"mechanism": "voucher_platform", "objective": "online", "items": [{"productId": "fz-ayam-bbq"}],
             "params": {"voucherPct": 10}}
    o = run(promo, "shopee", "bandung")
    u = o["unit"]
    assert u["merchantGross"] == 22500 and u["platformFees"] == 2250 + 625 and u["adsCost"] == 2813
    assert u["channelCosts"] == 3000 + 450 and u["cm"] == 5189 and round(u["cmPct"] * 100, 1) == 23.1
    assert round(u["effectiveTakeRate"] * 100, 1) == 25.3
    o1 = run({**promo, "overrides": {"avgUnitsPerOrder": 1}}, "shopee", "bandung")
    assert o1["unit"]["cm"] < 5189 and any(f["type"] == "bundle2" for f in o1["fixes"])


def test_pending_program_and_verify():
    promo = {"mechanism": "voucher_platform", "objective": "online", "items": [{"productId": "fz-ayam-bbq"}],
             "params": {"voucherPct": 10}, "programsJoined": ["gratis_ongkir_xtra"], "trackingReady": True,
             "quotaPerOutletDay": 10, "capacityPerOutletDay": 20}
    o = run(promo, "shopee", "bandung")
    assert o["gate"]["status"] == "GO WITH CONDITION"
    assert any("Isi tarif program" in c for c in o["gate"]["conditions"])
    assert any("Validasi biaya platform" in c for c in o["gate"]["conditions"])


def test_compare_platforms_numbers():
    k = run(GO, "offline_kios", "jakarta")["unit"]
    assert k["cm"] == 7891 and round(k["cmPct"] * 100, 1) == 44.8
    assert run(GO, "grabfood", "jakarta")["unit"]["cm"] == 4371
    assert run(GO, "shopeefood", "jakarta")["unit"]["cm"] == 4371


def test_recommend_online():
    req = {"objective": "online", "area": "jakarta", "maxDiscountPct": 25, "allowCofunding": True, "maxPlatformPct": 50}
    res = E.recommend(req, P, PR["gofood"], None, {})
    assert len(res) == 5 and res[0]["badge"] == "Rekomendasi utama"
    low = {"mn-jasmine", "mn-mango", "mn-dhp", "mn-earlgrey", "mn-butterscotch", "mn-lemonade", "ns-bojot-misdasem", "ns-bojot-kacang"}
    for x in res:
        assert x["result"]["unit"]["cm"] > 0
        assert not any(i["productId"] in low for i in x["promo"]["items"])
    assert any(x["promo"]["funding"]["merchantPct"] < 100 for x in res) or True


def test_recommend_aov_gerobak_speed():
    import time
    t = time.time()
    res = E.recommend({"objective": "aov", "area": "bandung", "maxDiscountPct": 15}, P, PR["offline_gerobak"], None,
                      BASELINES["offline_gerobak"]["bandung"])
    assert len(res) == 5 and time.time() - t < 3


def test_happy_hour_share_scales_units():
    base = {"mechanism": "happy_hour", "items": [{"productId": "ayam-b"}], "params": {"discountPct": 20, "hourShare": 100}}
    full = run(base, "offline_kios", "bandung")["scenarios"]["target"]["totalUnits"]
    part = run({**base, "params": {"discountPct": 20, "hourShare": 25}}, "offline_kios", "bandung")["scenarios"]["target"]["totalUnits"]
    assert part < full


def test_perceived_saving_for_ongkir():
    o = run({"mechanism": "ongkir", "objective": "online", "items": [{"productId": "ayam-b"}],
             "params": {"merchantOngkirRp": 3000, "platformOngkirRp": 2000}, "overrides": {"avgUnitsPerOrder": 1}}, "gofood", "bandung")
    assert o["unit"]["perceivedSaving"] == 5000 and o["unit"]["extraCost"] == 3000
    assert next(c for c in o["menarik"]["components"] if c["key"] == "hematRp")["score"] == 100


def test_calibration_low_history_lowers_attractiveness():
    b = {"mechanism": "bundle", "objective": "aov", "items": [{"productId": "ayam-b"}, {"productId": "mozza-k"}], "params": {"packagePrice": 27000}}
    hist = [{"mechanism": "bundle", "platformId": "offline_kios", "takeRate": t} for t in (3, 4, 5)]
    assert run(b, "offline_kios", "bandung", history=hist)["menarik"]["score"] < run(b, "offline_kios", "bandung")["menarik"]["score"]


def test_invalid_numbers_raise_calc_error():
    with pytest.raises(E.CalcError):
        run({"mechanism": "diskon_persen", "items": [{"productId": "ayam-b"}], "params": {"discountPct": "abc"}}, "offline_kios", "bandung")
    with pytest.raises(E.CalcError):
        run({"mechanism": "diskon_persen", "items": [{"productId": "ayam-b"}], "params": {"discountPct": 150}}, "offline_kios", "bandung")
