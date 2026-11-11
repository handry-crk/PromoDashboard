import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Trash2, Save, Send, Copy, ChevronDown, Wand2, Info } from "lucide-react";
import { api, rp, rpShort, pc, num, debounce, CH_LABEL } from "../lib";
import { CimolBall, Badge, Waterfall, Quadrant, Loader, useToast, fireConfetti, MiniBall, CountUp } from "../ui";
import { go } from "../App";

const PACKAGE = ["bundle", "addon", "bxgy", "min_belanja_gratis"];
const ONLINE_ONLY = ["voucher_platform", "flash_sale", "ongkir"];

export const blankPromo = () => ({
  nama: "", objective: "aov", mechanism: "bundle", platformProfileId: "offline_kios", areas: ["bandung"],
  periodStart: new Date().toISOString().slice(0, 10), periodEnd: new Date(Date.now() + 13 * 864e5).toISOString().slice(0, 10),
  items: [{ productId: "mozza-b", qty: 1 }, { productId: "mozza-k", qty: 1 }], params: { packagePrice: 27000 },
  funding: { merchantPct: 100, platformPct: 0 }, programsJoined: [], overrides: {}, fixedCosts: [], variableCostPerUnit: 0,
  quotaPerOutletDay: "", capacityPerOutletDay: "", trackingReady: false, outlets: "", openRate: "", trxPerOutletDay: "",
  scenarioInputs: { pesimis: { takeRate: 7, trafficUplift: 2 }, target: { takeRate: 10, trafficUplift: 4 }, optimis: { takeRate: 14, trafficUplift: 7 } },
  strategic: { isStrategic: false, reason: "", maxInvestment: "" },
});

export function NumInput({ value, onChange, suffix, prefix, className = "", ...rest }) {
  const fmt = (v) => (v === "" || v == null || isNaN(v) ? "" : Number(v).toLocaleString("id-ID", { maximumFractionDigits: 2 }));
  const [text, setText] = useState(fmt(value));
  const [focus, setFocus] = useState(false);
  useEffect(() => { if (!focus) setText(fmt(value)); }, [value, focus]); // eslint-disable-line
  return (
    <div className="relative">
      {prefix && <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/50 text-[14px] font-semibold">{prefix}</span>}
      <input {...rest} inputMode="decimal" className={`field num ${prefix ? "pl-9" : ""} ${suffix ? "pr-10" : ""} ${className}`} value={text}
        onFocus={() => setFocus(true)} onBlur={() => { setFocus(false); setText(fmt(value)); }}
        onChange={(e) => {
          const t = e.target.value.replace(/[^\d.,]/g, "");
          setText(t);
          const raw = t.replace(/\./g, "").replace(",", ".");
          if (raw === "" ) { onChange(""); return; }
          if (raw.endsWith(".")) return; // waiting for decimals
          const n = Number(raw);
          if (!isNaN(n)) onChange(n);
        }} />
      {suffix && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-ink/50 text-[14px] font-semibold">{suffix}</span>}
    </div>
  );
}

function Section({ title, children, open: o = true, hint }) {
  const [open, setOpen] = useState(o);
  return (
    <section className="card">
      <button type="button" onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-4 py-3 text-left" aria-expanded={open}>
        <span className="font-extrabold text-[16px]">{title}{hint && <span className="ml-2 text-[12px] font-semibold text-ink/50">{hint}</span>}</span>
        <motion.span animate={{ rotate: open ? 180 : 0 }}><ChevronDown size={20} /></motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="px-4 pb-4 space-y-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function Chips({ options, value, onChange, multi }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(([k, l, disabled]) => {
        const on = multi ? value.includes(k) : value === k;
        return (
          <button type="button" key={k} disabled={disabled}
            onClick={() => onChange(multi ? (on ? value.filter((x) => x !== k) : [...value, k]) : k)}
            className={`relative rounded-full px-3.5 min-h-[38px] text-[14px] font-semibold border transition disabled:opacity-35 ${on ? "border-bata text-cream" : "border-line bg-white/60 text-ink/80 hover:border-bata/60"}`}>
            {on && <motion.span layoutId={multi ? undefined : `chip-${options.map((o) => o[0]).join("")}`} className="absolute inset-0 rounded-full bg-bata" transition={{ type: "spring", stiffness: 500, damping: 35 }} />}
            <span className="relative">{l}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function Calculator({ st, reload, promoId }) {
  const toast = useToast();
  const [promo, setPromo] = useState(null);
  const [saved, setSaved] = useState(null);
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const [calcBusy, setCalcBusy] = useState(false);
  const [area, setArea] = useState("bandung");
  const [tab, setTab] = useState("unit");
  const [cmp, setCmp] = useState(null);
  const [shake, setShake] = useState(0);
  const prevGate = useRef(null);
  const P = useMemo(() => Object.fromEntries(st.products.map((p) => [p.id, p])), [st.products]);
  const profiles = st.profiles;
  const prof = profiles.find((p) => p.id === promo?.platformProfileId);
  const canEdit = st.user.isAdmin || ["planner", "channel_pic", "head"].includes(st.user.perm);

  useEffect(() => {
    (async () => {
      if (promoId) {
        try {
          const p = await api(`/promos/${promoId}`);
          setSaved(p);
          setPromo({ ...blankPromo(), ...p });
          setArea((p.areas || ["bandung"])[0]);
        } catch (e) { toast(e.message, "bad"); go("/library"); }
      } else {
        let pre = null;
        try { pre = JSON.parse(sessionStorage.getItem("crk_prefill") || "null"); sessionStorage.removeItem("crk_prefill"); } catch { /* */ }
        const b = { ...blankPromo(), ...(pre || {}) };
        setPromo(b);
        setArea(b.areas[0]);
      }
    })();
  }, [promoId]); // eslint-disable-line

  const runCalc = useMemo(() => debounce(async (p) => {
    setCalcBusy(true);
    try {
      const r = await api("/calc", { method: "POST", body: { promo: p } });
      setRes(r.results); setError(null);
    } catch (e) { setError(e.message); }
    finally { setCalcBusy(false); }
  }, 260), []);

  useEffect(() => { if (promo) runCalc(clean(promo)); }, [promo, runCalc]);

  const o = res?.[area] || (res && Object.values(res)[0]);
  const status = o ? `${o.quadrant}|${o.gate.status}` : null;
  useEffect(() => {
    if (!o) return;
    const prev = prevGate.current;
    if (prev && prev !== status) {
      if (o.quadrant === "Star" && o.gate.status === "GO") fireConfetti();
      if (o.gate.status === "HOLD" && !prev.endsWith("HOLD")) setShake((s) => s + 1);
    }
    prevGate.current = status;
  }, [status]); // eslint-disable-line

  if (!promo) return <Loader text="Membuka promo…" />;

  const up = (patch) => setPromo((p) => ({ ...p, ...patch }));
  const multi = promo.areas.length > 1;
  const secondary = multi && area !== promo.areas[0];
  const effParams = { ...(promo.params || {}), ...((promo.areaParams || {})[area] || {}) };
  const upParam = (k, v) => setPromo((p) => {
    if (p.areas.length > 1 && area !== p.areas[0]) {
      const ap = p.areaParams || {};
      return { ...p, areaParams: { ...ap, [area]: { ...(ap[area] || {}), [k]: v } } };
    }
    return { ...p, params: { ...p.params, [k]: v } };
  });
  const upArea = (a, k, v) => setPromo((p) => {
    const ap = p.areaParams || {};
    return { ...p, areaParams: { ...ap, [a]: { ...(ap[a] || {}), [k]: v === "" ? undefined : v } } };
  });
  const ch = prof?.channelType || "offline";
  const sellable = st.products.filter((p) => prof && (p.channels || []).includes(prof.productChannel) && p.active !== false);
  const mechs = Object.entries(st.mechanisms).map(([k, l]) => [k, l, ch === "offline" && ONLINE_ONLY.includes(k)]);
  const freeRole = ["bxgy", "min_belanja_gratis"].includes(promo.mechanism);

  const save = async (submit) => {
    if (!promo.nama) { toast("Isi nama promo dulu.", "bad"); return; }
    try {
      const body = clean(promo);
      const r = saved ? await api(`/promos/${saved.id}`, { method: "PUT", body }) : await api("/promos", { method: "POST", body });
      if (submit) await api(`/promos/${r.id}/submit`, { method: "POST", body: {} });
      toast(submit ? "Promo diajukan ke Finance" : "Promo tersimpan");
      reload();
      go(`/promo/${r.id}`);
    } catch (e) { toast(e.message, "bad"); }
  };

  const copyText = () => {
    if (!o) return;
    const u = o.unit;
    const t = `*${promo.nama || "Promo"}* (${prof?.label}, ${area})\n${st.mechanisms[promo.mechanism]}: ${rp(u.listPrice)} → ${rp(u.customerPays)} (hemat ${pc(u.discountPct)})\n` +
      `CM ${rp(u.cm)} (${pc(u.cmPct)}) · Sehat ${o.health.label} · Margin ${o.margin.label} · Menarik ${o.menarik.label}\nGate: ${o.gate.status}\n${o.takeaway}`;
    navigator.clipboard?.writeText(t).then(() => toast("Ringkasan tersalin"), () => toast("Gagal menyalin", "bad"));
  };

  const loadCompare = async () => {
    setCmp("loading");
    try { setCmp(await api("/calc/compare-platforms", { method: "POST", body: { promo: clean(promo), area } })); }
    catch (e) { setCmp(null); toast(e.message, "bad"); }
  };

  const applyFix = (f) => {
    const patch = { ...f.patch };
    if (patch.segmentMix === null) patch.segmentMix = undefined;
    setPromo((p) => ({ ...p, ...patch }));
    toast(`Diterapkan: ${f.title}`);
  };

  return (
    <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] gap-5 items-start">
      {/* mobile sticky score strip */}
      <div className="lg:hidden sticky top-14 z-30 -mx-4 px-4 py-2 bg-cream/95 backdrop-blur border-b border-line">
        {o ? (
          <div className="flex items-center justify-between gap-2">
            <MiniBall title="Sehat" label={o.health.label} score={o.health.score} />
            <MiniBall title="Margin" label={o.margin.label} score={o.margin.score} />
            <MiniBall title="Menarik" label={o.menarik.label} score={o.menarik.score} />
            <Badge label={o.gate.status === "GO WITH CONDITION" ? "GO*" : o.gate.status} />
          </div>
        ) : <div className="text-[13px] text-ink/60">{error || "Menghitung…"}</div>}
      </div>

      {/* ---------------- form ---------------- */}
      <div className="space-y-3">
        <div className="flex items-end justify-between">
          <h2 className="title"><b>{saved ? "Edit" : "Hitung"}</b> promo {saved && <span className="text-[14px] text-ink/50 font-semibold">{saved.kode}</span>}</h2>
        </div>
        <Section title="Promo & channel">
          <div><label className="lbl" htmlFor="nama">Nama promo</label>
            <input id="nama" className="field" placeholder="mis. Mozza Duo Gerobak" value={promo.nama} onChange={(e) => up({ nama: e.target.value })} /></div>
          <div><span className="lbl">Objective</span>
            <Chips options={Object.entries(st.objectives).map(([k, l]) => [k, l])} value={promo.objective} onChange={(v) => up({ objective: v })} /></div>
          <div><span className="lbl">Platform / channel</span>
            {["offline", "online_food", "marketplace"].map((g) => (
              <div key={g} className="mb-2">
                <div className="text-[12px] text-ink/50 font-semibold mb-1">{CH_LABEL[g]}</div>
                <Chips options={profiles.filter((p) => p.channelType === g).map((p) => [p.id, p.label.split(" – ")[0]])} value={promo.platformProfileId}
                  onChange={(v) => {
                    const np = profiles.find((x) => x.id === v);
                    const okItems = promo.items.filter((i) => (P[i.productId]?.channels || []).includes(np.productChannel));
                    const fallback = st.products.find((x) => (x.channels || []).includes(np.productChannel));
                    up({ platformProfileId: v, programsJoined: [], items: okItems.length ? okItems : [{ productId: fallback?.id, qty: 1 }],
                      mechanism: np.channelType === "offline" && ONLINE_ONLY.includes(promo.mechanism) ? "diskon_persen" : promo.mechanism,
                      funding: np.channelType === "offline" ? { merchantPct: 100, platformPct: 0 } : promo.funding });
                  }} />
              </div>
            ))}
            {prof && !prof.verified && <div className="text-[12px] text-warn font-semibold flex items-center gap-1"><Info size={14} />Biaya {prof.label} belum divalidasi — angka masih asumsi.</div>}
          </div>
          <div><span className="lbl">Area</span>
            <Chips multi options={[["bandung", "Bandung Raya"], ["jakarta", "Jabodetabek"]]} value={promo.areas}
              onChange={(v) => { if (!v.length) return; up({ areas: v }); if (!v.includes(area)) setArea(v[0]); }} /></div>
        </Section>

        <Section title="Mekanisme & item">
          <Chips options={mechs} value={promo.mechanism} onChange={(v) => up({ mechanism: v, segmentMix: undefined })} />
          <div className="space-y-2 pt-1">
            {promo.items.map((it, i) => (
              <motion.div key={i} layout className="grid grid-cols-[1fr_70px_auto] gap-2 items-center">
                <select className="field" aria-label={`Item ${i + 1}`} value={it.productId} onChange={(e) => {
                  const items = [...promo.items]; items[i] = { ...it, productId: e.target.value }; up({ items, segmentMix: undefined });
                }}>
                  {sellable.map((p) => <option key={p.id} value={p.id}>{p.nama} · {rp(p.prices?.[area] ?? p.prices?.bandung)}{p.hindariGratis ? " · margin tipis" : ""}</option>)}
                </select>
                <NumInput aria-label="Qty" value={it.qty || 1} onChange={(v) => { const items = [...promo.items]; items[i] = { ...it, qty: v || 1 }; up({ items }); }} />
                <div className="flex gap-1">
                  {freeRole && (
                    <button type="button" onClick={() => { const items = [...promo.items]; items[i] = { ...it, role: it.role === "free" ? "paid" : "free" }; up({ items }); }}
                      className={`h-11 px-2.5 rounded-xl text-[12px] font-bold border ${it.role === "free" ? "bg-ok text-cream border-ok" : "border-line"}`}>{it.role === "free" ? "Gratis" : "Bayar"}</button>
                  )}
                  <button type="button" aria-label="Hapus item" disabled={promo.items.length < 2} onClick={() => up({ items: promo.items.filter((_, j) => j !== i), segmentMix: undefined })}
                    className="h-11 w-11 rounded-xl border border-line flex items-center justify-center disabled:opacity-30"><Trash2 size={16} /></button>
                </div>
              </motion.div>
            ))}
            <button type="button" className="btn-soft" onClick={() => up({ items: [...promo.items, { productId: sellable[0]?.id, qty: 1, role: freeRole ? "free" : "paid" }], segmentMix: undefined })}><Plus size={16} />Tambah item</button>
          </div>
          {multi && (
            <div className="flex flex-wrap items-center gap-2 pt-1 text-[13px] font-semibold">
              <span className="text-ink/60">Harga promo untuk:</span>
              {promo.areas.map((a) => (
                <button type="button" key={a} onClick={() => setArea(a)} className={`px-3 min-h-[34px] rounded-full border ${area === a ? "bg-ink text-cream border-ink" : "border-line"}`}>
                  {a === "bandung" ? "Bandung Raya" : "Jabodetabek"}</button>
              ))}
            </div>
          )}
          <MechParams promo={{ ...promo, params: effParams }} upParam={upParam} st={st} sellable={sellable} />
          {secondary && <p className="text-[12px] text-ink/55">Kosongkan untuk memakai angka {promo.areas[0] === "bandung" ? "Bandung Raya" : "Jabodetabek"}.</p>}
        </Section>

        {ch !== "offline" && (
          <Section title="Potongan platform" hint={prof?.label}>
            <div>
              <div className="flex justify-between text-[13px] font-semibold mb-1"><span>Diskon ditanggung kita</span><span className="num">{promo.funding?.merchantPct ?? 100}% : {100 - (promo.funding?.merchantPct ?? 100)}% platform</span></div>
              <input type="range" min="0" max="100" step="5" className="w-full accent-bata" aria-label="Porsi diskon ditanggung merchant"
                value={promo.funding?.merchantPct ?? 100} onChange={(e) => up({ funding: { merchantPct: +e.target.value, platformPct: 100 - e.target.value } })} />
            </div>
            {!!prof?.programs?.length && <div><span className="lbl">Ikut program platform</span>
              <Chips multi options={prof.programs.map((g) => [g.programKey, g.label])} value={promo.programsJoined || []}
                onChange={(v) => {
                  const added = v.find((k) => !(promo.programsJoined || []).includes(k));
                  const pg = prof.programs.find((g) => g.programKey === added);
                  up({ programsJoined: v, ...(pg?.defaultPlatformFundingPct ? { funding: { merchantPct: 100 - pg.defaultPlatformFundingPct, platformPct: pg.defaultPlatformFundingPct } } : {}) });
                }} /></div>}
            <div className="grid grid-cols-2 gap-3">
              <div><label className="lbl">Porsi per order</label><NumInput value={promo.overrides?.avgUnitsPerOrder ?? ""} placeholder={String(prof?.avgUnitsPerOrder ?? 1)} onChange={(v) => up({ overrides: { ...promo.overrides, avgUnitsPerOrder: v === "" ? undefined : v } })} /></div>
              <div><label className="lbl">Packaging per order</label><NumInput prefix="Rp" value={promo.overrides?.extraPackagingPerOrder ?? ""} placeholder={num(prof?.costs?.extraPackagingPerOrder)} onChange={(v) => up({ overrides: { ...promo.overrides, extraPackagingPerOrder: v === "" ? undefined : v } })} /></div>
              <div><label className="lbl">Ads (ROAS target)</label><NumInput value={promo.overrides?.ads?.roas ?? ""} placeholder={prof?.ads?.model === "roas" ? String(prof.ads.roas) : "tanpa ads"}
                onChange={(v) => up({ overrides: { ...promo.overrides, ads: v === "" ? undefined : { model: "roas", roas: v } } })} /></div>
            </div>
            <p className="text-[12px] text-ink/55">Komisi, biaya per order, PPN, dan tarif program diatur di halaman <a className="underline text-bata" href="#/platform">Platform & Biaya</a>.</p>
          </Section>
        )}

        <Section title="Periode, outlet & kapasitas" open={false}>
          <div className="grid grid-cols-2 gap-3">
            {multi && <p className="col-span-2 text-[12px] text-ink/55">Biaya tetap dibagi ke tiap area sesuai jumlah outlet.</p>}
            <div><label className="lbl">Mulai</label><input type="date" className="field" value={promo.periodStart || ""} onChange={(e) => up({ periodStart: e.target.value })} /></div>
            <div><label className="lbl">Selesai</label><input type="date" className="field" value={promo.periodEnd || ""} onChange={(e) => up({ periodEnd: e.target.value })} /></div>
            {multi ? promo.areas.map((a) => (
              <div key={a} className="col-span-2 grid grid-cols-2 gap-3">
                <div><label className="lbl">Outlet {a === "bandung" ? "Bandung Raya" : "Jabodetabek"}</label>
                  <NumInput value={(promo.areaParams || {})[a]?.outlets ?? ""} placeholder="dari baseline" onChange={(v) => upArea(a, "outlets", v)} /></div>
                <div><label className="lbl">Open rate {a === "bandung" ? "Bdg" : "Jkt"}</label>
                  <NumInput suffix="%" value={(promo.areaParams || {})[a]?.openRate ?? ""} placeholder="baseline" onChange={(v) => upArea(a, "openRate", v)} /></div>
              </div>
            )) : (<>
              <div><label className="lbl">Jumlah outlet/toko</label><NumInput value={promo.outlets} placeholder="dari baseline" onChange={(v) => up({ outlets: v })} /></div>
              <div><label className="lbl">Open rate</label><NumInput suffix="%" value={promo.openRate} placeholder="100" onChange={(v) => up({ openRate: v })} /></div>
            </>)}
            <div><label className="lbl">Transaksi/outlet/hari</label><NumInput value={promo.trxPerOutletDay} placeholder="dari baseline" onChange={(v) => up({ trxPerOutletDay: v })} /></div>
            <div><label className="lbl">Biaya variabel/unit</label><NumInput prefix="Rp" value={promo.variableCostPerUnit} onChange={(v) => up({ variableCostPerUnit: v })} /></div>
            <div><label className="lbl">Kuota/outlet/hari</label><NumInput value={promo.quotaPerOutletDay} onChange={(v) => up({ quotaPerOutletDay: v })} /></div>
            <div><label className="lbl">Kapasitas/outlet/hari</label><NumInput value={promo.capacityPerOutletDay} onChange={(v) => up({ capacityPerOutletDay: v })} /></div>
          </div>
          <label className="flex items-center gap-2 text-[14px] font-semibold min-h-[44px]">
            <input type="checkbox" className="w-5 h-5 accent-bata" checked={!!promo.trackingReady} onChange={(e) => up({ trackingReady: e.target.checked })} />SKU / kode voucher sudah siap di POS
          </label>
          <div>
            <span className="lbl">Biaya tetap (POSM, ads, KOL)</span>
            {(promo.fixedCosts || []).map((f, i) => (
              <div key={i} className="grid grid-cols-[1fr_130px_auto] gap-2 mb-2">
                <input className="field" value={f.label} placeholder="Keterangan" onChange={(e) => { const x = [...promo.fixedCosts]; x[i] = { ...f, label: e.target.value }; up({ fixedCosts: x }); }} />
                <NumInput prefix="Rp" value={f.amount} onChange={(v) => { const x = [...promo.fixedCosts]; x[i] = { ...f, amount: v }; up({ fixedCosts: x }); }} />
                <button type="button" aria-label="Hapus biaya" className="h-11 w-11 rounded-xl border border-line flex items-center justify-center" onClick={() => up({ fixedCosts: promo.fixedCosts.filter((_, j) => j !== i) })}><Trash2 size={16} /></button>
              </div>
            ))}
            <button type="button" className="btn-soft" onClick={() => up({ fixedCosts: [...(promo.fixedCosts || []), { label: "", amount: 0 }] })}><Plus size={16} />Tambah biaya</button>
          </div>
        </Section>

        <Section title="Asumsi skenario" open={false}>
          <div className="grid grid-cols-3 gap-2 text-[13px]">
            {["pesimis", "target", "optimis"].map((k) => (
              <div key={k} className="space-y-2">
                <div className="font-extrabold capitalize">{k}</div>
                <div><label className="lbl">Take rate</label><NumInput suffix="%" value={promo.scenarioInputs?.[k]?.takeRate} onChange={(v) => up({ scenarioInputs: { ...promo.scenarioInputs, [k]: { ...promo.scenarioInputs[k], takeRate: v } } })} /></div>
                <div><label className="lbl">Traffic uplift</label><NumInput suffix="%" value={promo.scenarioInputs?.[k]?.trafficUplift} onChange={(v) => up({ scenarioInputs: { ...promo.scenarioInputs, [k]: { ...promo.scenarioInputs[k], trafficUplift: v } } })} /></div>
              </div>
            ))}
          </div>
        </Section>

        {PACKAGE.includes(promo.mechanism) && o?.incremental && (
          <Section title="Siapa yang beli paket ini?" open={false} hint="segment mix">
            <p className="text-[13px] text-ink/60">Kalau tidak ada promo, pembeli paket ini sebenarnya akan beli apa? Ini menentukan tambahan revenue dan CM yang benar-benar baru.</p>
            {(promo.segmentMix || o.incremental.segments.map((s, i) => ({ label: s.label, share: s.share, counterfactual: s.counterfactual }))).map((sg, i, arr) => (
              <div key={i} className="grid grid-cols-[1fr_90px] gap-2 items-center">
                <div className="text-[14px] font-semibold">{sg.label}</div>
                <NumInput suffix="%" value={sg.share} onChange={(v) => { const x = arr.map((a) => ({ ...a })); x[i].share = v; up({ segmentMix: x }); }} />
              </div>
            ))}
          </Section>
        )}

        <Section title="Pengecualian strategis" open={false}>
          <label className="flex items-center gap-2 text-[14px] font-semibold min-h-[44px]">
            <input type="checkbox" className="w-5 h-5 accent-bata" checked={!!promo.strategic?.isStrategic} onChange={(e) => up({ strategic: { ...promo.strategic, isStrategic: e.target.checked } })} />Promo ini sengaja rugi untuk tujuan strategis
          </label>
          {promo.strategic?.isStrategic && (<>
            <textarea className="field min-h-[80px]" placeholder="Alasan tertulis, mis. trial produk baru dengan target repeat 30D ≥ 25%" value={promo.strategic.reason} onChange={(e) => up({ strategic: { ...promo.strategic, reason: e.target.value } })} />
            <div><label className="lbl">Batas investasi</label><NumInput prefix="Rp" value={promo.strategic.maxInvestment} onChange={(v) => up({ strategic: { ...promo.strategic, maxInvestment: v } })} /></div>
          </>)}
        </Section>

        {canEdit && (
          <div className="flex flex-wrap gap-2 pt-1 pb-4">
            <button className="btn-primary" onClick={() => save(false)}><Save size={18} />{saved ? "Simpan perubahan" : "Simpan draft"}</button>
            <button className="btn-ghost" onClick={() => save(true)} disabled={o?.gate.status === "HOLD" && !promo.strategic?.isStrategic}><Send size={18} />Ajukan review</button>
            <button className="btn-soft" onClick={copyText}><Copy size={18} />Copy ringkasan</button>
          </div>
        )}
      </div>

      {/* ---------------- results ---------------- */}
      <div className="lg:sticky lg:top-[72px] space-y-3">
        {promo.areas.length > 1 && (
          <Chips options={promo.areas.map((a) => [a, a === "bandung" ? "Bandung Raya" : "Jabodetabek"])} value={area} onChange={setArea} />
        )}
        {error && <div className="card p-4 border-bata text-bata font-semibold">{error}</div>}
        {!o && !error && <Loader />}
        {o && (
          <>
            <motion.section key={`s${shake}`} className={`card p-4 relative overflow-hidden ${shake ? "wobble" : ""}`}>
              <div className="absolute right-3 top-3 flex items-center gap-2">
                {calcBusy && <motion.span className="w-2.5 h-2.5 rounded-full bg-bata" animate={{ opacity: [1, 0.2, 1] }} transition={{ duration: 0.6, repeat: Infinity }} />}
              </div>
              <div className="grid grid-cols-3 gap-1">
                <CimolBall title="Sehat" score={o.health.score} label={o.health.label} hint="Apakah promo sehat secara bisnis" />
                <CimolBall title="Margin" score={o.margin.score} label={o.margin.label} hint="CM setelah semua potongan" />
                <CimolBall title="Menarik" score={o.menarik.score} label={o.menarik.label} hint="Daya tarik untuk customer" />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Badge big label={o.gate.status} />
                <span className="pill">{o.quadrant}</span>
                {o.menarik.calibratedFrom && <span className="pill">Dikalibrasi dari {o.menarik.calibratedFrom} promo</span>}
              </div>
              <p className="mt-3 text-[15px] leading-relaxed">{o.takeaway}</p>
              {!!o.gate.conditions.length && (
                <ul className="mt-2 space-y-1 text-[13px] text-ink/75">
                  {o.gate.conditions.map((c, i) => <li key={i} className="flex gap-2"><span className="text-warn">●</span>{c}</li>)}
                </ul>
              )}
            </motion.section>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <KeyNum label="Customer bayar" v={o.unit.customerPays} sub={`hemat ${rp(o.unit.discountTotal)} (${pc(o.unit.discountPct, 0)})`} />
              <KeyNum label="CM per unit" v={o.unit.cm} sub={pc(o.unit.cmPct)} tone={o.unit.cm > 0 ? "#2F6B4A" : "#B42F27"} />
              <KeyNum label={ch === "offline" ? "Harga min. sehat" : "Potongan platform"} v={ch === "offline" ? o.minHealthyPrice?.rounded : null}
                text={ch === "offline" ? null : pc(o.unit.effectiveTakeRate)} sub={ch === "offline" ? (o.minHealthyPrice ? `tepat ${rp(o.minHealthyPrice.exact)}` : "–") : rp(o.unit.platformFees + o.unit.adsCost)} />
              <KeyNum label="Contribution Target" v={o.scenarios.target.contribution} sub={`ROI ${o.scenarios.target.roi == null ? "–" : pc(o.scenarios.target.roi, 0)}`} tone={o.scenarios.target.contribution > 0 ? "#2F6B4A" : "#B42F27"} />
            </div>

            {!!o.fixes?.length && (
              <section className="card p-4">
                <div className="font-extrabold mb-2 flex items-center gap-2"><Wand2 size={18} className="text-bata" />Saran perbaikan</div>
                <div className="space-y-2">
                  {o.fixes.map((f, i) => (
                    <motion.button key={f.title} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                      onClick={() => applyFix(f)} className="w-full text-left rounded-2xl bg-blush hover:bg-tint px-3 py-2.5">
                      <div className="font-bold text-bata">{f.title}</div><div className="text-[13px] text-ink/70">{f.detail}</div>
                    </motion.button>
                  ))}
                </div>
              </section>
            )}

            <section className="card p-4">
              <div className="flex gap-1 mb-3 overflow-x-auto">
                {[["unit", "Unit economics"], ["scenario", "Skenario"], ["score", "Rincian skor"], ["platform", "Per platform"]].map(([k, l]) => (
                  <button key={k} onClick={() => { setTab(k); if (k === "platform") loadCompare(); }}
                    className={`relative shrink-0 px-3 h-9 rounded-full text-[13px] font-bold ${tab === k ? "text-cream" : "text-ink/70"}`}>
                    {tab === k && <motion.span layoutId="rtab" className="absolute inset-0 rounded-full bg-ink" />}<span className="relative">{l}</span>
                  </button>
                ))}
              </div>
              <AnimatePresence mode="wait">
                <motion.div key={tab} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: 0.15 }}>
                  {tab === "unit" && <UnitTab o={o} ch={ch} />}
                  {tab === "scenario" && <ScenarioTab o={o} />}
                  {tab === "score" && <ScoreTab o={o} />}
                  {tab === "platform" && <PlatformTab cmp={cmp} />}
                </motion.div>
              </AnimatePresence>
            </section>
          </>
        )}
      </div>
    </div>
  );
}


const SERVER_ONLY = ["results", "summary", "timeline", "comments", "targets", "stale", "effectiveStatus", "waitingActual", "actual",
  "status", "kode", "createdBy", "createdById", "createdAt", "updatedAt", "priceVersion", "profileVersion", "rejectNote", "id"];
function clean(p) {
  const out = { ...p };
  SERVER_ONLY.forEach((k) => delete out[k]);
  ["outlets", "openRate", "trxPerOutletDay", "quotaPerOutletDay", "capacityPerOutletDay"].forEach((k) => { if (out[k] === "") delete out[k]; });
  if (out.segmentMix === undefined) delete out.segmentMix;
  if (out.segmentMix && !out.segmentMix.every((s) => s.counterfactual)) delete out.segmentMix;
  return out;
}

function KeyNum({ label, v, sub, tone, text }) {
  return (
    <div className="card p-3">
      <div className="text-[12px] font-semibold text-ink/60">{label}</div>
      <div className="text-[18px] font-extrabold leading-tight mt-0.5 break-words" style={{ color: tone || "#212121" }}>
        {text ?? (v == null ? "–" : <CountUp value={v} format={(x) => (Math.abs(x) >= 1e6 ? rpShort(x) : rp(x))} />)}
      </div>
      <div className="text-[12px] text-ink/55 num">{sub}</div>
    </div>
  );
}

function UnitTab({ o, ch }) {
  const u = o.unit;
  return (
    <div className="space-y-4">
      <Waterfall unit={u} />
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
        <Row k="GM sebelum platform" v={pc(u.gmPct)} />
        <Row k="CM normal (tanpa promo)" v={rp(u.normalCM)} />
        <Row k="Margin yang diberikan" v={pc(u.discountDepth, 0)} />
        {u.breakevenUplift != null && <Row k="Breakeven uplift" v={isFinite(u.breakevenUplift) ? `+${pc(u.breakevenUplift)}` : "tidak tercapai"} />}
        {u.cmVsBaseline != null && <Row k="CM vs transaksi rata-rata" v={pc(u.cmVsBaseline, 0)} />}
        {u.cmVsOffline != null && <Row k="CM vs jual di outlet" v={pc(u.cmVsOffline, 0)} />}
        {ch !== "offline" && <Row k="Harga outlet" v={rp(u.outletPrice)} />}
        {o.minHealthyPrice && <Row k="Harga minimum sehat" v={`${rp(o.minHealthyPrice.rounded)}`} />}
        {o.incremental && <Row k="Tambahan revenue/unit" v={rp(o.incremental.incRevenuePerUnit)} />}
        {o.incremental && <Row k="Tambahan CM/unit" v={rp(o.incremental.incCmPerUnit)} />}
      </div>
      {!!u.customerFeeLines?.length && <div className="text-[12px] text-ink/60">Dibayar customer: {u.customerFeeLines.map((f) => `${f.label} ${rp(f.amount)}`).join(", ")}</div>}
    </div>
  );
}
const Row = ({ k, v }) => (<><div className="text-ink/65">{k}</div><div className="text-right font-semibold num">{v}</div></>);

function ScenarioTab({ o }) {
  const s = o.scenarios;
  const rows = [
    ["Take rate / traffic", (x) => `${x.takeRate}% / +${x.trafficUplift}%`],
    ["Unit/outlet/hari", (x) => x.unitsPerOutletDay.toLocaleString("id-ID")],
    ["Total unit", (x) => num(x.totalUnits)],
    ["Revenue/outlet/hari", (x) => `${rp(x.revenuePerOutletDay)} (${x.revenueChangePct >= 0 ? "+" : ""}${pc(x.revenueChangePct)})`],
    ["Tambahan revenue", (x) => rp(x.incRevenue)],
    ["Tambahan CM", (x) => rp(x.incCM)],
    ["Diskon ditanggung kita", (x) => rp(x.merchantDiscount)],
    ["Subsidi platform", (x) => rp(x.platformSubsidy)],
    ["Total potongan platform", (x) => rp(x.platformFees)],
    ["Biaya tetap", (x) => rp(x.fixedCosts)],
    ["Contribution", (x) => rp(x.contribution)],
    ["ROI", (x) => (x.roi == null ? "–" : pc(x.roi, 0))],
  ];
  const max = Math.max(...["pesimis", "target", "optimis"].map((k) => Math.abs(s[k].contribution)), 1);
  return (
    <div>
      <div className="grid grid-cols-3 gap-3 mb-4 items-end h-28">
        {["pesimis", "target", "optimis"].map((k, i) => (
          <div key={k} className="flex flex-col items-center justify-end h-full">
            <div className="text-[12px] font-bold num mb-1" style={{ color: s[k].contribution >= 0 ? "#2F6B4A" : "#B42F27" }}>{rp(s[k].contribution)}</div>
            <motion.div className="w-full max-w-[70px] rounded-t-2xl" style={{ background: s[k].contribution >= 0 ? "#2F6B4A" : "#B42F27", opacity: k === "target" ? 1 : 0.55 }}
              initial={{ height: 0 }} animate={{ height: `${Math.max(6, (Math.abs(s[k].contribution) / max) * 70)}px` }} transition={{ delay: i * 0.1, type: "spring", stiffness: 120, damping: 14 }} />
            <div className="text-[12px] font-bold capitalize mt-1">{k}</div>
          </div>
        ))}
      </div>
      <div className="scroll-x -mx-1">
        <table className="w-full min-w-[420px] text-[13px]">
          <thead><tr><th className="th rounded-tl-xl">{num(s.meta.outletDays)} outlet-hari</th><th className="th">Pesimis</th><th className="th">Target</th><th className="th rounded-tr-xl">Optimis</th></tr></thead>
          <tbody>{rows.map(([l, f]) => (
            <tr key={l}><td className="td text-ink/70">{l}</td>{["pesimis", "target", "optimis"].map((k) => <td key={k} className={`td num text-right ${k === "target" ? "font-bold" : ""}`}>{f(s[k])}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function ScoreTab({ o }) {
  const block = (title, comps) => (
    <div className="mb-4">
      <div className="font-extrabold mb-2">{title}</div>
      <div className="space-y-2">
        {comps.map((c) => (
          <div key={c.key} className="grid grid-cols-[minmax(0,1fr)_80px] gap-2 items-center">
            <div><div className="text-[13px] font-semibold">{c.label} <span className="text-ink/45 font-normal">· bobot {c.weight}</span></div><div className="text-[12px] text-ink/60">{c.note}</div></div>
            <div className="h-2.5 rounded-full bg-cream overflow-hidden">
              <motion.div className="h-full rounded-full" style={{ background: c.score >= 80 ? "#2F6B4A" : c.score >= 50 ? "#B8741A" : "#B42F27" }}
                initial={{ width: 0 }} animate={{ width: `${Math.max(c.score, 4)}%` }} transition={{ type: "spring", stiffness: 90, damping: 16 }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
  return (
    <div>
      {block(`Sehat · ${o.health.score}`, o.health.components)}
      <div className="mb-4 text-[13px]"><span className="font-extrabold">Margin · {o.margin.score}</span> — CM {pc(o.margin.cmPct)} setelah semua potongan (GM sebelum platform {pc(o.margin.gmBeforePlatform)}).</div>
      {block(`Menarik · ${o.menarik.score}`, o.menarik.components)}
      <div className="max-w-sm"><Quadrant current={{ m: o.margin.score, a: o.menarik.score }} /></div>
    </div>
  );
}

function PlatformTab({ cmp }) {
  if (!cmp || cmp === "loading") return <Loader text="Membandingkan semua platform…" />;
  const max = Math.max(...cmp.rows.map((r) => Math.abs(r.cm)), 1);
  return (
    <div className="space-y-2">
      {cmp.rows.map((r, i) => (
        <motion.div key={r.platformId} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
          className={`rounded-2xl px-3 py-2.5 ${r.bestMargin ? "bg-ok/10 ring-1 ring-ok" : "bg-cream/60"}`}>
          <div className="flex items-center justify-between gap-2">
            <div className="font-bold text-[14px]">{r.label}{!r.verified && <span className="text-warn text-[11px] ml-1">belum divalidasi</span>}</div>
            <div className="flex gap-1">{r.bestMargin && <span className="pill border-ok text-ok">Margin terbaik</span>}{r.bestAttract && <span className="pill">Paling menarik</span>}</div>
          </div>
          <div className="mt-1.5 h-3 rounded-full bg-paper overflow-hidden">
            <motion.div className="h-full rounded-full" style={{ background: r.cm > 0 ? "#2F6B4A" : "#B42F27" }} initial={{ width: 0 }}
              animate={{ width: `${(Math.abs(r.cm) / max) * 100}%` }} transition={{ delay: 0.1 + i * 0.05 }} />
          </div>
          <div className="flex flex-wrap justify-between text-[12px] mt-1 text-ink/70 num gap-x-3">
            <span>Customer bayar {rp(r.customerPays)}</span><span>Potongan {r.effectiveTakeRate == null ? "0%" : pc(r.effectiveTakeRate)}</span>
            <span className="font-bold text-ink">CM {rp(r.cm)} ({pc(r.cmPct)})</span><span>{r.gate}</span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

function MechParams({ promo, upParam, st, sellable }) {
  const p = promo.params || {};
  const m = promo.mechanism;
  const f = (k, label, props = {}) => (
    <div key={k}><label className="lbl">{label}</label><NumInput value={p[k] ?? ""} onChange={(v) => upParam(k, v)} {...props} /></div>
  );
  const grid = (...els) => <div className="grid grid-cols-2 gap-3 pt-1">{els}</div>;
  switch (m) {
    case "diskon_persen": return grid(f("discountPct", "Diskon", { suffix: "%" }));
    case "happy_hour": return grid(f("discountPct", "Diskon", { suffix: "%" }), f("hourShare", "Porsi trx di jam itu", { suffix: "%" }));
    case "potongan_rp": return grid(f("offRp", "Potongan", { prefix: "Rp" }));
    case "harga_spesial": case "flash_sale": return grid(f("specialPrice", "Harga spesial", { prefix: "Rp" }));
    case "bundle": return grid(f("packagePrice", "Harga paket", { prefix: "Rp" }));
    case "addon": return grid(f("addonPrice", "Harga tebus item ke-2", { prefix: "Rp" }));
    case "voucher_platform": return grid(f("voucherPct", "Voucher", { suffix: "%" }), f("voucherCap", "Maks. potongan", { prefix: "Rp" }));
    case "ongkir": return grid(f("merchantOngkirRp", "Subsidi ongkir dari kita/order", { prefix: "Rp" }));
    case "stamp_card": return (
      <div className="grid grid-cols-2 gap-3 pt-1">
        {f("n", "Beli N gratis 1")}{f("completionRate", "Yang menyelesaikan kartu", { suffix: "%" })}
        <div className="col-span-2"><label className="lbl">Item gratis</label>
          <select className="field" value={p.freeProductId || ""} onChange={(e) => upParam("freeProductId", e.target.value)}>
            <option value="">Sama dengan item pertama</option>{sellable.map((x) => <option key={x.id} value={x.id}>{x.nama}</option>)}
          </select></div>
      </div>);
    case "voucher_next_visit": return grid(f("voucherRp", "Nilai voucher", { prefix: "Rp" }), f("redemptionRate", "Redemption", { suffix: "%" }));
    case "bxgy": case "min_belanja_gratis":
      return <p className="text-[13px] text-ink/60">Tandai item yang diberikan gratis dengan tombol <b>Gratis</b>.</p>;
    default: return null;
  }
}
