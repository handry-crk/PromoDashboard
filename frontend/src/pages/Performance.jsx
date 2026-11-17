import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { GraduationCap, Trophy, TrendingDown } from "lucide-react";
import { api, fmtDate, CH_LABEL, CH_ORDER } from "../lib";
import { Title, Loader, Empty, useToast, CountUp } from "../ui";
import { groupRecords } from "./Learning";

const nf = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 });
const pctTxt = (v) => (v == null ? "–" : `${nf.format(v)}%`);
const tone = (perf) => (perf == null ? "#8A8172" : perf >= 1 ? "#2F6B4A" : perf >= 0.8 ? "#B8741A" : "#B42F27");
const mean = (xs) => { const v = xs.filter((x) => x != null && !isNaN(x)); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
const BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const PERIODS = [["all", "Semua"], ["90", "3 bulan"], ["180", "6 bulan"], ["year", "Tahun ini"]];

/* Batang pencapaian: garis tegak = 100% target. Skala sampai 150%. */
function PerfBar({ perf, delay = 0 }) {
  const w = Math.max(2, Math.min(150, (perf || 0) * 100)) / 150 * 100;
  return (
    <div className="relative h-3 rounded-full bg-cream">
      <motion.div className="absolute inset-y-0 left-0 rounded-full" style={{ background: tone(perf) }} initial={{ width: 0 }} animate={{ width: `${w}%` }} transition={{ duration: 0.7, delay, ease: "easeOut" }} />
      <div className="absolute -inset-y-1 w-[2px] bg-ink/60" style={{ left: `${100 / 150 * 100}%` }} title="100% target" />
    </div>
  );
}

function Breakdown({ title, rows, note }) {
  if (!rows.length) return null;
  return (
    <section className="card p-4">
      <div className="font-extrabold">{title}</div>
      {note && <div className="text-[12px] text-ink/55 mb-1">{note}</div>}
      <div className="mt-2 space-y-2.5">
        {rows.map((x, i) => (
          <div key={x.label}>
            <div className="flex items-baseline justify-between gap-2 text-[13.5px]">
              <div className="min-w-0 truncate"><b>{x.label}</b> <span className="text-ink/50 text-[12px]">· {x.n} promo</span></div>
              <div className="shrink-0 font-extrabold num" style={{ color: tone(x.perf) }}>{pctTxt(x.perf * 100)}</div>
            </div>
            <PerfBar perf={x.perf} delay={i * 0.05} />
            {x.takeRate != null && <div className="text-[11.5px] text-ink/55 mt-0.5">Take rate rata-rata {pctTxt(x.takeRate)}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}

export default function Performance({ st }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("all");
  const [ch, setCh] = useState("all");
  const [sort, setSort] = useState("best");
  useEffect(() => { api("/learnings").then(setData).catch((e) => toast(e.message, "bad")); }, []); // eslint-disable-line

  const view = useMemo(() => {
    if (!data) return null;
    const now = new Date();
    const since = period === "all" ? null : period === "year" ? new Date(now.getFullYear(), 0, 1) : new Date(now.getTime() - (+period) * 864e5);
    const recs = data.records.filter((r) => r.perf != null && (ch === "all" || r.channelType === ch) && (!since || new Date(r.periodEnd) >= since));
    const groups = groupRecords(recs).map((g) => ({
      ...g, perf: mean(g.rows.map((r) => r.perf)), takeRate: mean(g.rows.map((r) => r.takeRate)), upliftPct: mean(g.rows.map((r) => r.upliftPct)),
      r0: g.rows[0], channels: g.rows.map((r) => r.platformLabel),
    }));
    const by = (keyFn, labelFn) => {
      const m = new Map();
      recs.forEach((r) => { const k = keyFn(r); if (k == null) return; if (!m.has(k)) m.set(k, []); m.get(k).push(r); });
      return [...m.entries()].map(([k, rows]) => ({ label: labelFn(k), n: groupRecords(rows).length, perf: mean(rows.map((r) => r.perf)), takeRate: mean(rows.map((r) => r.takeRate)) }))
        .sort((a, b) => b.perf - a.perf);
    };
    const months = new Map();
    groups.forEach((g) => { const k = g.r0.periodStart.slice(0, 7); if (!months.has(k)) months.set(k, []); months.get(k).push(g); });
    const trend = [...months.entries()].sort().slice(-12).map(([k, gs]) => ({ key: k, label: `${BULAN[+k.slice(5, 7) - 1]} ${k.slice(2, 4)}`, n: gs.length, perf: mean(gs.map((g) => g.perf)) }));
    const split = (label, a, b, fn) => {
      const A = recs.filter(fn), B = recs.filter((r) => !fn(r));
      return A.length && B.length ? { label, a, b, pa: mean(A.map((r) => r.perf)), pb: mean(B.map((r) => r.perf)), na: groupRecords(A).length, nb: groupRecords(B).length } : null;
    };
    return {
      recs, groups,
      kpi: { n: groups.length, hit: groups.filter((g) => g.perf >= 1).length, perf: mean(groups.map((g) => g.perf)), takeRate: mean(groups.map((g) => g.takeRate)), uplift: mean(groups.map((g) => g.upliftPct)) },
      byMech: by((r) => r.mechanism, (k) => st.mechanisms[k] || k),
      byPlat: by((r) => r.platformLabel, (k) => k),
      byObj: by((r) => r.objective, (k) => st.objectives[k] || k),
      trend,
      patterns: [split("Periode gajian", "Mencakup gajian", "Tanpa gajian", (r) => r.hasPayday), split("Momen / hari besar", "Ada momen", "Tanpa momen", (r) => r.hasMoment),
        split("Durasi", "7 hari atau kurang", "Lebih dari 7 hari", (r) => r.days <= 7)].filter(Boolean),
    };
  }, [data, period, ch, st]);

  if (!view) return <Loader text="Menghitung performa promo…" />;
  const { kpi, groups } = view;
  const ranked = [...groups].sort((a, b) => (sort === "best" ? b.perf - a.perf : sort === "worst" ? a.perf - b.perf : b.r0.periodStart.localeCompare(a.r0.periodStart)));
  const best = view.byMech[0], worst = view.byMech[view.byMech.length - 1];
  const filtered = period !== "all" || ch !== "all";
  const maxTrend = Math.max(1.5, ...view.trend.map((t) => t.perf || 0));

  return (
    <div className="space-y-4">
      <Title a="Performa" b="promo" sub="Hasil nyata dari promo yang sudah berjalan, berdasarkan hasil promo yang diinput"
        right={<a href="#/belajar" className="btn-soft"><GraduationCap size={16} /><span className="hidden sm:inline">Input hasil promo</span></a>} />

      <div className="card p-3 space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] font-bold text-ink/55 mr-1">Periode</span>
          {PERIODS.map(([k, l]) => <button key={k} aria-pressed={period === k} onClick={() => setPeriod(k)}
            className={`h-9 px-3.5 rounded-full text-[13px] font-semibold border ${period === k ? "bg-bata text-cream border-bata" : "border-line text-ink/70 bg-paper"}`}>{l}</button>)}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] font-bold text-ink/55 mr-1">Channel</span>
          {[["all", "Semua"], ...CH_ORDER.map((k) => [k, CH_LABEL[k]])].map(([k, l]) => <button key={k} aria-pressed={ch === k} onClick={() => setCh(k)}
            className={`h-9 px-3.5 rounded-full text-[13px] font-semibold border ${ch === k ? "bg-ink text-cream border-ink" : "border-line text-ink/70 bg-paper"}`}>{l}</button>)}
        </div>
      </div>

      {!groups.length ? (
        <Empty title={filtered ? "Tidak ada hasil promo untuk filter ini" : "Belum ada hasil promo"}
          text={filtered ? "Ganti periode atau channel." : "Masukkan hasil promo yang pernah dijalankan di Data belajar, atau tutup promo di Library dengan mengisi hasil aktual."}
          action={<a href="#/belajar" className="btn-primary"><GraduationCap size={16} />Input hasil promo</a>} />
      ) : (<>
        <section className="card p-4">
          <p className="text-[17px] md:text-[20px] font-bold leading-snug">
            {kpi.hit} dari {kpi.n} promo mencapai target, dengan rata-rata pencapaian {pctTxt(kpi.perf * 100)}.
            {best && view.byMech.length > 1 && <> Jenis promo terkuat: <span style={{ color: tone(best.perf) }}>{best.label} ({pctTxt(best.perf * 100)})</span>; terlemah: <span style={{ color: tone(worst.perf) }}>{worst.label} ({pctTxt(worst.perf * 100)})</span>.</>}
          </p>
          {kpi.n < 5 && <p className="text-[13px] text-ink/60 mt-1.5">Baru {kpi.n} promo yang dinilai, jadi pola di bawah belum bisa dijadikan kesimpulan.</p>}
        </section>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[["Promo dinilai", kpi.n, (v) => Math.round(v), null], ["Capai target", kpi.n ? kpi.hit / kpi.n * 100 : null, (v) => `${Math.round(v)}%`, kpi.n ? kpi.hit / kpi.n + 0.3 : null],
            ["Rata-rata pencapaian", kpi.perf != null ? kpi.perf * 100 : null, (v) => `${Math.round(v)}%`, kpi.perf], ["Rata-rata take rate", kpi.takeRate, (v) => `${nf.format(v)}%`, null]].map(([l, v, f, p]) => (
            <div key={l} className="card p-3.5">
              <div className="text-[12px] font-semibold text-ink/60">{l}</div>
              <div className="text-[26px] font-extrabold leading-tight num" style={p != null ? { color: tone(p) } : undefined}>{v == null ? "–" : <CountUp value={v} format={f} />}</div>
              {l === "Capai target" && <div className="text-[11.5px] text-ink/50">{kpi.hit} dari {kpi.n} promo</div>}
              {l === "Rata-rata pencapaian" && <div className="text-[11.5px] text-ink/50">100% = sesuai target</div>}
              {l === "Rata-rata take rate" && kpi.uplift != null && <div className="text-[11.5px] text-ink/50">Revenue rata-rata {kpi.uplift >= 0 ? "+" : ""}{nf.format(kpi.uplift)}%</div>}
            </div>
          ))}
        </div>

        <section className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
            <div className="font-extrabold">Peringkat promo</div>
            <div className="flex gap-1 p-1 rounded-full bg-cream">
              {[["best", "Terbaik", Trophy], ["worst", "Terlemah", TrendingDown], ["new", "Terbaru", null]].map(([k, l, I]) => (
                <button key={k} aria-pressed={sort === k} onClick={() => setSort(k)} className={`h-8 px-3 rounded-full text-[12.5px] font-bold inline-flex items-center gap-1 ${sort === k ? "bg-ink text-cream" : "text-ink/65"}`}>{I && <I size={13} />}{l}</button>
              ))}
            </div>
          </div>
          <div className="text-[12px] text-ink/55 mb-2">Garis tegak = 100% target. Batang penuh = 150%.</div>
          <div className="divide-y divide-line">
            {ranked.slice(0, 20).map((g, i) => (
              <div key={g.key} className="py-2.5 grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 items-center">
                <div className="w-7 h-7 rounded-full bg-blush text-bata text-[12.5px] font-extrabold flex items-center justify-center">{i + 1}</div>
                <div className="min-w-0">
                  <div className="font-bold truncate">{g.nama}</div>
                  <div className="text-[12px] text-ink/60 truncate">{g.channels.join(", ")} · {st.mechanisms[g.r0.mechanism] || g.r0.mechanism} · {fmtDate(g.r0.periodStart)} – {fmtDate(g.r0.periodEnd)}</div>
                </div>
                <div className="text-right">
                  <div className="font-extrabold num text-[16px]" style={{ color: tone(g.perf) }}>{pctTxt(g.perf * 100)}</div>
                  <div className="text-[11.5px] text-ink/55">{g.takeRate != null ? `take rate ${pctTxt(g.takeRate)}` : ""}</div>
                </div>
                <div className="col-start-2 col-span-2 mt-1.5"><PerfBar perf={g.perf} delay={Math.min(i, 10) * 0.04} /></div>
              </div>
            ))}
          </div>
          {ranked.length > 20 && <div className="text-[12px] text-ink/55 mt-2">Menampilkan 20 dari {ranked.length} promo.</div>}
        </section>

        <div className="grid md:grid-cols-2 gap-3 items-start">
          <Breakdown title="Per jenis promo" rows={view.byMech} note="Rata-rata pencapaian target" />
          <Breakdown title="Per channel" rows={view.byPlat} note="Rata-rata pencapaian target" />
          <Breakdown title="Per tujuan" rows={view.byObj} note="Rata-rata pencapaian target" />
          {view.patterns.length > 0 && (
            <section className="card p-4">
              <div className="font-extrabold">Pola waktu</div>
              <div className="text-[12px] text-ink/55 mb-2">Rata-rata pencapaian target</div>
              <div className="space-y-3">
                {view.patterns.map((p) => (
                  <div key={p.label}>
                    <div className="text-[12.5px] font-bold text-ink/70 mb-1">{p.label}</div>
                    <div className="grid grid-cols-2 gap-2">
                      {[[p.a, p.pa, p.na], [p.b, p.pb, p.nb]].map(([l, v, n]) => (
                        <div key={l} className="rounded-xl bg-cream/70 px-3 py-2">
                          <div className="text-[12px] text-ink/60">{l} <span className="text-ink/45">· {n}</span></div>
                          <div className="font-extrabold text-[18px] num" style={{ color: tone(v) }}>{pctTxt(v * 100)}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        {view.trend.length > 1 && (
          <section className="card p-4">
            <div className="font-extrabold">Tren per bulan</div>
            <div className="text-[12px] text-ink/55">Rata-rata pencapaian target menurut bulan mulai promo. Garis putus-putus = 100%.</div>
            <div className="mt-3 overflow-x-auto">
              <div className="relative flex items-end gap-2 h-[150px] min-w-[280px]" role="img" aria-label="Tren pencapaian per bulan">
                <div className="absolute inset-x-0 border-t-2 border-dashed border-ink/35" style={{ bottom: `${24 + (1 / maxTrend) * 104}px` }} />
                {view.trend.map((t, i) => (
                  <div key={t.key} className="flex-1 min-w-[34px] flex flex-col items-center justify-end h-full">
                    <div className="text-[11.5px] font-extrabold num" style={{ color: tone(t.perf) }}>{Math.round(t.perf * 100)}%</div>
                    <motion.div className="w-full max-w-[46px] rounded-t-lg" style={{ background: tone(t.perf) }} initial={{ height: 0 }} animate={{ height: Math.max(3, (t.perf / maxTrend) * 104) }} transition={{ duration: 0.6, delay: i * 0.05 }} />
                    <div className="h-6 flex flex-col items-center justify-center text-[11px] text-ink/60 leading-none"><span>{t.label}</span></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="text-[11.5px] text-ink/50 mt-1">Jumlah promo per bulan: {view.trend.map((t) => `${t.label} ${t.n}`).join(" · ")}</div>
          </section>
        )}

        <p className="text-[12px] text-ink/50">Pencapaian memakai "pencapaian vs target" bila diisi; bila tidak, memakai penilaian 1–5 atau kenaikan revenue (+10% dianggap sesuai target). Promo di beberapa channel dihitung sebagai satu promo.</p>
      </>)}
    </div>
  );
}
