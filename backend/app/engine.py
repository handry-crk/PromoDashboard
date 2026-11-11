"""CRK Promo Calculator — pure calculation engine (no DB access).

All money is integer Rupiah. Every line item is rounded half-up at the end.
"""
from __future__ import annotations

import math
from datetime import date
from itertools import combinations
from typing import Any

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def r(x: float) -> int:
    """Round half up to integer Rupiah."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def ceil_step(x: float, step: int) -> int:
    if step <= 0:
        return r(x)
    return int(math.ceil(x / step - 1e-9) * step)


def pct(a: float, b: float) -> float:
    return (a / b) if b else 0.0


OFFLINE_TYPES = {"offline"}
SINGLE_ITEM_MECHS = {"diskon_persen", "potongan_rp", "harga_spesial", "flash_sale", "happy_hour", "voucher_platform"}
PACKAGE_MECHS = {"bundle", "addon", "bxgy", "min_belanja_gratis"}
ONLINE_ONLY_MECHS = {"voucher_platform", "flash_sale", "ongkir"}

MECHANISMS = {
    "diskon_persen": "Diskon %",
    "potongan_rp": "Potongan harga",
    "harga_spesial": "Harga spesial",
    "bxgy": "Buy X Get Y",
    "bundle": "Bundle / paket",
    "addon": "Add-on / tebus murah",
    "min_belanja_gratis": "Gratis item min. belanja",
    "stamp_card": "Stamp card",
    "voucher_next_visit": "Voucher kunjungan berikut",
    "happy_hour": "Happy hour",
    "voucher_platform": "Voucher toko / produk",
    "ongkir": "Diskon ongkir",
    "flash_sale": "Flash sale",
}

SIMPLICITY = {
    "harga_spesial": 100, "diskon_persen": 100, "potongan_rp": 100, "bxgy": 95, "flash_sale": 90,
    "bundle": 85, "ongkir": 85, "voucher_platform": 80, "addon": 80, "happy_hour": 75,
    "min_belanja_gratis": 60, "stamp_card": 50, "voucher_next_visit": 45,
}

OBJECTIVES = {
    "trial": "Trial / traffic", "aov": "Naikkan AOV", "jam_sepi": "Isi jam sepi", "repeat": "Repeat / retention",
    "online": "Online / delivery", "awareness": "Awareness lokal / event", "capture": "Capture data",
}

DEFAULT_FIT = {
    "trial": {"cocok": ["bxgy", "harga_spesial", "diskon_persen", "flash_sale"], "bisa": ["potongan_rp", "bundle", "min_belanja_gratis"]},
    "aov": {"cocok": ["bundle", "addon", "min_belanja_gratis"], "bisa": ["voucher_platform", "bxgy"]},
    "jam_sepi": {"cocok": ["happy_hour"], "bisa": ["diskon_persen", "harga_spesial", "bundle"]},
    "repeat": {"cocok": ["stamp_card", "voucher_next_visit"], "bisa": ["bundle"]},
    "online": {"cocok": ["voucher_platform", "ongkir", "bundle", "diskon_persen", "flash_sale"], "bisa": ["harga_spesial", "addon"]},
    "awareness": {"cocok": ["harga_spesial", "bxgy", "flash_sale"], "bisa": ["diskon_persen"]},
    "capture": {"cocok": ["voucher_next_visit", "stamp_card"], "bisa": ["min_belanja_gratis"]},
}

DEFAULT_SETTINGS = {
    "safeDiscountGm": 45.0,
    "lowMarginGm": 35.0,
    "offlineMarginFloorPct": 30.0,
    "onlineMarginFloorPct": 20.0,
    "marketplaceMarginFloorPct": 20.0,
    "psychPoints": [5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 50000],
    "roundingStep": 500,
    "weights": {"sehat": 0.35, "margin": 0.25, "menarik": 0.25, "fit": 0.15},
    "fit": DEFAULT_FIT,
}


def fit_level(settings: dict, objective: str, mechanism: str) -> str:
    fit = (settings.get("fit") or DEFAULT_FIT).get(objective or "", {})
    if mechanism in fit.get("cocok", []):
        return "cocok"
    if mechanism in fit.get("bisa", []):
        return "bisa"
    return "tidak"


# ---------------------------------------------------------------------------
# prices
# ---------------------------------------------------------------------------

def offline_price(product: dict, area: str) -> int | None:
    return (product.get("prices") or {}).get(area)


def list_price(product: dict, profile: dict, area: str) -> int | None:
    over = ((product.get("platformPrices") or {}).get(profile["id"]) or {}).get(area)
    if over:
        return int(over)
    base = offline_price(product, area)
    if base is None:
        return None
    pricing = profile.get("pricing") or {}
    mk = float(pricing.get("markupPct") or 0)
    if mk:
        return ceil_step(base * (1 + mk / 100), int(pricing.get("roundingStep") or 500))
    return int(base)


def product_gm(product: dict) -> float:
    p = offline_price(product, "bandung") or offline_price(product, "jakarta") or 0
    return pct(p - product["hpp"], p) * 100 if p else 0.0


def product_flags(product: dict, settings: dict) -> dict:
    gm = product_gm(product)
    return {
        "gmPct": round(gm, 1),
        "amanDiskon": gm >= settings.get("safeDiscountGm", 45),
        "hindariGratis": gm < settings.get("lowMarginGm", 35),
    }


def sells_on(product: dict, profile: dict) -> bool:
    return profile.get("productChannel") in (product.get("channels") or []) and product.get("active", True)


# ---------------------------------------------------------------------------
# settlement (platform fees)
# ---------------------------------------------------------------------------

def settle(profile: dict, list_p: int, discount_total: int, merchant_pct: float, *, is_promo: bool,
           programs: list[str], units_per_order: float, overrides: dict | None = None) -> dict:
    """Return merchant-side settlement for one unit."""
    overrides = overrides or {}
    merchant_disc = r(discount_total * merchant_pct / 100)
    platform_disc = discount_total - merchant_disc
    pricing = profile.get("pricing") or {}
    pkg_fee_cust = float(overrides.get("packagingFeeToCustomer", pricing.get("packagingFeeToCustomer") or 0))
    pkg_fee_unit = r(pkg_fee_cust / units_per_order) if pkg_fee_cust else 0
    merchant_gross = list_p - merchant_disc + pkg_fee_unit
    bases = {
        "gross_list": list_p,
        "net_after_merchant_discount": list_p - merchant_disc,
        "net_after_all_discount": list_p - discount_total,
    }
    lines: list[dict] = []
    customer_lines: list[dict] = []
    taxable_sum = 0
    admin_disc = float(profile.get("adminFeeDiscountPct") or 0)
    pending: list[str] = []
    for c in profile.get("feeComponents") or []:
        if not c.get("active", True):
            continue
        when = c.get("appliesWhen", "always")
        if when == "promo_only" and not is_promo:
            continue
        if when == "program_opt_in" and (not is_promo or c.get("programKey") not in programs):
            continue
        typ = c.get("type", "percent")
        rate = float(c.get("rate") or 0)
        amount = float(c.get("amount") or 0)
        base = bases.get(c.get("base", "net_after_all_discount"), bases["net_after_all_discount"])
        if typ == "percent":
            v = rate / 100 * base
        elif typ == "percent_capped":
            per_order = rate / 100 * base * units_per_order
            cap = float(c.get("cap") or 0)
            if cap:
                per_order = min(per_order, cap)
            v = per_order / units_per_order
        elif typ == "fixed_per_order":
            v = amount / units_per_order
        else:
            v = amount
        if c.get("discountable") and admin_disc:
            v = v * (1 - admin_disc / 100)
        v = r(v)
        if when == "program_opt_in" and rate == 0 and amount == 0:
            pending.append(c.get("label", c.get("key")))
        item = {"key": c.get("key"), "label": c.get("label"), "amount": v}
        if c.get("payer", "merchant") == "customer":
            customer_lines.append(item)
            continue
        lines.append(item)
        if c.get("taxable"):
            taxable_sum += v
    ppn = float(profile.get("ppnPct") or 0)
    if ppn and taxable_sum:
        lines.append({"key": "ppn", "label": f"PPN atas biaya {ppn:g}%", "amount": r(taxable_sum * ppn / 100)})
    platform_fees = sum(l["amount"] for l in lines)

    costs = profile.get("costs") or {}
    pack = float(overrides.get("extraPackagingPerOrder", costs.get("extraPackagingPerOrder") or 0))
    ret = float(costs.get("returnAllowancePct") or 0)
    pay = float(costs.get("paymentFeePct") or 0)
    other = float(costs.get("otherFixedPerOrder") or 0)
    cost_lines = []
    if pack:
        cost_lines.append({"key": "packaging", "label": "Packaging channel", "amount": r(pack / units_per_order)})
    if ret:
        cost_lines.append({"key": "retur", "label": f"Cadangan retur/rusak {ret:g}%", "amount": r(merchant_gross * ret / 100)})
    if pay:
        cost_lines.append({"key": "payment", "label": f"Biaya pembayaran {pay:g}%", "amount": r(merchant_gross * pay / 100)})
    if other:
        cost_lines.append({"key": "other", "label": "Biaya lain per order", "amount": r(other / units_per_order)})
    channel_costs = sum(l["amount"] for l in cost_lines)

    ads = dict(profile.get("ads") or {})
    ads.update(overrides.get("ads") or {})
    model = ads.get("model", "none")
    if model == "pct_of_sales":
        ads_cost = r(merchant_gross * float(ads.get("pct") or 0) / 100)
    elif model == "roas" and float(ads.get("roas") or 0) > 0:
        ads_cost = r(merchant_gross / float(ads["roas"]))
    elif model == "cpc" and float(ads.get("cvrPct") or 0) > 0:
        ads_cost = r(float(ads.get("cpc") or 0) / (float(ads["cvrPct"]) / 100) / units_per_order)
    else:
        ads_cost = 0

    return {
        "merchantDiscount": merchant_disc,
        "platformDiscount": platform_disc,
        "packagingFeeToCustomer": pkg_fee_unit,
        "merchantGross": merchant_gross,
        "feeLines": lines,
        "customerFeeLines": customer_lines,
        "platformFees": platform_fees,
        "costLines": cost_lines,
        "channelCosts": channel_costs,
        "adsCost": ads_cost,
        "merchantNet": merchant_gross - platform_fees - channel_costs - ads_cost,
        "pendingPrograms": pending,
    }


# ---------------------------------------------------------------------------
# unit build per mechanism
# ---------------------------------------------------------------------------

class CalcError(ValueError):
    pass


def _items(promo: dict, products: dict, profile: dict, area: str):
    rows = []
    for it in promo.get("items") or []:
        p = products.get(it.get("productId"))
        if not p:
            raise CalcError("Produk tidak ditemukan. Pilih ulang item promo.")
        lp = list_price(p, profile, area)
        if lp is None:
            raise CalcError(f"{p['nama']} tidak dijual di area {area.title()}.")
        qty = int(it.get("qty") or 1)
        rows.append({"p": p, "qty": qty, "role": it.get("role", "paid"), "list": lp * qty, "hpp": p["hpp"] * qty,
                     "offline": (offline_price(p, area) or lp) * qty})
    if not rows:
        raise CalcError("Tambahkan minimal 1 item promo.")
    return rows


def build_unit(promo: dict, products: dict, profile: dict, area: str) -> dict:
    mech = promo.get("mechanism")
    prm = promo.get("params") or {}
    rows = _items(promo, products, profile, area)
    list_total = sum(x["list"] for x in rows)
    hpp = sum(x["hpp"] for x in rows)
    offline_total = sum(x["offline"] for x in rows)
    paid_list = sum(x["list"] for x in rows if x["role"] != "free")
    extra_cost = 0  # mechanism cost not shown as price discount (stamp, voucher next visit, ongkir)
    extra_label = None
    perceived = None  # customer-perceived saving for mechanisms without a price cut
    if mech in ("diskon_persen", "happy_hour"):
        d = float(prm.get("discountPct") or 0)
        if not 0 <= d <= 100:
            raise CalcError("Diskon harus di antara 0 dan 100%.")
        pay = r(list_total * (1 - d / 100))
    elif mech == "potongan_rp":
        pay = list_total - int(prm.get("offRp") or 0)
    elif mech in ("harga_spesial", "flash_sale"):
        pay = int(prm.get("specialPrice") or list_total)
    elif mech == "bundle":
        pay = int(prm.get("packagePrice") or list_total)
    elif mech == "addon":
        trig = rows[0]["list"]
        pay = trig + int(prm.get("addonPrice") or 0) if len(rows) > 1 else trig
    elif mech in ("bxgy", "min_belanja_gratis"):
        pay = paid_list
    elif mech == "voucher_platform":
        if prm.get("voucherPct"):
            off = list_total * float(prm["voucherPct"]) / 100
            cap = float(prm.get("voucherCap") or 0)
            off = min(off, cap) if cap else off
        else:
            off = float(prm.get("voucherRp") or 0)
        pay = r(list_total - off)
    elif mech == "stamp_card":
        pay = list_total
        free = products.get(prm.get("freeProductId")) or rows[0]["p"]
        n = max(int(prm.get("n") or 5), 1)
        extra_cost = r(free["hpp"] * float(prm.get("completionRate") or 50) / 100 / n)
        extra_label = "Biaya stamp card"
        perceived = r((list_price(free, profile, area) or 0) / n)
    elif mech == "voucher_next_visit":
        pay = list_total
        extra_cost = r(float(prm.get("voucherRp") or 0) * float(prm.get("redemptionRate") or 30) / 100)
        extra_label = "Biaya voucher kunjungan berikut"
        perceived = r(float(prm.get("voucherRp") or 0))
    elif mech == "ongkir":
        pay = list_total
        upo = float((promo.get("overrides") or {}).get("avgUnitsPerOrder") or profile.get("avgUnitsPerOrder") or 1)
        extra_cost = r(float(prm.get("merchantOngkirRp") or 0) / upo)
        extra_label = "Subsidi ongkir merchant"
        perceived = r((float(prm.get("merchantOngkirRp") or 0) + float(prm.get("platformOngkirRp") or 0)) / upo)
    else:
        raise CalcError("Mekanisme promo belum dipilih.")
    if pay < 0:
        raise CalcError("Harga promo tidak boleh negatif.")
    if pay > list_total:
        pay = list_total
    return {"rows": rows, "list": list_total, "pay": pay, "hpp": hpp, "offline": offline_total,
            "discount": list_total - pay, "extraCost": extra_cost, "extraLabel": extra_label, "perceived": perceived}


def _units_per_order(promo: dict, profile: dict) -> float:
    v = (promo.get("overrides") or {}).get("avgUnitsPerOrder")
    return float(v or profile.get("avgUnitsPerOrder") or 1) or 1.0


def unit_cm(profile: dict, list_p: int, discount: int, hpp: int, *, merchant_pct: float, programs: list[str],
            upo: float, overrides: dict, is_promo: bool, extra_cost: int = 0, var_cost: int = 0) -> dict:
    s = settle(profile, list_p, discount, merchant_pct, is_promo=is_promo, programs=programs,
               units_per_order=upo, overrides=overrides)
    s["cm"] = s["merchantNet"] - hpp - extra_cost - var_cost
    return s


def normal_cm_for_items(profile: dict, rows: list[dict], promo: dict) -> int:
    upo = _units_per_order(promo, profile)
    lst = sum(x["list"] for x in rows)
    hpp = sum(x["hpp"] for x in rows)
    return unit_cm(profile, lst, 0, hpp, merchant_pct=100, programs=[], upo=upo,
                   overrides=promo.get("overrides") or {}, is_promo=False)["cm"]


# ---------------------------------------------------------------------------
# main calculation
# ---------------------------------------------------------------------------

def _days(promo: dict) -> int:
    try:
        a = date.fromisoformat(promo.get("periodStart"))
        b = date.fromisoformat(promo.get("periodEnd"))
        return max((b - a).days + 1, 1)
    except Exception:
        return int(promo.get("days") or 30)


def floor_pct(profile: dict, settings: dict) -> float:
    ct = profile.get("channelType")
    if ct == "online_food":
        return settings.get("onlineMarginFloorPct", 20)
    if ct == "marketplace":
        return settings.get("marketplaceMarginFloorPct", 20)
    return settings.get("offlineMarginFloorPct", 30)


def calc(promo: dict, products: dict, profile: dict, area: str, settings: dict | None = None,
         baseline: dict | None = None, history: list[dict] | None = None, light: bool = False) -> dict:
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    baseline = baseline or {}
    mech = promo.get("mechanism")
    if mech in ONLINE_ONLY_MECHS and profile.get("channelType") == "offline":
        raise CalcError(f"{MECHANISMS[mech]} hanya untuk online food atau marketplace.")
    u = build_unit(promo, products, profile, area)
    upo = _units_per_order(promo, profile)
    funding = promo.get("funding") or {}
    merchant_pct = float(funding.get("merchantPct", 100))
    if profile.get("channelType") == "offline":
        merchant_pct = 100
    programs = promo.get("programsJoined") or []
    overrides = promo.get("overrides") or {}
    var_cost = int(promo.get("variableCostPerUnit") or 0)

    s = unit_cm(profile, u["list"], u["discount"], u["hpp"], merchant_pct=merchant_pct, programs=programs,
                upo=upo, overrides=overrides, is_promo=True, extra_cost=u["extraCost"], var_cost=var_cost)
    cm = s["cm"]
    customer_pays = u["pay"]
    gross_profit = s["merchantGross"] - u["hpp"]
    normal = normal_cm_for_items(profile, u["rows"], promo)
    promo_cost = s["merchantDiscount"] + u["extraCost"]
    is_online = profile.get("channelType") in ("online_food", "marketplace")
    eff_take = pct(s["platformFees"] + s["adsCost"], s["merchantGross"]) if is_online else None
    base_gp = baseline.get("gpPerTrx")
    cm_vs_base = pct(cm, base_gp) if (base_gp and mech in PACKAGE_MECHS) else None
    breakeven = None
    if mech in SINGLE_ITEM_MECHS:
        breakeven = (normal / cm - 1) if cm > 0 else float("inf")

    # offline comparison (same items at outlet price)
    off_cm = None
    if is_online:
        off_cm = sum(x["offline"] for x in u["rows"]) - u["hpp"]

    unit = {
        "listPrice": u["list"], "customerPays": customer_pays, "discountTotal": u["discount"],
        "discountPct": pct(u["discount"], u["list"]), "merchantDiscount": s["merchantDiscount"],
        "platformDiscount": s["platformDiscount"], "merchantGross": s["merchantGross"],
        "feeLines": s["feeLines"], "customerFeeLines": s["customerFeeLines"], "platformFees": s["platformFees"],
        "costLines": s["costLines"], "channelCosts": s["channelCosts"], "adsCost": s["adsCost"],
        "extraCost": u["extraCost"], "extraLabel": u["extraLabel"], "variableCost": var_cost,
        "hpp": u["hpp"], "merchantNet": s["merchantNet"], "cm": cm, "cmPct": pct(cm, customer_pays),
        "grossProfit": gross_profit, "gmPct": pct(gross_profit, s["merchantGross"]),
        "effectiveTakeRate": eff_take, "normalCM": normal, "cmLossPerUnit": normal - cm,
        "discountDepth": pct(promo_cost, normal) if normal > 0 else (1.0 if promo_cost else 0.0),
        "breakevenUplift": breakeven, "cmVsBaseline": cm_vs_base,
        "cmVsOffline": pct(cm, off_cm) if off_cm else None, "offlineCM": off_cm,
        "outletPrice": u["offline"], "unitsPerOrder": upo, "pendingPrograms": s["pendingPrograms"],
        "perceivedSaving": u["perceived"] if u["perceived"] is not None else u["discount"],
    }

    # incremental model
    inc = None
    if mech in PACKAGE_MECHS and len(u["rows"]) >= 1:
        segs = promo.get("segmentMix") or default_segments(u["rows"])
        tot_share = sum(float(sg.get("share") or 0) for sg in segs) or 100
        inc_rev = 0.0
        inc_cm = 0.0
        seg_out = []
        for sg in segs:
            cf_rows = []
            for pid in sg.get("counterfactual") or []:
                p = products.get(pid)
                if p:
                    lp = list_price(p, profile, area) or 0
                    cf_rows.append({"list": lp, "hpp": p["hpp"]})
            cf_list = sum(x["list"] for x in cf_rows)
            cf_cm = normal_cm_for_items(profile, cf_rows, promo) if cf_rows else 0
            ir = customer_pays - cf_list
            ic = cm - cf_cm
            sh = float(sg.get("share") or 0) / tot_share
            inc_rev += sh * ir
            inc_cm += sh * ic
            seg_out.append({"label": sg.get("label"), "share": sg.get("share"), "counterfactual": sg.get("counterfactual"), "incRevenue": ir, "incCM": ic})
        inc = {"incRevenuePerUnit": r(inc_rev), "incCmPerUnit": r(inc_cm), "segments": seg_out}

    # minimum healthy price
    min_price = None
    if mech in PACKAGE_MECHS | SINGLE_ITEM_MECHS:
        min_price = min_healthy_price(profile, u, promo, settings, base_gp if mech in PACKAGE_MECHS else None,
                                      merchant_pct, programs, upo, overrides, var_cost)

    scen = scenarios(promo, unit, inc, baseline, profile)

    health = health_score(promo, unit, scen, settings, profile, mech)
    margin = margin_score(unit)
    menarik = attract_score(promo, unit, u, settings, profile, mech, history)
    quadrant = quad(health, margin, menarik)
    gate = gate_status(promo, health, margin, scen, profile, unit)
    out = {
        "area": area, "platformId": profile["id"], "platformLabel": profile.get("label"),
        "channelType": profile.get("channelType"), "mechanism": mech, "unit": unit, "incremental": inc,
        "minHealthyPrice": min_price, "scenarios": scen, "health": health, "margin": margin,
        "menarik": menarik, "quadrant": quadrant, "gate": gate,
    }
    out["takeaway"] = idfmt(takeaway(promo, out))
    for blk in (health, menarik):
        for c in blk["components"]:
            c["note"] = idfmt(c["note"])
    if not light:
        out["fixes"] = fix_suggestions(promo, products, profile, area, settings, baseline, out)
        for f in out["fixes"]:
            f["detail"] = idfmt(f["detail"])
    return out


def idfmt(s: str) -> str:
    """Indonesian decimal comma for percentages (44.1% -> 44,1%)."""
    import re
    return re.sub(r"(\d)\.(\d+%)", r"\1,\2", s or "")


def default_segments(rows: list[dict]) -> list[dict]:
    paid = [x for x in rows]
    if len(paid) < 2:
        return [{"label": "Pembelian normal (kanibalisasi)", "share": 100, "counterfactual": [x["p"]["id"] for x in paid]}]
    srt = sorted(paid, key=lambda x: x["list"], reverse=True)
    return [
        {"label": "Upgrade dari item termahal saja", "share": 50, "counterfactual": [srt[0]["p"]["id"]]},
        {"label": "Upgrade dari item termurah saja", "share": 20, "counterfactual": [srt[-1]["p"]["id"]]},
        {"label": "Tetap beli semua item harga normal (kanibalisasi)", "share": 30,
         "counterfactual": [x["p"]["id"] for x in paid]},
    ]


def min_healthy_price(profile, u, promo, settings, base_gp, merchant_pct, programs, upo, overrides, var_cost):
    fl = floor_pct(profile, settings) / 100
    step = int(settings.get("roundingStep") or 500)

    def cm_at(p: int) -> int:
        disc = max(u["list"] - p, 0)
        return unit_cm(profile, max(u["list"], p), disc, u["hpp"], merchant_pct=merchant_pct, programs=programs,
                       upo=upo, overrides=overrides, is_promo=True, extra_cost=u["extraCost"], var_cost=var_cost)["cm"]

    def ok(p: int) -> bool:
        target = max(base_gp or 0, fl * p)
        return cm_at(p) >= target

    lo, hi = max(u["hpp"], 1), max(u["list"] * 4, u["hpp"] * 6, 10000)
    if not ok(hi):
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if ok(mid):
            hi = mid
        else:
            lo = mid + 1
    return {"exact": lo, "rounded": ceil_step(lo, step), "target": "baseline" if base_gp else "floor",
            "aboveList": lo > u["list"]}


def scenarios(promo, unit, inc, baseline, profile):
    sc_in = promo.get("scenarioInputs") or {}
    outlets = float(promo.get("outlets") or baseline.get("outlets") or 1)
    open_rate = float(promo.get("openRate") or baseline.get("openRate") or 100) / 100
    trx = float(promo.get("trxPerOutletDay") or baseline.get("trxPerOutletDay") or 50)
    aov = float(baseline.get("aovNormal") or unit["listPrice"])
    days = _days(promo)
    outlet_days = outlets * days * open_rate
    quota = promo.get("quotaPerOutletDay")
    capacity = promo.get("capacityPerOutletDay")
    fixed = sum(int(f.get("amount") or 0) for f in promo.get("fixedCosts") or [])
    defaults = {"pesimis": {"takeRate": 7, "trafficUplift": 2}, "target": {"takeRate": 10, "trafficUplift": 4},
                "optimis": {"takeRate": 14, "trafficUplift": 7}}
    out = {}
    for k in ("pesimis", "target", "optimis"):
        si = {**defaults[k], **(sc_in.get(k) or {})}
        tr = float(si["takeRate"]) / 100
        if promo.get("mechanism") == "happy_hour":
            tr *= float((promo.get("params") or {}).get("hourShare") or 100) / 100
        up = float(si["trafficUplift"]) / 100
        units = trx * (1 + up) * tr
        if quota:
            units = min(units, float(quota))
        new_trx = trx * up
        new_buy = min(new_trx, units)
        existing = units - new_buy
        if inc:
            inc_cm_day = existing * inc["incCmPerUnit"] + new_buy * unit["cm"]
            inc_rev_day = existing * inc["incRevenuePerUnit"] + new_buy * unit["customerPays"]
        else:
            inc_cm_day = existing * (unit["cm"] - unit["normalCM"]) + new_buy * unit["cm"]
            inc_rev_day = existing * (unit["customerPays"] - unit["listPrice"]) + new_buy * unit["customerPays"]
        tot_units = units * outlet_days
        inc_cm = inc_cm_day * outlet_days
        merch_disc = tot_units * (unit["merchantDiscount"] + unit["extraCost"])
        contribution = inc_cm - fixed
        invest = merch_disc + fixed
        base_rev_day = trx * aov
        out[k] = {
            "takeRate": si["takeRate"], "trafficUplift": si["trafficUplift"],
            "unitsPerOutletDay": round(units, 1), "totalUnits": r(tot_units),
            "incRevenue": r(inc_rev_day * outlet_days), "incCM": r(inc_cm),
            "merchantDiscount": r(merch_disc), "platformSubsidy": r(tot_units * unit["platformDiscount"]),
            "platformFees": r(tot_units * unit["platformFees"]), "fixedCosts": fixed,
            "contribution": r(contribution), "investment": r(invest),
            "roi": (contribution / invest) if invest else None,
            "revenuePerOutletDay": r(base_rev_day + inc_rev_day), "baselineRevenuePerOutletDay": r(base_rev_day),
            "revenueChangePct": pct(inc_rev_day, base_rev_day),
            "capacityOk": (units <= float(capacity)) if capacity else None,
        }
    out["meta"] = {"outletDays": r(outlet_days), "days": days, "outlets": outlets, "openRate": open_rate * 100,
                   "trxPerOutletDay": trx}
    return out


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def _label(score: float, hi: int, mid: int, labels: tuple[str, str, str]) -> str:
    return labels[0] if score >= hi else labels[1] if score >= mid else labels[2]


def health_score(promo, unit, scen, settings, profile, mech):
    fl = floor_pct(profile, settings) / 100
    comps = []
    hard = []

    def add(key, label, weight, score, note):
        comps.append({"key": key, "label": label, "weight": weight, "score": score, "note": note})

    cm, cmp_ = unit["cm"], unit["cmPct"]
    if cm <= 0:
        add("cm", "CM per unit", 25, 0, f"CM Rp{cm:,} — rugi per transaksi".replace(",", "."))
        hard.append("CM per unit ≤ 0")
    elif cmp_ >= fl:
        add("cm", "CM per unit", 25, 100, f"CM {cmp_*100:.1f}% ≥ batas {fl*100:.0f}%")
    else:
        add("cm", "CM per unit", 25, 50, f"CM {cmp_*100:.1f}% di bawah batas {fl*100:.0f}%")
    dd = unit["discountDepth"]
    add("depth", "Diskon vs CM normal", 15, 100 if dd <= 0.5 else 50 if dd <= 0.8 else 0,
        f"{dd*100:.0f}% margin normal diberikan")
    if unit["cmVsBaseline"] is not None:
        v = unit["cmVsBaseline"]
        add("baseline", "CM vs transaksi rata-rata", 15, 100 if v >= 1 else 50 if v >= 0.85 else 0,
            f"{v*100:.0f}% dari CM transaksi rata-rata")
    if unit["breakevenUplift"] is not None:
        b = unit["breakevenUplift"]
        add("breakeven", "Breakeven uplift", 10, 100 if b <= 0.25 else 50 if b <= 0.5 else 0,
            "Tidak bisa balik modal" if b == float("inf") else f"Butuh +{b*100:.1f}% volume")
    if unit["effectiveTakeRate"] is not None:
        t = unit["effectiveTakeRate"]
        add("take", "Potongan platform efektif", 10, 100 if t <= 0.25 else 50 if t <= 0.35 else 0,
            f"{t*100:.1f}% dari pendapatan kotor")
    bad_items = unsafe_items(promo, unit, settings, mech)
    add("safety", "Item aman diskon", 10, 0 if bad_items else 100,
        ("Item bermargin rendah didiskon/gratis: " + ", ".join(bad_items)) if bad_items else "Tidak ada item bermargin rendah yang didiskon")
    q, c = promo.get("quotaPerOutletDay"), promo.get("capacityPerOutletDay")
    if q and c and float(q) > float(c):
        add("capacity", "Kapasitas", 10, 0, f"Kuota {q} > kapasitas {c}/outlet/hari")
        hard.append("Kuota melebihi kapasitas")
    elif q and c:
        add("capacity", "Kapasitas", 10, 100, f"Kuota {q} ≤ kapasitas {c}")
    else:
        add("capacity", "Kapasitas", 10, 50, "Kuota/kapasitas belum diisi")
    tc = scen["target"]["contribution"]
    add("scenario", "Contribution skenario Target", 5, 100 if tc > 0 else 0, f"Rp{tc:,}".replace(",", "."))
    tw = sum(x["weight"] for x in comps)
    score = sum(x["weight"] * x["score"] for x in comps) / tw if tw else 0
    label = _label(score, 75, 50, ("Sehat", "Waspada", "Tidak Sehat"))
    strategic = (promo.get("strategic") or {}).get("isStrategic") and (promo.get("strategic") or {}).get("reason")
    if hard:
        label = "Tidak Sehat — Strategis" if strategic else "Tidak Sehat"
        score = min(score, 49)
    return {"score": round(score), "label": label, "components": comps, "hardFails": hard}


def unsafe_items(promo, unit, settings, mech):
    low = settings.get("lowMarginGm", 35)
    discounted = unit["discountTotal"] > 0
    bad = []
    for idx, (n, gm, role) in enumerate(promo.get("_itemGm", [])):
        if gm >= low:
            continue
        if role == "free" or (discounted and not (mech == "addon" and idx == 0)):
            bad.append(n)
    return bad


def margin_score(unit):
    c = unit["cmPct"] * 100
    if c >= 40:
        s = 100.0
    elif c >= 30:
        s = 50 + (c - 30) / 10 * 49
    elif c >= 20:
        s = 20 + (c - 20) / 10 * 29
    else:
        s = 0.0
    if unit["cmVsBaseline"] is not None and unit["cmVsBaseline"] < 1:
        s -= 20
    s = max(0.0, s)
    return {"score": round(s), "label": _label(s, 70, 50, ("Bagus", "Cukup", "Buruk")),
            "cmPct": unit["cmPct"], "gmBeforePlatform": unit["gmPct"]}


def attract_score(promo, unit, u, settings, profile, mech, history):
    comps = []

    def add(key, label, weight, score, note):
        comps.append({"key": key, "label": label, "weight": weight, "score": score, "note": note})

    hr = unit["perceivedSaving"]
    hp = pct(hr, unit["listPrice"]) * 100
    add("hematPct", "Hemat %", 25, 20 if hp < 5 else 50 if hp < 10 else 80 if hp < 20 else 100 if hp <= 35 else 85,
        f"Hemat {hp:.1f}%" + ("" if hr == unit["discountTotal"] else " (nilai yang dirasakan customer)"))
    add("hematRp", "Hemat Rp", 15, 20 if hr < 1000 else 50 if hr < 3000 else 80 if hr < 5000 else 100,
        f"Hemat Rp{hr:,}".replace(",", "."))
    price = unit["customerPays"]
    psych = any(0 <= pt - price <= 1000 for pt in settings.get("psychPoints", []))
    add("psych", "Harga psikologis", 15, 100 if psych else 60, f"Harga Rp{price:,}".replace(",", "."))
    add("simple", "Kemudahan mekanisme", 15, SIMPLICITY.get(mech, 70), MECHANISMS.get(mech, mech))
    if profile.get("channelType") in ("online_food", "marketplace"):
        ratio = pct(price, unit["outletPrice"]) - 1
        sc = 100 if ratio <= 0 else 70 if ratio <= 0.10 else 40 if ratio <= 0.20 else 20
        add("vsOutlet", "Harga app vs outlet", 10, sc, f"{ratio*100:+.1f}% vs harga outlet")
    free = any(x["role"] == "free" for x in u["rows"])
    days = _days(promo) if promo.get("periodStart") else 30
    if free or mech in ("ongkir", "flash_sale") or promo.get("programsJoined") or days <= 14:
        us, note = 100, "Ada kata gratis / urgency / program platform"
    elif days > 60:
        us, note = 40, f"Periode {days} hari terlalu panjang"
    else:
        us, note = 70, f"Periode {days} hari"
    add("urgency", "Gratis / urgency", 10, us, note)
    fl = fit_level(settings, promo.get("objective"), mech)
    add("fit", "Fit objective", 10, {"cocok": 100, "bisa": 60}.get(fl, 20), f"{fl.title()} untuk {OBJECTIVES.get(promo.get('objective'), '-')}")
    tw = sum(x["weight"] for x in comps)
    rule = sum(x["weight"] * x["score"] for x in comps) / tw
    calibrated = None
    hist = [h for h in (history or []) if h.get("mechanism") == mech and h.get("platformId") == profile["id"]
            and h.get("takeRate") is not None]
    final = rule
    if len(hist) >= 3:
        # actual take rate of this mechanism on this platform vs the take rate the plan assumes
        avg_actual = sum(h["takeRate"] for h in hist) / len(hist)
        target_tr = float(((promo.get("scenarioInputs") or {}).get("target") or {}).get("takeRate") or 10)
        hist_score = max(0.0, min(100.0, avg_actual / target_tr * 80)) if target_tr else 50.0
        final = 0.6 * rule + 0.4 * hist_score
        calibrated = len(hist)
    return {"score": round(final), "label": _label(final, 70, 50, ("Menarik", "Cukup", "Kurang")),
            "components": comps, "calibratedFrom": calibrated, "fit": fl}


def quad(h, m, a):
    healthy = h["label"] == "Sehat" or (h["label"] == "Waspada" and m["label"] != "Buruk")
    attractive = a["label"] == "Menarik"
    if healthy and attractive:
        return "Star"
    if attractive:
        return "Margin Trap"
    if healthy:
        return "Sleeper"
    return "Avoid"


def gate_status(promo, h, m, scen, profile, unit):
    conds = []
    if h["label"] == "Tidak Sehat":
        return {"status": "HOLD", "conditions": [f"Promo Tidak Sehat: {', '.join(h['hardFails']) or 'skor di bawah 50'}"]}
    if "Kuota melebihi kapasitas" in h["hardFails"]:
        return {"status": "HOLD", "conditions": ["Kuota melebihi kapasitas outlet"]}
    if h["label"].startswith("Tidak Sehat"):
        conds.append("Pengecualian strategis: batasi investasi sesuai alasan tertulis")
    if h["label"] == "Waspada":
        conds.append("Skor Sehat masih Waspada — lihat saran perbaikan")
    if m["label"] == "Buruk":
        conds.append("Margin Buruk setelah biaya platform")
    if not promo.get("trackingReady"):
        conds.append("Siapkan SKU/kode voucher di POS untuk tracking")
    q, c = promo.get("quotaPerOutletDay"), promo.get("capacityPerOutletDay")
    if not (q and c):
        conds.append("Isi kuota dan kapasitas per outlet/hari (konfirmasi Ops)")
    if scen["target"]["contribution"] <= 0:
        conds.append("Contribution skenario Target belum positif")
    if not profile.get("verified"):
        conds.append(f"Validasi biaya platform {profile.get('label')}")
    if unit.get("pendingPrograms"):
        conds.append("Isi tarif program: " + ", ".join(unit["pendingPrograms"]))
    return {"status": "GO" if not conds else "GO WITH CONDITION", "conditions": conds}


def rp(x) -> str:
    x = r(x)
    s = f"{abs(x):,}".replace(",", ".")
    return ("−Rp" if x < 0 else "Rp") + s


def takeaway(promo, out):
    u = out["unit"]
    nama = promo.get("nama") or MECHANISMS.get(promo.get("mechanism"), "Promo")
    plat = out["platformLabel"]
    good = []
    if out["menarik"]["label"] == "Menarik":
        good.append(f"menarik dengan hemat {rp(u['discountTotal'])} ({u['discountPct']*100:.0f}%)")
    if out["health"]["label"] == "Sehat":
        good.append(f"sehat dengan CM {rp(u['cm'])} ({u['cmPct']*100:.1f}%)")
    first = f"{nama} di {plat} " + (" dan ".join(good) if good else f"menghasilkan CM {rp(u['cm'])} per unit") + "."
    risk = None
    if u["cm"] <= 0:
        risk = f"setiap transaksi rugi {rp(-u['cm'])}"
    elif out["health"]["label"] != "Sehat" or out["margin"]["label"] == "Buruk":
        if u["effectiveTakeRate"] and u["effectiveTakeRate"] > 0.2:
            risk = f"potongan platform {u['effectiveTakeRate']*100:.1f}% membuat CM tinggal {rp(u['cm'])} ({u['cmPct']*100:.1f}%)"
        elif u["cmVsBaseline"] is not None and u["cmVsBaseline"] < 1:
            risk = f"CM per paket hanya {u['cmVsBaseline']*100:.0f}% dari transaksi rata-rata (kanibalisasi)"
        else:
            bad = [c["label"] for c in out["health"]["components"] if c["score"] == 0]
            risk = "perlu perbaikan di " + ", ".join(bad[:2]).lower() if bad else f"CM {u['cmPct']*100:.1f}% masih tipis"
    elif out["menarik"]["label"] != "Menarik":
        risk = "daya tarik untuk customer masih " + out["menarik"]["label"].lower()
    return first + (f" Namun, {risk}." if risk else "")


# ---------------------------------------------------------------------------
# fixes & recommendations
# ---------------------------------------------------------------------------

def _clone(p):
    import copy
    return copy.deepcopy(p)


def fix_suggestions(promo, products, profile, area, settings, baseline, out):
    if out["quadrant"] == "Star" and out["gate"]["status"] == "GO":
        return []
    fixes = []
    u = out["unit"]
    mech = promo.get("mechanism")
    mp = out.get("minHealthyPrice")
    if mp and mp["rounded"] > u["customerPays"] and mech in ("bundle", "harga_spesial", "flash_sale"):
        np_ = _clone(promo)
        key = "packagePrice" if mech == "bundle" else "specialPrice"
        np_.setdefault("params", {})[key] = mp["rounded"]
        fixes.append({"type": "price", "title": f"Naikkan harga ke {rp(mp['rounded'])}",
                      "detail": f"Harga minimum agar CM sehat {rp(mp['exact'])}.", "patch": {"params": np_["params"]}})
    if mech == "diskon_persen":
        d0 = float((promo.get("params") or {}).get("discountPct") or 0)
        for d in range(int(d0) - 5, 0, -5):
            np_ = _clone(promo)
            np_["params"]["discountPct"] = d
            try:
                o = calc(np_, products, profile, area, settings, baseline, light=True)
            except CalcError:
                break
            if o["health"]["label"] == "Sehat":
                fixes.append({"type": "discount", "title": f"Turunkan diskon ke {d}%",
                              "detail": f"CM naik ke {rp(o['unit']['cm'])}; tetap {o['menarik']['label'].lower()}.",
                              "patch": {"params": np_["params"]}})
                break
    if profile.get("channelType") in ("online_food", "marketplace") and u["discountTotal"] > 0:
        cur = float((promo.get("funding") or {}).get("merchantPct", 100))
        for m in range(int(cur) - 10, -1, -10):
            np_ = _clone(promo)
            np_["funding"] = {"merchantPct": m, "platformPct": 100 - m}
            o = calc(np_, products, profile, area, settings, baseline, light=True)
            if o["health"]["label"] == "Sehat":
                fixes.append({"type": "cofund", "title": f"Ajukan co-funding platform {100-m}%",
                              "detail": f"CM naik ke {rp(o['unit']['cm'])}; customer tetap hemat {rp(u['discountTotal'])}.",
                              "patch": {"funding": np_["funding"]}})
                break
    low = settings.get("lowMarginGm", 35)
    bad = [(i, it) for i, it in enumerate(promo.get("items") or [])
           if products.get(it.get("productId")) and product_gm(products[it["productId"]]) < low]
    if bad and mech in ("bundle", "bxgy", "min_belanja_gratis", "diskon_persen"):
        i, it = bad[0]
        orig = products[it["productId"]]
        op = offline_price(orig, area) or 0
        cands = [p for p in products.values() if sells_on(p, profile) and product_gm(p) >= settings.get("safeDiscountGm", 45)
                 and offline_price(p, area) and p["id"] not in [x.get("productId") for x in promo["items"]]]
        cands.sort(key=lambda p: abs((offline_price(p, area) or 0) - op))
        if cands:
            sw = cands[0]
            np_ = _clone(promo)
            np_["items"][i]["productId"] = sw["id"]
            np_.pop("segmentMix", None)
            fixes.append({"type": "swap", "title": f"Ganti {orig['nama']} dengan {sw['nama']}",
                          "detail": f"{orig['nama']} GM {product_gm(orig):.0f}% tidak aman didiskon; {sw['nama']} GM {product_gm(sw):.0f}%.",
                          "patch": {"items": np_["items"], "segmentMix": None}})
    if mech == "bxgy":
        it = (promo.get("items") or [{}])[0]
        orig = products.get(it.get("productId"))
        if orig and out["unit"]["cm"] <= 0:
            safe = [p for p in products.values() if sells_on(p, profile) and product_gm(p) >= settings.get("safeDiscountGm", 45)
                    and offline_price(p, area)]
            safe.sort(key=lambda p: offline_price(p, area))
            if safe:
                sw = safe[0]
                np_ = _clone(promo)
                for x in np_["items"]:
                    x["productId"] = sw["id"]
                fixes.append({"type": "swap", "title": f"B1G1 pakai {sw['nama']}",
                              "detail": f"GM {product_gm(sw):.0f}% memberi ruang untuk item gratis.",
                              "patch": {"items": np_["items"]}})
    q, c = promo.get("quotaPerOutletDay"), promo.get("capacityPerOutletDay")
    if q and c and float(q) > float(c):
        fixes.append({"type": "quota", "title": f"Batasi kuota ke {c}/outlet/hari", "detail": "Kuota tidak boleh melebihi kapasitas.",
                      "patch": {"quotaPerOutletDay": c}})
    if profile.get("channelType") == "marketplace" and u["unitsPerOrder"] < 2:
        fixes.append({"type": "bundle2", "title": "Jual bundle 2 pack", "detail": "Biaya per order dan packaging dingin terbagi ke 2 pack.",
                      "patch": {"overrides": {**(promo.get("overrides") or {}), "avgUnitsPerOrder": 2}}})
    return fixes[:5]


def prepare_promo(promo: dict, products: dict) -> dict:
    """Attach item margin info used by the item-safety rule."""
    p = dict(promo)
    p["_itemGm"] = [(products[it["productId"]]["nama"], product_gm(products[it["productId"]]), it.get("role", "paid"))
                    for it in promo.get("items") or [] if it.get("productId") in products]
    return p


def run(promo, products, profile, area, settings=None, baseline=None, history=None, light=False):
    try:
        return _run(promo, products, profile, area, settings, baseline, history, light)
    except (ValueError, TypeError) as e:
        if isinstance(e, CalcError):
            raise
        raise CalcError("Ada isian angka yang tidak valid. Periksa harga, diskon, dan jumlah.") from e


def _run(promo, products, profile, area, settings=None, baseline=None, history=None, light=False):
    ap = dict((promo.get("areaParams") or {}).get(area) or {})
    if ap:
        top = {k: ap.pop(k) for k in ("outlets", "openRate", "trxPerOutletDay", "quotaPerOutletDay", "capacityPerOutletDay") if k in ap}
        top = {k: v for k, v in top.items() if v not in (None, "")}
        promo = {**promo, **top, "params": {**(promo.get("params") or {}), **ap}}
    return calc(prepare_promo(promo, products), products, profile, area, settings, baseline, history, light)


def snap(x: float, points: list[int], step: int) -> int:
    """Largest psychological price point not above x (within Rp1.500), else floor to step."""
    near = [pt for pt in points if pt <= x and x - pt <= 1500]
    return max(near) if near else int(x // step * step)


def recommend(req: dict, products: dict, profile: dict, settings: dict | None, baseline: dict | None,
              history: list[dict] | None = None, top: int = 5) -> list[dict]:
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    area = req.get("area", "bandung")
    objective = req.get("objective", "aov")
    max_disc = float(req.get("maxDiscountPct") or 30)
    budget = req.get("budget")
    allow_cofund = req.get("allowCofunding") and profile.get("channelType") != "offline"
    max_pf = float(req.get("maxPlatformPct") or 50)
    include = set(req.get("includeProducts") or [])
    exclude = set(req.get("excludeProducts") or [])
    mechs_allowed = req.get("mechanisms") or (
        (settings.get("fit") or DEFAULT_FIT).get(objective, {}).get("cocok", []) +
        (settings.get("fit") or DEFAULT_FIT).get(objective, {}).get("bisa", []))
    if profile.get("channelType") == "offline":
        mechs_allowed = [m for m in mechs_allowed if m not in ONLINE_ONLY_MECHS]
    low = settings.get("lowMarginGm", 35)
    safe_gm = settings.get("safeDiscountGm", 45)
    items = [p for p in products.values() if sells_on(p, profile) and list_price(p, profile, area)
             and p["id"] not in exclude and p.get("kategori") != "addon"]
    if include:
        items = [p for p in items if p["id"] in include] or items
    safe_items = [p for p in items if product_gm(p) >= low]
    points = settings.get("psychPoints", [])
    step = int(settings.get("roundingStep") or 500)
    base_promo = {k: req.get(k) for k in ("objective", "periodStart", "periodEnd", "outlets", "openRate",
                                         "trxPerOutletDay", "quotaPerOutletDay", "capacityPerOutletDay",
                                         "scenarioInputs", "fixedCosts", "trackingReady", "overrides")}
    base_promo["objective"] = objective
    cands: list[dict] = []

    def add(mech, its, params, nama):
        cands.append({**base_promo, "mechanism": mech, "items": its, "params": params, "nama": nama})

    for m in mechs_allowed:
        if m in ("diskon_persen", "happy_hour", "flash_sale", "harga_spesial", "potongan_rp", "voucher_platform"):
            for p in safe_items:
                lp = list_price(p, profile, area)
                for d in (10, 15, 20, 25, 30):
                    if d > max_disc:
                        continue
                    if m == "diskon_persen" or m == "happy_hour":
                        add(m, [{"productId": p["id"], "qty": 1}], {"discountPct": d, "hourShare": 30}, f"Diskon {d}% {p['nama']}")
                    elif m == "voucher_platform":
                        add(m, [{"productId": p["id"], "qty": 2}], {"voucherPct": d}, f"Voucher {d}% {p['nama']} (2 pcs)")
                    else:
                        sp = snap(lp * (1 - d / 100), points, step)
                        if sp >= lp or (lp - sp) / lp * 100 > max_disc:
                            continue
                        lbl = "Flash sale" if m == "flash_sale" else "Harga spesial" if m == "harga_spesial" else "Potongan"
                        if m == "potongan_rp":
                            add(m, [{"productId": p["id"], "qty": 1}], {"offRp": lp - sp}, f"Potongan {rp(lp-sp)} {p['nama']}")
                        else:
                            add(m, [{"productId": p["id"], "qty": 1}], {"specialPrice": sp}, f"{lbl} {p['nama']} {rp(sp)}")
        elif m == "bxgy":
            for p in items:
                if product_gm(p) < safe_gm:
                    continue
                add(m, [{"productId": p["id"], "qty": 1}, {"productId": p["id"], "qty": 1, "role": "free"}], {}, f"B1G1 {p['nama']}")
                add(m, [{"productId": p["id"], "qty": 2}, {"productId": p["id"], "qty": 1, "role": "free"}], {}, f"B2G1 {p['nama']}")
        elif m == "bundle":
            pool = sorted(safe_items, key=lambda p: -(list_price(p, profile, area) or 0))[:24]
            for a, b in combinations(pool, 2):
                lp = list_price(a, profile, area) + list_price(b, profile, area)
                seen = set()
                for d in (5, 10, 15):
                    if d > max_disc:
                        continue
                    pp = snap(lp * (1 - d / 100), points, step)
                    if pp >= lp or pp in seen:
                        continue
                    seen.add(pp)
                    add(m, [{"productId": a["id"], "qty": 1}, {"productId": b["id"], "qty": 1}], {"packagePrice": pp},
                        f"Paket {a['nama']} + {b['nama']} {rp(pp)}")
            if profile.get("channelType") == "marketplace":
                for p in safe_items:
                    lp = list_price(p, profile, area)
                    for n in (2, 3, 5):
                        for d in (5, 10):
                            pp = ceil_step(lp * n * (1 - d / 100), 1000)
                            add(m, [{"productId": p["id"], "qty": n}], {"packagePrice": pp}, f"Bundle {n} pack {p['nama']} {rp(pp)}")
        elif m == "addon":
            for a in items:
                for b in safe_items:
                    if a["id"] == b["id"]:
                        continue
                    lb = list_price(b, profile, area)
                    for ap in range(3000, 10001, 1000):
                        if ap >= lb or (lb - ap) / (lb + list_price(a, profile, area)) * 100 > max_disc:
                            continue
                        add(m, [{"productId": a["id"], "qty": 1}, {"productId": b["id"], "qty": 1}], {"addonPrice": ap},
                            f"Beli {a['nama']}, tebus {b['nama']} {rp(ap)}")
        elif m == "stamp_card":
            for p in safe_items[:12]:
                for n in (5, 8):
                    add(m, [{"productId": p["id"], "qty": 1}], {"n": n, "completionRate": 40, "freeProductId": p["id"]},
                        f"Stamp card beli {n} gratis 1 {p['nama']}")
        elif m == "voucher_next_visit":
            for p in safe_items[:12]:
                for v in (3000, 5000):
                    add(m, [{"productId": p["id"], "qty": 1}], {"voucherRp": v, "redemptionRate": 30},
                        f"Voucher balik lagi {rp(v)} ({p['nama']})")
        elif m == "ongkir":
            for p in safe_items[:12]:
                for v in (3000, 5000):
                    add(m, [{"productId": p["id"], "qty": 1}], {"merchantOngkirRp": v}, f"Diskon ongkir {rp(v)} ({p['nama']})")
        elif m == "min_belanja_gratis":
            cheap = sorted([p for p in safe_items], key=lambda p: list_price(p, profile, area))[:3]
            for a in safe_items[:12]:
                for f in cheap:
                    if a["id"] == f["id"]:
                        continue
                    add(m, [{"productId": a["id"], "qty": 2}, {"productId": f["id"], "qty": 1, "role": "free"}], {},
                        f"Beli 2 {a['nama']} gratis {f['nama']}")

    fund_opts = [100]
    if allow_cofund:
        fund_opts.append(int(100 - max_pf))
    progs = [None] + [pg["programKey"] for pg in (profile.get("programs") or []) if pg["programKey"] in (req.get("programsAllowed") or [])]
    hist_by = {}
    for h in history or []:
        if h.get("achievement") is not None:
            hist_by.setdefault((h.get("mechanism"), h.get("platformId")), []).append(h["achievement"])

    results = []
    w = settings.get("weights", DEFAULT_SETTINGS["weights"])
    for c in cands:
        for mp in fund_opts:
            for pg in progs:
                pr = _clone(c)
                pr["funding"] = {"merchantPct": mp, "platformPct": 100 - mp}
                pr["programsJoined"] = [pg] if pg else []
                if pg:
                    pdef = next((x for x in profile.get("programs") or [] if x["programKey"] == pg), {})
                    if mp == 100 and pdef.get("defaultPlatformFundingPct"):
                        pr["funding"] = {"merchantPct": 100 - pdef["defaultPlatformFundingPct"],
                                         "platformPct": pdef["defaultPlatformFundingPct"]}
                try:
                    o = run(pr, products, profile, area, settings, baseline, history, light=True)
                except CalcError:
                    continue
                u = o["unit"]
                if u["cm"] <= 0 or o["health"]["label"].startswith("Tidak Sehat"):
                    continue
                if u["discountPct"] * 100 > max_disc + 0.01:
                    continue
                if any(c_["key"] == "safety" and c_["score"] == 0 for c_ in o["health"]["components"]):
                    continue
                if budget and o["scenarios"]["target"]["investment"] > float(budget):
                    continue
                fit_s = {"cocok": 100, "bisa": 60}.get(o["menarik"]["fit"], 20)
                base = (w["sehat"] * o["health"]["score"] + w["margin"] * o["margin"]["score"] +
                        w["menarik"] * o["menarik"]["score"] + w["fit"] * fit_s)
                hs = hist_by.get((pr["mechanism"], profile["id"]))
                mult = max(0.8, min(1.2, sum(hs) / len(hs))) if hs else 1.0
                pr["nama"] = c["nama"] + (f" · co-funding {100-pr['funding']['merchantPct']}%" if pr["funding"]["merchantPct"] < 100 else "") + \
                    (f" · {pg}" if pg else "")
                results.append({"promo": pr, "score": round(base * mult, 1), "multiplier": mult, "result": {
                    "unit": {k: u[k] for k in ("listPrice", "customerPays", "discountTotal", "discountPct", "cm", "cmPct",
                                               "effectiveTakeRate", "merchantDiscount", "platformDiscount", "platformFees")},
                    "health": {"score": o["health"]["score"], "label": o["health"]["label"]},
                    "margin": {"score": o["margin"]["score"], "label": o["margin"]["label"]},
                    "menarik": {"score": o["menarik"]["score"], "label": o["menarik"]["label"]},
                    "quadrant": o["quadrant"], "gate": o["gate"]["status"],
                    "contribution": o["scenarios"]["target"]["contribution"], "roi": o["scenarios"]["target"]["roi"],
                    "takeaway": o["takeaway"]}})
    results.sort(key=lambda x: (-x["score"], -x["result"]["contribution"]))
    picked, seen, per_mech, per_anchor = [], set(), {}, {}
    for strict in (True, False):
        for x in results:
            if len(picked) >= top:
                break
            mech = x["promo"]["mechanism"]
            anchor = x["promo"]["items"][0]["productId"]
            key = (mech, tuple(sorted(i["productId"] for i in x["promo"]["items"])))
            if key in seen:
                continue
            if strict and (per_mech.get(mech, 0) >= 2 or per_anchor.get(anchor, 0) >= 1):
                continue
            seen.add(key)
            per_mech[mech] = per_mech.get(mech, 0) + 1
            per_anchor[anchor] = per_anchor.get(anchor, 0) + 1
            picked.append(x)
    picked.sort(key=lambda x: (-x["score"], -x["result"]["contribution"]))
    for i, x in enumerate(picked):
        x["rank"] = i + 1
        x["badge"] = "Rekomendasi utama" if i == 0 else "Cadangan" if i == 1 else None
        x["reason"] = reason_line(x)
    return picked


def reason_line(x):
    r_ = x["result"]
    u = r_["unit"]
    return (f"{r_['menarik']['label']} (hemat {u['discountPct']*100:.0f}%), {r_['health']['label'].lower()} dengan CM "
            f"{rp(u['cm'])} ({u['cmPct']*100:.1f}%), contribution skenario Target {rp(r_['contribution'])}.")
