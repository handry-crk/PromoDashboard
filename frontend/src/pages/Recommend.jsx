import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowUpRight, Save } from "lucide-react";
import { api, rp, pc, CH_LABEL, CH_ORDER } from "../lib";
import { Title, MiniBall, Badge, Loader, useToast, fireConfetti, CountUp } from "../ui";
import { NumInput } from "./Calculator";
import { go } from "../App";

export default function Recommend({ st, reload }) {
  const toast = useToast();
  const [f, setF] = useState({ platformProfileId: "offline_gerobak", objective: "aov", area: "bandung", maxDiscountPct: 20,
    allowCofunding: false, maxPlatformPct: 50, budget: "", programsAllowed: [], outlets: "", trxPerOutletDay: "" });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const prof = st.profiles.find((p) => p.id === f.platformProfileId);
  const set = (patch) => setF({ ...f, ...patch });

  const run = async () => {
    setBusy(true); setRes(null);
    try {
      const body = { ...f };
      ["budget", "outlets", "trxPerOutletDay"].forEach((k) => { if (body[k] === "") delete body[k]; });
      const t0 = Date.now();
      const r = await api("/recommend", { method: "POST", body });
      await new Promise((ok) => setTimeout(ok, Math.max(0, 900 - (Date.now() - t0))));
      setRes(r.results);
      if (r.results.length) fireConfetti();
    } catch (e) { toast(e.message, "bad"); } finally { setBusy(false); }
  };

  const open = (x) => {
    sessionStorage.setItem("crk_prefill", JSON.stringify({ ...x.promo, nama: x.promo.nama }));
    go("/hitung");
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
          <select className="field" value={f.platformProfileId} onChange={(e) => set({ platformProfileId: e.target.value, programsAllowed: [] })}>
            {CH_ORDER.map((g) => (
              <optgroup key={g} label={CH_LABEL[g]}>{st.profiles.filter((p) => p.channelType === g).map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</optgroup>
            ))}
          </select></div>
        <div><span className="lbl">Objective</span>
          <select className="field" value={f.objective} onChange={(e) => set({ objective: e.target.value })}>
            {Object.entries(st.objectives).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></div>
        <div><span className="lbl">Area</span>
          <div className="grid grid-cols-2 gap-2">{[["bandung", "Bandung Raya"], ["jakarta", "Jabodetabek"]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => set({ area: k })} className={`h-11 rounded-xl font-semibold border ${f.area === k ? "bg-bata text-cream border-bata" : "border-line bg-white/60"}`}>{l}</button>
          ))}</div></div>
        <div>
          <div className="flex justify-between"><span className="lbl">Diskon maksimal</span><span className="text-[14px] font-extrabold text-bata num">{f.maxDiscountPct}%</span></div>
          <input type="range" min="5" max="50" step="5" className="w-full accent-bata" aria-label="Diskon maksimal" value={f.maxDiscountPct} onChange={(e) => set({ maxDiscountPct: +e.target.value })} />
        </div>
        {prof?.channelType !== "offline" && (<>
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
        {res && !res.length && <div className="card p-6">{prof?.channelType === "event"
          ? "Tidak ada promo yang membuat event ini balik modal dengan asumsi default. Negosiasi sewa booth atau revenue share, tambah hari event, atau ubah asumsi pengunjung di Platform & Biaya."
          : "Tidak ada kombinasi yang lolos. Naikkan diskon maksimal atau budget, atau izinkan co-funding."}</div>}
        <AnimatePresence>
          {res?.map((x, i) => (
            <motion.article key={x.promo.nama + i} initial={{ opacity: 0, y: 24, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: i * 0.12, type: "spring", stiffness: 200, damping: 20 }}
              className={`card p-4 relative overflow-hidden ${i === 0 ? "ring-2 ring-bata" : ""}`}>
              <div className="flex items-start gap-3">
                <motion.div className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center font-extrabold text-[18px] ${i === 0 ? "bg-bata text-cream" : "bg-blush text-bata"}`}
                  initial={{ rotate: -90, scale: 0 }} animate={{ rotate: 0, scale: 1 }} transition={{ delay: 0.15 + i * 0.12, type: "spring" }}>{x.rank}</motion.div>
                <div className="min-w-0 flex-1">
                  {x.badge && <div className={`text-[12px] font-extrabold ${i === 0 ? "text-bata" : "text-ink/60"}`}>{x.badge}</div>}
                  <h3 className="font-extrabold text-[17px] leading-snug">{x.promo.nama}</h3>
                  <p className="text-[13px] text-ink/70 mt-0.5">{x.reason}</p>
                  <div className="flex flex-wrap gap-3 mt-2 items-center">
                    <MiniBall title="Sehat" label={x.result.health.label} score={x.result.health.score} />
                    <MiniBall title="Margin" label={x.result.margin.label} score={x.result.margin.score} />
                    <MiniBall title="Menarik" label={x.result.menarik.label} score={x.result.menarik.score} />
                    <Badge label={x.result.gate} /><span className="pill">{x.result.quadrant}</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-3 text-[13px]">
                    <Kv k="Harga" v={`${rp(x.result.unit.listPrice)} → ${rp(x.result.unit.customerPays)}`} />
                    <Kv k="CM per unit" v={<CountUp value={x.result.unit.cm} format={rp} />} />
                    <Kv k="Potongan platform" v={x.result.unit.effectiveTakeRate == null ? "–" : pc(x.result.unit.effectiveTakeRate)} />
                    <Kv k="Contribution Target" v={rp(x.result.contribution)} />
                    {x.result.durationAdvice && <Kv k="Durasi saran" v={`${x.result.durationAdvice.rec} hari (${x.result.durationAdvice.min}–${x.result.durationAdvice.max})`} />}
                  </div>
                  <div className="flex flex-wrap gap-2 mt-3">
                    <button className="btn-primary" onClick={() => open(x)}><ArrowUpRight size={18} />Buka di kalkulator</button>
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
    </div>
  );
}
const Kv = ({ k, v }) => <div className="rounded-xl bg-cream/70 px-2.5 py-1.5"><div className="text-[11px] text-ink/55 font-semibold">{k}</div><div className="font-bold num">{v}</div></div>;
