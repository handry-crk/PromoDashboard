import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Search, ArrowUp, AlertTriangle, Check, Package } from "lucide-react";
import { api, rp, CH_LABEL, CH_ORDER } from "../lib";
import { Title, Loader, useToast, Empty } from "../ui";
import { NumInput } from "./Calculator";

const TONE = { rugi: "#B42F27", tipis: "#B8741A", cukup: "#6F6A5E", sehat: "#2F6B4A" };
const BG = { rugi: "bg-blush text-bata", tipis: "bg-[#F6E7C8] text-[#6F4A0E]", cukup: "bg-cream text-ink/75", sehat: "bg-[#DCE9DF] text-[#234F37]" };
const LABEL = { rugi: "Rugi", tipis: "Tipis", cukup: "Cukup", sehat: "Sehat" };
const pct = (v, d = 1) => (v == null ? "–" : `${(v * 100).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d })}%`);
const AREAS = [["bandung", "Bandung Raya"], ["jakarta", "Jabodetabek"]];

function StatusPill({ s }) { return s ? <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-bold whitespace-nowrap ${BG[s]}`}>{LABEL[s]}</span> : null; }

/* Garis harga: balik modal → minimum sehat → target, dengan penanda harga sekarang. */
function PriceLine({ r, mark }) {
  const pts = [r.breakeven, r.minHealthy, r.target, mark].filter(Boolean);
  if (pts.length < 2) return null;
  const lo = Math.min(...pts) * 0.9, hi = Math.max(...pts) * 1.08;
  const x = (v) => `${Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100))}%`;
  return (
    <div className="relative h-9 mt-1" aria-hidden>
      <div className="absolute top-3 inset-x-0 h-2.5 rounded-full overflow-hidden bg-cream">
        <div className="absolute inset-y-0 left-0 bg-[#E9B7AE]" style={{ width: x(r.breakeven) }} />
        <div className="absolute inset-y-0 bg-[#EBD3A1]" style={{ left: x(r.breakeven), width: `calc(${x(r.minHealthy)} - ${x(r.breakeven)})` }} />
        <div className="absolute inset-y-0 bg-[#D9D2C2]" style={{ left: x(r.minHealthy), width: `calc(${x(r.target)} - ${x(r.minHealthy)})` }} />
        <div className="absolute inset-y-0 right-0 bg-[#A9CDB6]" style={{ left: x(r.target) }} />
      </div>
      {mark && (
        <motion.div className="absolute top-0 -translate-x-1/2 flex flex-col items-center" initial={{ left: "0%" }} animate={{ left: x(mark) }} transition={{ type: "spring", stiffness: 120, damping: 18 }}>
          <div className="w-[3px] h-[26px] bg-ink rounded-full" />
        </motion.div>
      )}
    </div>
  );
}

function ChannelCard({ r, i, tried }) {
  const cur = r.current, t = r.trial;
  const mark = t?.price || cur?.price;
  const s = t?.status || r.status;
  return (
    <motion.article initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.05 }} className="card p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-extrabold truncate">{r.platformLabel}</div>
          <div className="text-[12px] text-ink/55">Batas CM {r.floorPct}% · target {r.targetPct}%{r.verified === false ? " · biaya belum divalidasi" : ""}</div>
        </div>
        <StatusPill s={s} />
      </div>
      {r.sold === false && <div className="mt-2 text-[12.5px] text-ink/60">Produk ini belum dijual di channel ini. Angka di bawah untuk bahan pertimbangan.</div>}
      {!r.target ? <div className="mt-2 text-[13px] text-bata font-semibold">Dengan biaya channel ini, harga berapa pun tidak mencapai target margin.</div> : (<>
        <div className="grid grid-cols-3 gap-1.5 mt-2.5 text-center">
          {[["Balik modal", r.breakeven, "text-bata"], ["Minimum sehat", r.minHealthy, "text-[#6F4A0E]"], ["Harga target", r.target, "text-[#234F37]"]].map(([l, v, c]) => (
            <div key={l} className="rounded-xl bg-cream/70 px-1.5 py-1.5 min-w-0">
              <div className="text-[11px] text-ink/55 font-semibold leading-tight">{l}</div>
              <div className={`font-extrabold num text-[15px] leading-tight mt-0.5 ${c}`}>{rp(v)}</div>
            </div>
          ))}
        </div>
        <PriceLine r={r} mark={mark} />
        {(t || cur) && (
          <div className="text-[13px] leading-snug">
            <b className="num">{rp((t || cur).price)}</b> <span className="text-ink/60">{t ? "(harga yang dicoba)" : "(harga sekarang)"}</span>: CM <b className="num" style={{ color: TONE[s] }}>{rp((t || cur).cm)} ({pct((t || cur).cmPct)})</b>
          </div>
        )}
        {!tried && cur && r.status === "rugi" && <Advice icon={AlertTriangle} tone="text-bata">Rugi {rp(-cur.cm)} per porsi. Naikkan minimal {rp(r.breakeven - cur.price)} untuk balik modal, atau {rp(r.gapToMin)} supaya sehat.</Advice>}
        {!tried && cur && r.status === "tipis" && <Advice icon={ArrowUp} tone="text-[#6F4A0E]">Di bawah batas sehat. Naikkan {rp(r.gapToMin)} ke {rp(r.minHealthy)}; jangan diberi promo di harga ini.</Advice>}
        {!tried && cur && r.status === "cukup" && <Advice icon={Check} tone="text-ink/70">Sudah sehat, tetapi ruang promo hanya {r.promoRoomPct.toLocaleString("id-ID")}%. Untuk leluasa promo, naikkan {rp(r.gapToTarget)} ke {rp(r.target)}.</Advice>}
        {!tried && cur && r.status === "sehat" && <Advice icon={Check} tone="text-[#234F37]">Harga sudah sehat. Ruang promo sampai {r.promoRoomPct.toLocaleString("id-ID")}% sebelum menyentuh batas minimum.</Advice>}
        {!cur && !t && <Advice icon={ArrowUp} tone="text-ink/70">Pasang minimal {rp(r.minHealthy)}; {rp(r.target)} bila ingin ada ruang promo{r.psych ? `, atau ${rp(r.psych)} sebagai harga yang enak dilihat` : ""}.</Advice>}
        {r.atTarget && (
          <details className="mt-2 text-[12.5px]">
            <summary className="cursor-pointer font-bold text-bata">Rincian di harga target</summary>
            <dl className="mt-1.5 grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 num">
              <dt className="text-ink/65">Harga jual</dt><dd className="font-bold text-right">{rp(r.atTarget.price)}</dd>
              {r.atTarget.feeLines.map((f) => <Row key={f.key} k={f.label} v={-f.amount} />)}
              {r.atTarget.costLines.map((f) => <Row key={f.key} k={f.label} v={-f.amount} />)}
              {!!r.atTarget.adsCost && <Row k="Ads" v={-r.atTarget.adsCost} />}
              <Row k="HPP" v={-r.atTarget.hpp} />
              <dt className="font-bold">CM per unit</dt><dd className="font-extrabold text-right text-[#234F37]">{rp(r.atTarget.cm)} ({pct(r.atTarget.cmPct)})</dd>
            </dl>
            {r.atTarget.unitsPerOrder !== 1 && <div className="text-ink/50 mt-1">Biaya per order dibagi {r.atTarget.unitsPerOrder.toLocaleString("id-ID")} porsi per order.</div>}
          </details>
        )}
      </>)}
    </motion.article>
  );
}
const Row = ({ k, v }) => <><dt className="text-ink/65">{k}</dt><dd className="text-right">{rp(v)}</dd></>;
const Advice = ({ icon: I, tone, children }) => <div className={`mt-2 flex gap-1.5 text-[13px] font-semibold ${tone}`}><I size={15} className="shrink-0 mt-0.5" /><span>{children}</span></div>;

export default function Pricing({ st }) {
  const toast = useToast();
  const profiles = st.profiles.filter((p) => p.channelType !== "event" && !p.label.endsWith("(lama)"));
  const [tab, setTab] = useState("semua");
  const [area, setArea] = useState("bandung");
  // semua produk
  const [plat, setPlat] = useState(profiles[0]?.id || "");
  const [ov, setOv] = useState(null);
  const [q, setQ] = useState("");
  const [only, setOnly] = useState("all");
  // simulasi
  const [pid, setPid] = useState("");
  const [hpp, setHpp] = useState("");
  const [tryPrice, setTryPrice] = useState("");
  const [targets, setTargets] = useState({});
  const [sim, setSim] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (tab !== "semua" || !plat) return;
    setOv(null);
    api("/pricing/overview", { method: "POST", body: { platformProfileId: plat, area, targets } }).then(setOv).catch((e) => toast(e.message, "bad"));
  }, [tab, plat, area, targets]); // eslint-disable-line

  useEffect(() => {
    if (tab !== "simulasi") return;
    const h = pid ? undefined : hpp;
    if (!pid && !(+hpp > 0)) { setSim(null); return; }
    setBusy(true);
    const t = setTimeout(() => {
      api("/pricing/check", { method: "POST", body: { productId: pid || undefined, hpp: h, area, tryPrice: tryPrice || undefined, targets } })
        .then(setSim).catch((e) => { setSim(null); toast(e.message, "bad"); }).finally(() => setBusy(false));
    }, 300);
    return () => clearTimeout(t);
  }, [tab, pid, hpp, tryPrice, area, targets]); // eslint-disable-line

  const rows = useMemo(() => (ov?.rows || []).filter((r) => (only === "all" || r.status === only) && (!q || r.nama.toLowerCase().includes(q.toLowerCase()))), [ov, q, only]);
  const openSim = (id) => { setPid(id); setHpp(""); setTryPrice(""); setTab("simulasi"); window.scrollTo({ top: 0 }); };
  const types = [...new Set(profiles.map((p) => p.channelType))];
  const defTarget = (ct) => ({ offline: st.settings.offlineMarginFloorPct, online_food: st.settings.onlineMarginFloorPct, marketplace: st.settings.marketplaceMarginFloorPct }[ct] ?? 20) + 10;

  return (
    <div className="space-y-4">
      <Title a="Harga jual" b="sehat" sub="Harga normal tanpa promo yang masih untung setelah HPP dan potongan platform"
        right={<a href="#/produk" className="btn-soft"><Package size={16} /><span className="hidden sm:inline">Produk & HPP</span></a>} />

      <div className="card p-3 space-y-3">
        <div className="flex gap-1 p-1 rounded-full bg-cream w-fit max-w-full">
          {[["semua", "Cek semua produk"], ["simulasi", "Simulasi harga"]].map(([k, l]) => (
            <button key={k} aria-pressed={tab === k} onClick={() => setTab(k)} className={`h-9 px-3.5 rounded-full text-[13px] font-bold ${tab === k ? "bg-ink text-cream" : "text-ink/65"}`}>{l}</button>
          ))}
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <div><span className="lbl">Area</span>
            <div className="grid grid-cols-2 gap-1.5">{AREAS.map(([k, l]) => <button key={k} aria-pressed={area === k} onClick={() => setArea(k)} className={`h-11 rounded-xl text-[13.5px] font-semibold border ${area === k ? "bg-bata text-cream border-bata" : "border-line bg-white/60"}`}>{l}</button>)}</div></div>
          <div><span className="lbl">Target CM <span className="font-normal text-ink/50">(batas minimum + 10 poin bila kosong)</span></span>
            <div className="grid grid-cols-3 gap-1.5">
              {types.map((ct) => <div key={ct}><NumInput suffix="%" placeholder={String(defTarget(ct))} value={targets[ct] ?? ""} onChange={(v) => setTargets((t) => { const n = { ...t }; if (v === "" || v == null) delete n[ct]; else n[ct] = v; return n; })} />
                <div className="text-[11px] text-ink/55 mt-0.5 truncate">{CH_LABEL[ct]}</div></div>)}
            </div></div>
        </div>
      </div>

      {tab === "semua" && (<>
        <div className="card p-3 space-y-2">
          <span className="lbl">Channel</span>
          <div className="space-y-1.5">
            {CH_ORDER.filter((g) => g !== "event").map((g) => {
              const list = profiles.filter((p) => p.channelType === g);
              if (!list.length) return null;
              return <div key={g} className="flex flex-wrap gap-1.5">{list.map((p) => <button key={p.id} aria-pressed={plat === p.id} onClick={() => setPlat(p.id)}
                className={`rounded-full px-3 min-h-[36px] text-[13px] font-semibold border ${plat === p.id ? "bg-bata text-cream border-bata" : "border-line bg-white/60 text-ink/75"}`}>{p.label}</button>)}</div>;
            })}
          </div>
        </div>
        {!ov ? <div className="card"><Loader text="Menghitung harga tiap produk…" /></div> : !ov.rows.length ? <Empty title="Belum ada produk di channel ini" text="Atur channel penjualan tiap produk di Produk & HPP." /> : (<>
          <section className="card p-4">
            <p className="text-[17px] md:text-[19px] font-bold leading-snug">
              Di {ov.platformLabel} ({AREAS.find((a) => a[0] === ov.area)[1]}), {ov.counts.sehat + ov.counts.cukup} dari {ov.rows.length} produk berharga sehat.
              {ov.counts.rugi > 0 && <> <span className="text-bata">{ov.counts.rugi} produk rugi</span> di harga sekarang.</>}
              {ov.counts.tipis > 0 && <> <span className="text-[#8A5A12]">{ov.counts.tipis} produk di bawah batas CM {ov.floorPct}%.</span></>}
            </p>
            <div className="text-[12.5px] text-ink/60 mt-1.5">Batas minimum CM {ov.floorPct}%, target {ov.targetPct}%.{ov.unitsPerOrder !== 1 ? ` Biaya per order dibagi ${ov.unitsPerOrder.toLocaleString("id-ID")} porsi.` : ""}{!ov.verified && ov.channelType !== "offline" ? " Biaya platform ini belum divalidasi, jadi angkanya masih asumsi." : ""}</div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {[["all", `Semua ${ov.rows.length}`], ...["rugi", "tipis", "cukup", "sehat"].filter((k) => ov.counts[k]).map((k) => [k, `${LABEL[k]} ${ov.counts[k]}`])].map(([k, l]) => (
                <button key={k} aria-pressed={only === k} onClick={() => setOnly(k)} className={`h-9 px-3.5 rounded-full text-[13px] font-semibold border ${only === k ? "bg-ink text-cream border-ink" : "border-line bg-paper text-ink/70"}`}>{l}</button>
              ))}
            </div>
            <label className="relative block mt-2"><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/45" />
              <input className="field !pl-9" placeholder="Cari produk" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari produk" /></label>
          </section>
          <div className="grid md:grid-cols-2 gap-2 items-start">
            {rows.map((r, i) => (
              <motion.button type="button" key={r.id} onClick={() => openSim(r.id)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 14) * 0.02 }}
                className="card p-3 text-left hover:border-bata/60" style={{ borderLeft: `5px solid ${TONE[r.status]}` }}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0"><div className="font-bold truncate">{r.nama}</div>
                    <div className="text-[12px] text-ink/60 num">HPP {rp(r.hpp)} · harga {rp(r.price)}</div></div>
                  <StatusPill s={r.status} />
                </div>
                <div className="grid grid-cols-3 gap-1.5 mt-2 text-[12.5px]">
                  <div className="rounded-lg bg-cream/70 px-2 py-1"><div className="text-[10.5px] text-ink/55 font-semibold">CM sekarang</div><div className="font-extrabold num" style={{ color: TONE[r.status] }}>{rp(r.cm)} <span className="font-semibold">({pct(r.cmPct, 0)})</span></div></div>
                  <div className="rounded-lg bg-cream/70 px-2 py-1"><div className="text-[10.5px] text-ink/55 font-semibold">Minimum sehat</div><div className="font-extrabold num">{rp(r.minHealthy)}</div></div>
                  <div className="rounded-lg bg-cream/70 px-2 py-1"><div className="text-[10.5px] text-ink/55 font-semibold">Harga target</div><div className="font-extrabold num">{rp(r.target)}</div></div>
                </div>
                <div className="text-[12.5px] mt-1.5 font-semibold" style={{ color: TONE[r.status] }}>
                  {r.status === "rugi" ? `Naikkan ${rp(r.gapToMin)} supaya sehat` : r.status === "tipis" ? `Naikkan ${rp(r.gapToMin)} ke batas sehat` : r.status === "cukup" ? `Ruang promo ${r.promoRoomPct.toLocaleString("id-ID")}%` : `Ruang promo ${r.promoRoomPct.toLocaleString("id-ID")}%`}
                </div>
              </motion.button>
            ))}
          </div>
          {!rows.length && <div className="card p-4 text-[14px] text-ink/60">Tidak ada produk yang cocok dengan filter.</div>}
        </>)}
      </>)}

      {tab === "simulasi" && (<>
        <div className="card p-3 grid sm:grid-cols-3 gap-3">
          <div className="sm:col-span-1"><label className="lbl" htmlFor="pr-prod">Produk</label>
            <select id="pr-prod" className="field" value={pid} onChange={(e) => { setPid(e.target.value); setTryPrice(""); }}>
              <option value="">Produk baru (isi HPP)</option>
              {[...new Set(st.products.map((p) => p.kategori))].map((k) => <optgroup key={k} label={String(k || "lainnya").replace(/_/g, " ")}>{st.products.filter((p) => p.kategori === k).map((p) => <option key={p.id} value={p.id}>{p.nama}</option>)}</optgroup>)}
            </select></div>
          <div><label className="lbl">HPP per porsi</label>
            {pid ? <div className="field bg-cream/60 num font-bold">{rp(st.products.find((p) => p.id === pid)?.hpp)}</div> : <NumInput prefix="Rp" placeholder="mis. 9.500" value={hpp} onChange={setHpp} />}</div>
          <div><label className="lbl">Coba harga jual <span className="font-normal text-ink/50">(opsional)</span></label><NumInput prefix="Rp" placeholder="mis. 20.000" value={tryPrice} onChange={setTryPrice} /></div>
        </div>
        {!sim && !busy && <div className="card p-5 text-[14.5px] text-ink/70">Pilih produk, atau isi HPP produk baru. Sistem menghitung harga balik modal, harga minimum sehat, dan harga target untuk tiap channel, lengkap dengan potongan platformnya.</div>}
        {busy && !sim && <div className="card"><Loader text="Menghitung harga sehat…" /></div>}
        {sim && (<>
          <section className="card p-4">
            <div className="font-extrabold text-[17px]">{sim.nama} · HPP {rp(sim.hpp)}</div>
            <div className="text-[12.5px] text-ink/60 mt-1">Balik modal = CM Rp0. Minimum sehat = CM di batas channel. Harga target = batas + {sim.targetExtra} poin (atau target yang Anda isi), supaya masih ada ruang promo. Garis hitam = {tryPrice ? "harga yang dicoba" : "harga sekarang"}.</div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[12px] font-semibold text-ink/65">
              {[["#E9B7AE", "Rugi"], ["#EBD3A1", "Tipis"], ["#D9D2C2", "Cukup"], ["#A9CDB6", "Sehat"]].map(([c, l]) => <span key={l} className="inline-flex items-center gap-1.5"><i className="w-3.5 h-2.5 rounded-sm inline-block" style={{ background: c }} />{l}</span>)}
            </div>
          </section>
          <div className="grid md:grid-cols-2 gap-2 items-start">{sim.rows.map((r, i) => <ChannelCard key={r.platformId} r={r} i={i} tried={!!tryPrice} />)}</div>
        </>)}
      </>)}
    </div>
  );
}
