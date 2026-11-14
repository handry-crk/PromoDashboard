import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Tag, Package, Store, Settings as SetI, Users, GraduationCap, CalendarDays, FileUp, Search, Download } from "lucide-react";
import { api } from "../lib";
import { Title, Loader, Empty, useToast } from "../ui";

const ICON = { promo: Tag, produk: Package, platform: Store, settings: SetI, anggota: Users, belajar: GraduationCap, kalender: CalendarDays, file: FileUp };
const dayKey = (iso) => new Date(iso).toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const clock = (iso) => new Date(iso).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });

export default function HistoryPage() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [cat, setCat] = useState("");
  const [by, setBy] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(100);

  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ limit: String(limit) });
      if (cat) p.set("category", cat);
      if (by) p.set("by", by);
      if (q.trim()) p.set("q", q.trim());
      api(`/audit?${p}`).then(setData).catch((e) => toast(e.message, "bad"));
    }, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [cat, by, q, limit]); // eslint-disable-line

  const groups = useMemo(() => {
    const g = [];
    (data?.rows || []).forEach((r) => {
      const k = dayKey(r.at);
      if (!g.length || g[g.length - 1].day !== k) g.push({ day: k, rows: [] });
      g[g.length - 1].rows.push(r);
    });
    return g;
  }, [data]);

  if (!data) return <Loader text="Membuka riwayat…" />;
  const cats = data.categories || {};

  const exportCsv = () => {
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [["Waktu", "Oleh", "Role", "Kategori", "Aksi", "Objek", "Detail", "File"].join(";")]
      .concat(data.rows.map((r) => [new Date(r.at).toLocaleString("id-ID"), r.byName, r.role, cats[r.category] || r.category, r.action, r.target, r.detail, r.file].map(esc).join(";")));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + lines.join("\n")], { type: "text/csv" }));
    a.download = "riwayat-perubahan.csv"; a.click();
  };

  return (
    <div className="space-y-4">
      <Title a="Riwayat" b="perubahan" sub="Siapa mengubah apa, dan kapan"
        right={<button className="btn-soft" onClick={exportCsv} disabled={!data.rows.length}><Download size={16} /><span className="hidden sm:inline">Unduh CSV</span></button>} />

      <div className="card p-3 space-y-3">
        <div className="flex gap-1.5 overflow-x-auto -mx-1 px-1 pb-1">
          {[["", "Semua"], ...Object.entries(cats)].map(([k, l]) => (
            <button key={k} onClick={() => setCat(k)}
              className={`shrink-0 h-9 px-3.5 rounded-full text-[13px] font-semibold border ${cat === k ? "bg-bata text-cream border-bata" : "border-line text-ink/70 bg-paper"}`}>{l}</button>
          ))}
        </div>
        <div className="grid sm:grid-cols-[1fr_220px] gap-2">
          <label className="relative block">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/45" />
            <input className="field !pl-9" placeholder="Cari produk, promo, nama file…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari riwayat" />
          </label>
          <select className="field" value={by} onChange={(e) => setBy(e.target.value)} aria-label="Filter orang">
            <option value="">Semua orang</option>
            {data.people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>

      {!groups.length ? (
        <Empty title="Belum ada riwayat" text={cat || by || q ? "Tidak ada perubahan yang cocok dengan filter ini." : "Setiap perubahan produk, biaya platform, promo, anggota, dan file yang diimport akan tercatat di sini."} />
      ) : groups.map((g) => (
        <section key={g.day}>
          <div className="sticky top-14 z-10 -mx-4 px-4 py-1.5 bg-cream/95 backdrop-blur text-[13px] font-extrabold text-ink/70">{g.day}</div>
          <div className="card divide-y divide-line">
            {g.rows.map((r, i) => {
              const I = ICON[r.category] || Tag;
              return (
                <motion.div key={r.id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 12) * 0.02 }}
                  className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 px-3.5 py-3">
                  <div className="w-9 h-9 rounded-full bg-blush text-bata flex items-center justify-center mt-0.5"><I size={17} /></div>
                  <div className="min-w-0">
                    <div className="text-[14.5px] leading-snug"><b className="font-extrabold">{r.byName}</b> <span className="text-ink/75">{r.action.charAt(0).toLowerCase() + r.action.slice(1)}</span>
                      {r.target && <> <b className="font-bold break-words">{r.target}</b></>}</div>
                    {r.file && <div className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-cream px-2.5 py-0.5 text-[12px] font-semibold break-all"><FileUp size={13} />{r.file}</div>}
                    {r.detail && <div className="text-[13px] text-ink/65 mt-0.5 break-words">{r.detail}</div>}
                    <div className="text-[11.5px] text-ink/50 mt-0.5">{[r.role, cats[r.category]].filter(Boolean).join(" · ")}</div>
                  </div>
                  <time className="text-[13px] font-bold text-ink/60 tabular-nums" dateTime={r.at}>{clock(r.at)}</time>
                </motion.div>
              );
            })}
          </div>
        </section>
      ))}
      {data.rows.length >= limit && data.total > data.rows.length && (
        <button className="btn-ghost w-full" onClick={() => setLimit(limit + 200)}>Tampilkan lebih lama</button>
      )}
    </div>
  );
}
