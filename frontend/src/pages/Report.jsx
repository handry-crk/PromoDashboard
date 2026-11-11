import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api, rp, pc, fmtDate, STATUS } from "../lib";
import { MiniBall, Badge, Loader } from "../ui";

export default function Report() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("t") || "";
    api(`/report?t=${encodeURIComponent(t)}`).then(setD).catch((e) => setErr(e.message));
  }, []);
  if (err) return <div className="min-h-screen flex items-center justify-center p-6 text-center"><div><div className="text-[22px] font-extrabold">{err}</div><div className="text-ink/60 mt-1">Minta link terbaru ke Marketing.</div></div></div>;
  if (!d) return <Loader text="Memuat laporan…" />;
  const groups = [["running", "Sedang berjalan"], ["approved", "Disetujui, belum mulai"], ["done", "Selesai"]];
  return (
    <div className="min-h-screen">
      <header className="bg-bata text-cream"><div className="max-w-5xl mx-auto px-4 py-6">
        <div className="text-[12px] font-bold opacity-80">CRK GROUP · Cimol Bojot AA</div>
        <h1 className="text-[28px]"><b className="font-extrabold">Promo</b> Reporting</h1>
        <div className="text-[13px] opacity-80">Diperbarui {new Date(d.generatedAt).toLocaleString("id-ID")}</div>
      </div></header>
      <main className="max-w-5xl mx-auto px-4 py-5 space-y-6">
        {groups.map(([k, l]) => {
          const list = d.promos.filter((p) => p.status === k);
          if (!list.length) return null;
          return (
            <section key={k}>
              <h2 className="text-[19px] font-extrabold mb-2">{l} <span className="text-ink/45">({list.length})</span></h2>
              <div className="grid md:grid-cols-2 gap-3">
                {list.map((p, i) => (
                  <motion.div key={p.kode} className="card p-4" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                    <div className="flex justify-between gap-2"><div className="font-extrabold text-[16px]">{p.nama}</div><span className="pill">{STATUS[p.status]}</span></div>
                    <div className="text-[12px] text-ink/60">{p.kode} · {p.platform} · {p.mechanism} · {fmtDate(p.periodStart)} – {fmtDate(p.periodEnd)}</div>
                    <div className="text-[13px] mt-1">{p.items}</div>
                    {Object.entries(p.areas).map(([a, x]) => (
                      <div key={a} className="mt-2 rounded-2xl bg-cream/60 px-3 py-2">
                        <div className="text-[12px] font-semibold text-ink/60 num">{a === "bandung" ? "Bandung Raya" : "Jabodetabek"} · {rp(x.listPrice)} → {rp(x.customerPays)} (hemat {pc(x.discountPct, 0)})</div>
                        <div className="flex flex-wrap gap-3 mt-1 items-center">
                          <MiniBall title="Sehat" label={x.health} score="" /><MiniBall title="Margin" label={x.margin} score="" /><MiniBall title="Menarik" label={x.menarik} score="" /><Badge label={x.gate} />
                        </div>
                      </div>
                    ))}
                    {p.achievement && (
                      <div className="mt-2 text-[13px] grid grid-cols-2 gap-1 num">
                        {[["Unit", p.achievement.units], ["Tambahan revenue", p.achievement.incRevenue], ["Take rate", p.achievement.takeRate], ["Contribution", p.achievement.contribution]].map(([l2, v]) => (
                          <div key={l2}>{l2}: <b style={{ color: v >= 1 ? "#2F6B4A" : v >= 0.8 ? "#B8741A" : "#B42F27" }}>{v == null ? "–" : pc(v, 0)}</b></div>
                        ))}
                      </div>
                    )}
                    {p.learningHeadline && <div className="mt-2"><div className="italic font-extrabold">{p.learningHeadline}</div><div className="text-[13px]">{p.learning}</div></div>}
                  </motion.div>
                ))}
              </div>
            </section>
          );
        })}
        {!d.promos.length && <div className="card p-6">Belum ada promo yang disetujui.</div>}
      </main>
    </div>
  );
}
