import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowUpRight, Save, Play, TriangleAlert } from "lucide-react";
import { api, rp, pc, fmtDate, CH_LABEL, CH_ORDER } from "../lib";
import { Title, MiniBall, Badge, Loader, useToast, fireConfetti, CountUp, Sheet } from "../ui";
import { NumInput } from "./Calculator";
import { go } from "../App";

export default function Recommend({ st, reload }) {
  const toast = useToast();
  const [f, setF] = useState({ platformProfileIds: ["offline_gerobak"], objective: "aov", objective2: "", area: "bandung", maxDiscountPct: 20,
    allowCofunding: false, maxPlatformPct: 50, budget: "", programsAllowed: [], outlets: "", trxPerOutletDay: "" });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const selProfs = f.platformProfileIds.map((id) => st.profiles.find((p) => p.id === id)).filter(Boolean);
  const prof = selProfs.length === 1 ? selProfs[0] : null;
  const anyOnline = selProfs.some((p) => p.channelType !== "offline" && p.channelType !== "event");
  const togglePlat = (id) => setF((cur) => {
    const on = cur.platformProfileIds.includes(id);
    return { ...cur, platformProfileIds: on ? cur.platformProfileIds.filter((x) => x !== id) : [...cur.platformProfileIds, id], programsAllowed: [] };
  });
  const [emptyFor, setEmptyFor] = useState([]);
  const set = (patch) => setF({ ...f, ...patch });

  const run = async () => {
    if (!selProfs.length) { toast("Pilih minimal satu platform / channel.", "bad"); return; }
    setBusy(true); setRes(null); setEmptyFor([]);
    try {
      const { platformProfileIds, ...rest } = f;
      ["budget", "outlets", "trxPerOutletDay", "objective2"].forEach((k) => { if (rest[k] === "") delete rest[k]; });
      const t0 = Date.now();
      const all = [], none = [];
      const many = selProfs.length > 1;
      for (const p of selProfs) {
        const r = await api("/recommend", { method: "POST", body: { ...rest, platformProfileId: p.id, programsAllowed: many ? [] : rest.programsAllowed,
          allowCofunding: rest.allowCofunding && p.channelType !== "offline" } });
        const list = many ? r.results.slice(0, 3) : r.results;
        if (!list.length) none.push(p.label);
        list.forEach((x, k) => all.push({ ...x, _pid: p.id, _label: p.label, _head: many && k === 0, _top: k === 0 }));
      }
      await new Promise((ok) => setTimeout(ok, Math.max(0, 900 - (Date.now() - t0))));
      setRes(all); setEmptyFor(none);
      if (all.length) fireConfetti();
    } catch (e) { toast(e.message, "bad"); } finally { setBusy(false); }
  };

  const open = (x) => {
    sessionStorage.setItem("crk_prefill", JSON.stringify({ ...x.promo, nama: x.promo.nama }));
    go("/hitung");
  };
  const isHead = st.user.isAdmin || st.user.perm === "head";
  const todayStr = (() => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); })();
  const [go1, setGo1] = useState(null); // { x, startDate, days }
  const [pre, setPre] = useState(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    if (!go1) { setPre(null); return; }
    if (!go1.days || !go1.startDate) return;
    let live = true;
    const t = setTimeout(() => {
      api("/promos/run-now", { method: "POST", body: { promo: go1.x.promo, startDate: go1.startDate, days: go1.days, dryRun: true } })
        .then((r) => live && setPre(r)).catch((e) => live && setPre({ blocked: e.message, warnings: [] }));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [go1]);
  const runNow = async () => {
    setRunning(true);
    try {
      const r = await api("/promos/run-now", { method: "POST", body: { promo: go1.x.promo, startDate: go1.startDate, days: go1.days } });
      fireConfetti();
      toast(r.resultStatus === "running" ? "Promo langsung Running" : r.resultStatus === "approved" ? `Promo disetujui, mulai ${fmtDate(r.periodStart)}` : "Promo diajukan ke Finance");
      setGo1(null); reload(); go(`/promo/${r.promo.id}`);
    } catch (e) { toast(e.message, "bad"); } finally { setRunning(false); }
  };
  const saveDraft = async (x) => {
    try { const p = await api("/promos", { method: "POST", body: x.promo }); toast("Tersimpan sebagai draft"); reload(); go(`/promo/${p.id}`); }
    catch (e) { toast(e.message, "bad"); }
  };

  return (
    <div className="grid lg:grid-cols-[360px_1fr] gap-5 items-start">
      <section className="card p-4 space-y-4 lg:sticky lg:top-[72px]">
        <Title a="Cari" b="rekomendasi" sub="Mesin mencoba semua kombinasi lalu memilih yang terbaik" />
        <div><span className="lbl">Platform / channel</span>
<div className="space-y-1.5">
            {CH_ORDER.map((g) => {
              const list = st.profiles.filter((p) => p.channelType === g);
              if (!list.length) return null;
              return (
                <div key={g}>
                  <div className="text-[11.5px] font-semibold text-ink/50 mb-1">{CH_LABEL[g]}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {list.map((p) => {
                      const on = f.platformProfileIds.includes(p.id);
                      return <button key={p.id} type="button" aria-pressed={on} onClick={() => togglePlat(p.id)}
                        className={`rounded-full px-3 min-h-[36px] text-[13px] font-semibold border ${on ? "bg-bata text-cream border-bata" : "border-line bg-white/60 text-ink/75"}`}>{p.label}</button>;
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-[12px] text-ink/55 mt-1.5">Bisa pilih lebih dari satu. {selProfs.length > 1 ? `${selProfs.length} channel dipilih: 3 rekomendasi terbaik per channel.` : ""}</p></div>
        <div><span className="lbl">Objective</span>
          <select className="field" value={f.objective} onChange={(e) => set({ objective: e.target.value, ...(f.objective2 === e.target.value ? { objective2: "" } : {}) })}>
            {Object.entries(st.objectives).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></div>
        <div><span className="lbl">Objective pendukung <span className="font-normal text-ink/50">(opsional)</span></span>
          <select className="field" value={f.objective2} onChange={(e) => set({ objective2: e.target.value })} aria-label="Objective pendukung">
            <option value="">Tidak ada</option>
            {Object.entries(st.objectives).filter(([k]) => k !== f.objective).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></div>
        <div><span className="lbl">Area</span>
          <div className="grid grid-cols-2 gap-2">{[["bandung", "Bandung Raya"], ["jakarta", "Jabodetabek"]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => set({ area: k })} className={`h-11 rounded-xl font-semibold border ${f.area === k ? "bg-bata text-cream border-bata" : "border-line bg-white/60"}`}>{l}</button>
          ))}</div></div>
        <div>
          <div className="flex justify-between"><span className="lbl">Diskon maksimal</span><span className="text-[14px] font-extrabold text-bata num">{f.maxDiscountPct}%</span></div>
          <input type="range" min="5" max="50" step="5" className="w-full accent-bata" aria-label="Diskon maksimal" value={f.maxDiscountPct} onChange={(e) => set({ maxDiscountPct: +e.target.value })} />
        </div>
        {anyOnline && (<>
          <label className="flex items-center gap-2 text-[14px] font-semibold min-h-[44px]">
            <input type="checkbox" className="w-5 h-5 accent-bata" checked={f.allowCofunding} onChange={(e) => set({ allowCofunding: e.target.checked })} />Boleh ajukan co-funding ke platform
          </label>
          {f.allowCofunding && <div><label className="lbl">Maks. porsi platform</label><NumInput suffix="%" value={f.maxPlatformPct} onChange={(v) => set({ maxPlatformPct: v })} /></div>}
          {!!prof?.programs?.length && <div><span className="lbl">Program yang boleh diikuti</span>
            <div className="flex flex-wrap gap-2">{prof.programs.map((g) => {
              const on = f.programsAllowed.includes(g.programKey);
              return <button key={g.programKey} type="button" onClick={() => set({ programsAllowed: on ? f.programsAllowed.filter((x) => x !== g.programKey) : [...f.programsAllowed, g.programKey] })}
                className={`px-3 min-h-[38px] rounded-full text-[13px] font-semibold border ${on ? "bg-bata text-cream border-bata" : "border-line"}`}>{g.label}</button>;
            })}</div></div>}
        </>)}
        <div className="grid grid-cols-2 gap-3">
          <div><label className="lbl">Budget maks.</label><NumInput prefix="Rp" value={f.budget} placeholder="bebas" onChange={(v) => set({ budget: v })} /></div>
          <div><label className="lbl">Jumlah outlet</label><NumInput value={f.outlets} placeholder="baseline" onChange={(v) => set({ outlets: v })} /></div>
        </div>
        <button className="btn-primary w-full" onClick={run} disabled={busy}><Sparkles size={18} />{busy ? "Mencari…" : "Cari rekomendasi"}</button>
      </section>

      <section className="space-y-3 min-w-0">
        {busy && <div className="card"><Loader text="Mencoba ratusan kombinasi promo…" /></div>}
        {!busy && !res && (
          <div className="card p-6 text-[15px] text-ink/70">
            Pilih platform dan objective, lalu tekan <b>Cari rekomendasi</b>. Mesin hanya menampilkan promo yang tetap untung setelah HPP dan semua potongan platform, dan tidak mendiskon item bermargin tipis (minuman, saus Misdasem/Kacang).
          </div>
        )}
        {res && res.length > 0 && emptyFor.length > 0 && <div className="card p-4 text-[14px]">Tidak ada promo yang lolos untuk {emptyFor.join(", ")}. Naikkan diskon maksimal atau izinkan co-funding.</div>}
        {res && !res.length && <div className="card p-6">{selProfs.every((p) => p.channelType === "event")
          ? "Tidak ada promo yang membuat event ini balik modal dengan asumsi default. Negosiasi sewa booth atau revenue share, tambah hari event, atau ubah asumsi pengunjung di Platform & Biaya."
          : "Tidak ada kombinasi yang lolos. Naikkan diskon maksimal atau budget, atau izinkan co-funding."}</div>}
        <AnimatePresence>
          {res?.map((x, i) => (
            <motion.article key={(x._pid || "") + x.promo.nama + i} initial={{ opacity: 0, y: 24, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: i * 0.12, type: "spring", stiffness: 200, damping: 20 }}
              className={`card p-4 relative overflow-hidden ${x._top ? "ring-2 ring-bata" : ""}`}>
              {x._head && <div className="-mx-4 -mt-4 mb-3 px-4 py-2 bg-ink text-cream text-[13px] font-extrabold">{x._label}</div>}
              <div className="flex items-start gap-3">
                <motion.div className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center font-extrabold text-[18px] ${x._top ? "bg-bata text-cream" : "bg-blush text-bata"}`}
                  initial={{ rotate: -90, scale: 0 }} animate={{ rotate: 0, scale: 1 }} transition={{ delay: 0.15 + i * 0.12, type: "spring" }}>{x.rank}</motion.div>
                <div className="min-w-0 flex-1">
                  {x.badge && <div className={`text-[12px] font-extrabold ${x._top ? "text-bata" : "text-ink/60"}`}>{x.badge}</div>}
                  <h3 className="font-extrabold text-[17px] leading-snug">{x.promo.nama}</h3>
                  <p className="text-[13px] text-ink/70 mt-0.5">{x.reason}</p>
                  <div className="flex flex-wrap gap-3 mt-2 items-center">
                    <MiniBall title="Sehat" label={x.result.health.label} score={x.result.health.score} />
                    <MiniBall title="Margin" label={x.result.margin.label} score={x.result.margin.score} />
                    <MiniBall title="Menarik" label={x.result.menarik.label} score={x.result.menarik.score} />
                    <Badge label={x.result.gate} /><span className="pill">{x.result.quadrant}</span>
                    {x.focus > 0 && <span className="rounded-full bg-ink text-cream px-2.5 py-0.5 text-[12px] font-bold whitespace-nowrap">{x.focus > 1 ? "Prioritas utama" : "Produk prioritas"}</span>}
                    {x.promo.objective2 && <span className="pill">Fit {st.objectives[x.promo.objective]}: {x.result.menarik.fit} · {st.objectives[x.promo.objective2]}: {x.result.menarik.fit2}</span>}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-3 text-[13px]">
                    <Kv k="Harga" v={`${rp(x.result.unit.listPrice)} → ${rp(x.result.unit.customerPays)}`} />
                    <Kv k="CM per unit" v={<CountUp value={x.result.unit.cm} format={rp} />} />
                    <Kv k="Potongan platform" v={x.result.unit.effectiveTakeRate == null ? "–" : pc(x.result.unit.effectiveTakeRate)} />
                    <Kv k="Contribution Target" v={rp(x.result.contribution)} />
                    {x.result.durationAdvice && <Kv k="Durasi saran" v={`${x.result.durationAdvice.rec} hari (${x.result.durationAdvice.min}–${x.result.durationAdvice.max})`} />}
                  </div>
                  <div className="flex flex-wrap gap-2 mt-3">
                    <button className="btn-primary" onClick={() => setGo1({ x, startDate: todayStr, days: x.result.durationAdvice?.rec || 7 })}><Play size={18} />{isHead ? "Jalankan sekarang" : "Ajukan sekarang"}</button>
                    <button className="btn-ghost" onClick={() => open(x)}><ArrowUpRight size={18} />Buka di kalkulator</button>
                    <button className="btn-ghost" onClick={() => saveDraft(x)}><Save size={18} />Simpan draft</button>
                  </div>
                </div>
                <div className="hidden sm:block text-right shrink-0">
                  <div className="text-[11px] text-ink/50 font-semibold">Skor</div>
                  <div className="text-[28px] font-extrabold text-bata leading-none"><CountUp value={x.score} format={(v) => v.toFixed(0)} /></div>
                </div>
              </div>
            </motion.article>
          ))}
        </AnimatePresence>
      </section>

      <Sheet open={!!go1} onClose={() => setGo1(null)} title={isHead ? "Jalankan promo ini?" : "Ajukan promo ini?"}>
        {go1 && (
          <div className="space-y-3">
            <div className="rounded-2xl bg-cream/70 px-3 py-2.5">
              <div className="font-extrabold leading-snug">{go1.x.promo.nama}</div>
              <div className="text-[13px] text-ink/65 mt-0.5">{go1.x._label || st.profiles.find((p) => p.id === go1.x.promo.platformProfileId)?.label} · {go1.x.promo.areas?.[0] === "jakarta" ? "Jabodetabek" : "Bandung Raya"} · CM per unit {rp(go1.x.result.unit.cm)}</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="lbl" htmlFor="rn-start">Mulai</label>
                <input id="rn-start" type="date" className="field" min={todayStr} value={go1.startDate} onChange={(e) => setGo1({ ...go1, startDate: e.target.value })} /></div>
              <div><label className="lbl">Durasi</label><NumInput suffix="hari" value={go1.days} onChange={(v) => setGo1({ ...go1, days: v })} /></div>
            </div>
            {go1.x.result.durationAdvice && <div className="text-[12.5px] text-ink/60">Durasi saran {go1.x.result.durationAdvice.rec} hari (wajar {go1.x.result.durationAdvice.min}–{go1.x.result.durationAdvice.max}).</div>}
            {pre && !pre.blocked && (
              <div className="rounded-2xl border border-line px-3 py-2.5 text-[14px]">
                <div><b>{fmtDate(pre.periodStart)} – {fmtDate(pre.periodEnd)}</b> · {pre.days} hari · Gate {pre.gate}</div>
                <div className="text-ink/70 mt-0.5">{pre.resultStatus === "running" ? "Status langsung Running, tanpa review Finance. Tercatat di Riwayat atas nama Anda."
                  : pre.resultStatus === "approved" ? `Status Approved dan otomatis Running pada ${fmtDate(pre.periodStart)}, tanpa review Finance.`
                  : "Promo dibuat dan langsung masuk review pricing Finance / Cost Control, lalu keputusan Marketing Manager."}</div>
              </div>
            )}
            {pre?.blocked && <div className="rounded-2xl bg-blush text-bata px-3 py-2.5 text-[14px] font-semibold">{pre.blocked}</div>}
            {pre?.warnings?.map((w, i) => (
              <div key={i} className="flex gap-2 rounded-2xl bg-[#F6E7C8] px-3 py-2 text-[13px]"><TriangleAlert size={16} className="shrink-0 mt-0.5 text-[#8A5A12]" /><span>{w}</span></div>
            ))}
            <button className="btn-primary w-full" onClick={runNow} disabled={running || !pre || !!pre.blocked || !go1.days}>
              <Play size={18} />{running ? "Memproses…" : !isHead ? "Ajukan ke Finance / Cost Control" : pre?.resultStatus === "approved" ? "Setujui & jadwalkan" : "Jalankan sekarang"}</button>
            <button className="btn-ghost w-full" onClick={() => setGo1(null)}>Batal</button>
          </div>
        )}
      </Sheet>
    </div>
  );
}
const Kv = ({ k, v }) => <div className="rounded-xl bg-cream/70 px-2.5 py-1.5"><div className="text-[11px] text-ink/55 font-semibold">{k}</div><div className="font-bold num">{v}</div></div>;
