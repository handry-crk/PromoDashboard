import { useState } from "react";
import { motion } from "framer-motion";
import { Calculator, Sparkles, Database } from "lucide-react";
import { api, rpShort, STATUS, fmtDate } from "../lib";
import { Title, Stat, Quadrant, MiniBall, Badge, Empty, useToast, fireConfetti } from "../ui";

export default function Home({ st, reload }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const promos = st.promos;
  const sums = promos.flatMap((p) => Object.entries(p.summary || {}).map(([a, s]) => ({ ...s, area: a, p })));
  const running = promos.filter((p) => p.effectiveStatus === "running");
  const pending = promos.filter((p) => ["review_finance", "review_head"].includes(p.status));
  const waiting = promos.filter((p) => p.waitingActual);
  const stars = sums.filter((s) => s.quadrant === "Star").length;
  const traps = sums.filter((s) => s.quadrant === "Margin Trap").length;
  const avgHealth = sums.length ? sums.reduce((a, s) => a + s.health.score, 0) / sums.length : null;
  const month = new Date().toISOString().slice(0, 7);
  const contrib = promos.reduce((a, p) => a + (((p.actual || {}).at || "").startsWith(month) ? p.actual.contribution || 0 : 0), 0);
  const unverified = st.profiles.filter((p) => !p.verified).length;

  const seed = async () => {
    setBusy(true);
    try { await api("/seed/crk", { method: "POST" }); toast("Data CRK berhasil diimport"); fireConfetti(); reload(); }
    catch (e) { toast(e.message, "bad"); } finally { setBusy(false); }
  };

  if (st.empty) {
    return (
      <Empty title="Dashboard masih kosong"
        text={st.user.isAdmin ? "Import Price Structure v2, profil biaya platform, dan 3 promo contoh (Mozza Duo, Paket AA 30 Ribu, Braga Pairing)." : "Minta Admin menjalankan Import data CRK dulu."}
        action={st.user.isAdmin && <button className="btn-primary" onClick={seed} disabled={busy}><Database size={18} />{busy ? "Mengimport…" : "Import data CRK"}</button>} />
    );
  }

  const takeaway = (() => {
    const parts = [`${running.length} promo sedang berjalan`];
    if (avgHealth != null) parts.push(`rata-rata skor Sehat ${Math.round(avgHealth)}`);
    let s = parts.join(" dengan ") + ".";
    const warn = [];
    if (traps) warn.push(`${traps} promo masuk Margin Trap`);
    if (unverified) warn.push(`${unverified} profil biaya platform belum divalidasi`);
    if (waiting.length) warn.push(`${waiting.length} promo menunggu hasil aktual`);
    if (warn.length) s += ` Namun, ${warn.join(", ")}.`;
    return s;
  })();

  return (
    <div className="space-y-5">
      <motion.section className="card p-5 md:p-6 relative overflow-hidden" initial={{ scale: 0.98 }} animate={{ scale: 1 }}>
        <div className="grain absolute inset-0 opacity-50 pointer-events-none" />
        <div className="relative md:flex md:items-end md:justify-between gap-6">
          <div className="max-w-2xl">
            <div className="text-[14px] font-semibold text-ink/60">Halo {st.user.name},</div>
            <p className="text-[20px] md:text-[24px] font-bold leading-snug mt-1">{takeaway}</p>
          </div>
          <div className="flex gap-2 mt-4 md:mt-0 shrink-0">
            <a href="#/hitung" className="btn-primary"><Calculator size={18} />Hitung promo</a>
            <a href="#/rekomendasi" className="btn-ghost"><Sparkles size={18} />Cari rekomendasi</a>
          </div>
        </div>
      </motion.section>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Stat label="Promo running" value={running.length} />
        <Stat label="Rata-rata skor Sehat" value={avgHealth ?? "–"} tone={avgHealth >= 75 ? "ok" : avgHealth >= 50 ? "warn" : "bad"} />
        <Stat label="Promo Star" value={stars} tone="ok" />
        <Stat label="Margin Trap" value={traps} tone="bad" />
        <Stat label="Contribution bulan ini" value={contrib} format={(v) => rpShort(v)} sub="dari hasil aktual" />
        <Stat label="Menunggu approval" value={pending.length} tone="warn" sub={unverified ? `${unverified} platform belum divalidasi` : null} />
      </div>

      <div className="grid md:grid-cols-[1fr_1.2fr] gap-5">
        <section className="card p-4">
          <Title a="Peta" b="promo" sub="Margin vs daya tarik, semua promo" />
          <Quadrant points={sums.map((s) => ({ id: s.p.id + s.area, m: s.margin.score, a: s.menarik.score, label: `${s.p.nama} (${s.area})` }))} />
        </section>
        <section className="card p-4">
          <Title a="Running" b="sekarang" sub="Promo yang sedang jalan dan menunggu keputusan" />
          <div className="space-y-2">
            {[...running, ...pending, ...waiting.filter((w) => !running.includes(w))].slice(0, 8).map((p, i) => {
              const s = Object.values(p.summary || {})[0];
              return (
                <motion.a key={p.id} href={`#/promo/${p.id}`} className="block rounded-2xl bg-cream/60 hover:bg-blush px-3 py-2.5"
                  initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold truncate">{p.nama}</div>
                    <span className="pill">{p.waitingActual ? "Isi hasil aktual" : STATUS[p.effectiveStatus]}</span>
                  </div>
                  <div className="text-[12px] text-ink/60">{p.kode} · {fmtDate(p.periodStart)} – {fmtDate(p.periodEnd)}</div>
                  {s && <div className="flex flex-wrap gap-3 mt-1.5 items-center">
                    <MiniBall title="Sehat" label={s.health.label} score={s.health.score} />
                    <MiniBall title="Margin" label={s.margin.label} score={s.margin.score} />
                    <MiniBall title="Menarik" label={s.menarik.label} score={s.menarik.score} />
                    <Badge label={s.gate} />
                  </div>}
                </motion.a>
              );
            })}
            {!running.length && !pending.length && <div className="text-[14px] text-ink/60 py-6 text-center">Belum ada promo berjalan. Mulai dari kalkulator.</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
