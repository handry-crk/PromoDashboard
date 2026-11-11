"""Seed data: Price Structure v2 (10 Nov 2026), platform profiles, baselines, history promos."""

OUTLET = ["kios", "gerobak", "online_food", "event"]
FROZEN_CH = ["kios", "marketplace", "event"]
DRINK_CH = ["kios", "online_food", "event"]


def _p(pid, nama, kategori, porsi, hpp, bdg, jkt, channels, **kw):
    prices = {}
    if bdg is not None:
        prices["bandung"] = bdg
    if jkt is not None:
        prices["jakarta"] = jkt
    return {"id": pid, "sku": pid.upper(), "nama": nama, "kategori": kategori, "porsi": porsi, "hpp": hpp,
            "prices": prices, "platformPrices": {}, "channels": channels, "active": True, **kw}


PRODUCTS = [
    _p("bojot-k", "Cimol Bojot Kecil", "reguler", "kecil", 3341, 6000, 6000, OUTLET),
    _p("bojot-b", "Cimol Bojot Besar", "reguler", "besar", 6754, 12000, 12000, OUTLET),
    _p("mozza-k", "Cimol Mozza Kecil", "reguler", "kecil", 5004, 10000, 11000, OUTLET),
    _p("mozza-b", "Cimol Mozza Besar", "reguler", "besar", 10080, 20000, 22000, OUTLET),
    _p("beef-k", "Cimol Beef Kecil", "reguler", "kecil", 5185, 10000, 11000, OUTLET),
    _p("beef-b", "Cimol Beef Besar", "reguler", "besar", 10442, 20000, 22000, OUTLET),
    _p("ayam-k", "Cimol Ayam Kecil", "reguler", "kecil", 4633, 10000, 11000, OUTLET),
    _p("ayam-b", "Cimol Ayam Besar", "reguler", "besar", 9338, 20000, 22000, OUTLET),
    _p("mix-mozza-bojot", "Mix Mozza Bojot", "mix", "-", 8417, 16000, 17000, OUTLET),
    _p("mix-ayam-bojot", "Mix Ayam Bojot", "mix", "-", 8046, 16000, 17000, OUTLET),
    _p("mix-beef-bojot", "Mix Beef Bojot", "mix", "-", 8598, 16000, 17000, OUTLET),
    _p("mix-mozza-ayam", "Mix Mozza Ayam", "mix", "-", 9709, 20000, 22000, OUTLET),
    _p("mix-mozza-beef", "Mix Mozza Beef", "mix", "-", 10261, 20000, 22000, OUTLET),
    _p("kuah-mozza", "Kuah Keju Mozza", "kuah_keju", "-", 8245, 15000, 15000, OUTLET),
    _p("kuah-beef", "Kuah Keju Beef", "kuah_keju", "-", 8426, 15000, 15000, OUTLET),
    _p("kuah-ayam", "Kuah Keju Ayam", "kuah_keju", "-", 7874, 15000, 15000, OUTLET),
    _p("ns-beef-mentai", "Cimol Beef Mentai", "new_series", "-", 7650, 15000, 15000, OUTLET),
    _p("ns-ayam-mentai", "Cimol Ayam Mentai", "new_series", "-", 7494, 15000, 15000, OUTLET),
    _p("ns-ayam-takoyaki", "Cimol Ayam Saus Takoyaki", "new_series", "-", 8286, 15000, 15000, OUTLET),
    _p("ns-ayam-kare", "Cimol Ayam Kare Jepang", "new_series", "-", 8952, 15000, 15000, OUTLET),
    _p("ns-beef-kare", "Cimol Beef Kare Jepang", "new_series", "-", 9108, 15000, 15000, OUTLET),
    _p("ns-bojot-misdasem", "Cimol Bojot Saus Misdasem", "new_series", "-", 6833, 10000, 10000, OUTLET),
    _p("ns-bojot-kacang", "Cimol Bojot Saus Kacang", "new_series", "-", 6958, 10000, 10000, OUTLET),
    _p("fz-mozza-asin", "Frozen Mozza Asin Pedas", "frozen", "-", 9996, 26000, 26000, FROZEN_CH),
    _p("fz-mozza-bawang", "Frozen Mozza Ayam Bawang", "frozen", "-", 9952, 26000, 26000, FROZEN_CH),
    _p("fz-mozza-balado", "Frozen Mozza Balado", "frozen", "-", 10081, 26000, 26000, FROZEN_CH),
    _p("fz-mozza-bbq", "Frozen Mozza Barbeque", "frozen", "-", 10131, 26000, 26000, FROZEN_CH),
    _p("fz-mozza-jagung", "Frozen Mozza Jagung Bakar", "frozen", "-", 10042, 26000, 26000, FROZEN_CH),
    _p("fz-ayam-asin", "Frozen Ayam Asin Pedas", "frozen", "-", 8571, 25000, 25000, FROZEN_CH),
    _p("fz-ayam-bawang", "Frozen Ayam Ayam Bawang", "frozen", "-", 8600, 25000, 25000, FROZEN_CH),
    _p("fz-ayam-balado", "Frozen Ayam Balado", "frozen", "-", 8562, 25000, 25000, FROZEN_CH),
    _p("fz-ayam-bbq", "Frozen Ayam Barbeque", "frozen", "-", 8173, 25000, 25000, FROZEN_CH),
    _p("fz-ayam-jagung", "Frozen Ayam Jagung Bakar", "frozen", "-", 9291, 25000, 25000, FROZEN_CH),
    _p("mn-jasmine", "Sweet Jasmine Tea", "minuman", "-", 8764, 12000, 12000, DRINK_CH),
    _p("mn-mango", "Mango Jasmine Tea", "minuman", "-", 11468, 16000, 16000, DRINK_CH),
    _p("mn-dhp", "Da Hong Pao Milk Tea", "minuman", "-", 12758, 18000, 18000, DRINK_CH),
    _p("mn-earlgrey", "Earl Grey Milk Tea", "minuman", "-", 12218, 18000, 18000, DRINK_CH),
    _p("mn-butterscotch", "Butterscotch Da Hong Pao", "minuman", "-", 17082, 24000, 24000, DRINK_CH),
    _p("mn-lemonade", "Sweet Lemonade", "minuman", "-", 12820, 17000, 17000, DRINK_CH),
]
for p in PRODUCTS:
    if p["kategori"] == "frozen":
        p["marketplaceCategory"] = "Kategori A – makanan/snack (cek)"

NOTE = "Asumsi publik Nov 2026 — cocokkan dengan Merchant/Seller Center"


def _offline(pid, label, ch):
    return {"id": pid, "platform": pid, "channelType": "offline", "productChannel": ch, "label": label,
            "verified": True, "sourceNote": "Tanpa potongan platform", "effectiveDate": "2026-11-10",
            "pricing": {"markupPct": 0, "roundingStep": 500, "packagingFeeToCustomer": 0}, "avgUnitsPerOrder": 1,
            "feeComponents": [], "ppnPct": 0, "adminFeeDiscountPct": 0, "programs": [],
            "costs": {"extraPackagingPerOrder": 0, "returnAllowancePct": 0, "paymentFeePct": 0, "otherFixedPerOrder": 0},
            "ads": {"model": "none"}, "version": 1}


def _food(pid, label, comps, prog_key, prog_label):
    return {"id": pid, "platform": pid, "channelType": "online_food", "productChannel": "online_food", "label": label,
            "verified": False, "sourceNote": NOTE, "effectiveDate": "2026-11-11",
            "pricing": {"markupPct": 0, "roundingStep": 500, "packagingFeeToCustomer": 0}, "avgUnitsPerOrder": 1.5,
            "feeComponents": comps, "ppnPct": 0, "adminFeeDiscountPct": 0,
            "programs": [{"programKey": prog_key, "label": prog_label, "defaultPlatformFundingPct": 50,
                          "description": "Diskon dibagi merchant dan platform"}],
            "costs": {"extraPackagingPerOrder": 1500, "returnAllowancePct": 0, "paymentFeePct": 0, "otherFixedPerOrder": 0},
            "ads": {"model": "pct_of_sales", "pct": 0}, "version": 1}


def _comp(key, label, typ="percent", rate=0, amount=0, base="net_after_merchant_discount", when="always",
          program=None, taxable=False, discountable=False, cap=0, payer="merchant"):
    return {"key": key, "label": label, "type": typ, "rate": rate, "amount": amount, "base": base, "cap": cap,
            "appliesWhen": when, "programKey": program, "taxable": taxable, "discountable": discountable,
            "payer": payer, "active": True}


PROFILES = [
    _offline("offline_kios", "Offline Kios", "kios"),
    _offline("offline_gerobak", "Offline Gerobak", "gerobak"),
    _offline("event", "Event / Booth", "event"),
    _food("gofood", "GoFood – Reguler", [
        _comp("komisi", "Komisi GoFood", rate=20, taxable=True),
        _comp("biaya_order", "Biaya per order", "fixed_per_order", amount=1000, taxable=True)],
        "gofood_cofund", "GoFood Promo Co-funding"),
    _food("grabfood", "GrabFood – Reguler", [_comp("komisi", "Komisi GrabFood", rate=20, taxable=True)],
          "grabfood_cofund", "GrabFood Diskon Bersama"),
    _food("shopeefood", "ShopeeFood – Reguler", [_comp("komisi", "Komisi ShopeeFood", rate=20, taxable=True)],
          "shopeefood_cofund", "ShopeeFood Promo Spesial"),
    {"id": "shopee", "platform": "shopee", "channelType": "marketplace", "productChannel": "marketplace",
     "label": "Shopee – Star", "verified": False, "sourceNote": NOTE, "effectiveDate": "2026-11-11",
     "pricing": {"markupPct": 0, "roundingStep": 1000, "packagingFeeToCustomer": 0}, "avgUnitsPerOrder": 2,
     "feeComponents": [
         _comp("admin", "Biaya admin (Kategori A)", rate=10, base="net_after_all_discount", discountable=True),
         _comp("proses", "Biaya proses pesanan", "fixed_per_order", amount=1250),
         _comp("gox", "Gratis Ongkir XTRA", "percent_capped", base="net_after_all_discount", when="program_opt_in", program="gratis_ongkir_xtra"),
         _comp("cbx", "Cashback / Promo XTRA", "percent_capped", base="net_after_all_discount", when="program_opt_in", program="cashback_xtra"),
         _comp("po", "Pre-order", rate=3, base="net_after_all_discount", when="program_opt_in", program="preorder")],
     "ppnPct": 0, "adminFeeDiscountPct": 0,
     "programs": [{"programKey": "gratis_ongkir_xtra", "label": "Gratis Ongkir XTRA", "defaultPlatformFundingPct": 0},
                  {"programKey": "cashback_xtra", "label": "Cashback XTRA", "defaultPlatformFundingPct": 0},
                  {"programKey": "preorder", "label": "Pre-order", "defaultPlatformFundingPct": 0}],
     "costs": {"extraPackagingPerOrder": 6000, "returnAllowancePct": 2, "paymentFeePct": 0, "otherFixedPerOrder": 0},
     "ads": {"model": "roas", "roas": 8}, "version": 1},
    {"id": "tokopedia_tiktok", "platform": "tokopedia_tiktok", "channelType": "marketplace", "productChannel": "marketplace",
     "label": "Tokopedia/TikTok Shop – Power Merchant", "verified": False, "sourceNote": NOTE, "effectiveDate": "2026-11-11",
     "pricing": {"markupPct": 0, "roundingStep": 1000, "packagingFeeToCustomer": 0}, "avgUnitsPerOrder": 2,
     "feeComponents": [
         _comp("komisi", "Komisi platform", rate=10, base="net_after_all_discount", discountable=True),
         _comp("logistik", "Biaya layanan logistik (isi dari Seller Center)", "fixed_per_order", amount=0),
         _comp("growth", "Growth Xtra", "percent_capped", base="net_after_all_discount", when="program_opt_in", program="growth_xtra")],
     "ppnPct": 0, "adminFeeDiscountPct": 0,
     "programs": [{"programKey": "growth_xtra", "label": "Growth Xtra", "defaultPlatformFundingPct": 0}],
     "costs": {"extraPackagingPerOrder": 6000, "returnAllowancePct": 2, "paymentFeePct": 0, "otherFixedPerOrder": 0},
     "ads": {"model": "roas", "roas": 8}, "version": 1},
]

BASELINES = {
    "offline_kios": {"bandung": {"gpPerTrx": 12650, "aovNormal": 25000, "trxPerOutletDay": 150, "outlets": 1, "openRate": 100},
                     "jakarta": {"gpPerTrx": 12650, "aovNormal": 25000, "trxPerOutletDay": 150, "outlets": 1, "openRate": 100}},
    "offline_gerobak": {"bandung": {"aovNormal": 15000, "trxPerOutletDay": 68, "outlets": 140, "openRate": 93},
                        "jakarta": {"aovNormal": 15000, "trxPerOutletDay": 68, "outlets": 358, "openRate": 83}},
}


def history_promos():
    return [
        {"id": "PR-2611-01", "kode": "PR-2611-01", "nama": "Mozza Duo", "objective": "aov", "mechanism": "bundle",
         "platformProfileId": "offline_gerobak", "areas": ["bandung", "jakarta"], "periodStart": "2026-11-10",
         "periodEnd": "2026-12-31", "outlets": 498, "openRate": 85, "trxPerOutletDay": 68,
         "items": [{"productId": "mozza-b", "qty": 1}, {"productId": "mozza-k", "qty": 1}],
         "params": {"packagePrice": 27000},
         "areaParams": {"bandung": {"outlets": 140, "openRate": 93}, "jakarta": {"packagePrice": 30000, "outlets": 358, "openRate": 83}},
         "segmentMix": [
             {"label": "Upgrade dari Mozza besar", "share": 50, "counterfactual": ["mozza-b"]},
             {"label": "Upgrade dari Mozza kecil", "share": 20, "counterfactual": ["mozza-k"]},
             {"label": "Kanibalisasi (beli keduanya)", "share": 30, "counterfactual": ["mozza-b", "mozza-k"]}],
         "quotaPerOutletDay": 20, "capacityPerOutletDay": 25, "trackingReady": True,
         "fixedCosts": [{"label": "POSM 498 gerobak", "amount": 74700000}],
         "scenarioInputs": {"pesimis": {"takeRate": 7, "trafficUplift": 2}, "target": {"takeRate": 10, "trafficUplift": 4},
                            "optimis": {"takeRate": 14, "trafficUplift": 7}},
         "funding": {"merchantPct": 100}, "status": "running"},
        {"id": "PR-2610-01", "kode": "PR-2610-01", "nama": "Paket AA 30 Ribu", "objective": "aov", "mechanism": "bundle",
         "platformProfileId": "offline_kios", "areas": ["bandung"], "periodStart": "2026-10-15", "periodEnd": "2026-10-31",
         "items": [{"productId": "ayam-b", "qty": 1}, {"productId": "mn-dhp", "qty": 1}], "params": {"packagePrice": 30000},
         "funding": {"merchantPct": 100}, "status": "rejected",
         "rejectNote": "GM di bawah GP transaksi rata-rata; revisi harga ≥ 34.700 atau ganti minuman"},
        {"id": "PR-2610-02", "kode": "PR-2610-02", "nama": "Braga Pairing", "objective": "aov", "mechanism": "bundle",
         "platformProfileId": "offline_kios", "areas": ["bandung"], "periodStart": "2026-10-20", "periodEnd": "2026-11-20",
         "outlets": 1, "items": [{"productId": "mn-dhp", "qty": 1}, {"productId": "fz-mozza-balado", "qty": 1}],
         "params": {"packagePrice": 40000}, "funding": {"merchantPct": 100}, "status": "approved", "trackingReady": True,
         "quotaPerOutletDay": 15, "capacityPerOutletDay": 30},
    ]
