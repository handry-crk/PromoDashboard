import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Tag, Package, Store, Settings as SetI, Users, GraduationCap, CalendarDays, FileUp, Search, Download } from "lucide-react";
import { api } from "../lib";
import { Title, Loader, Empty, useToast } from "../ui";

const ICON = { promo: Tag, produk: Package, platform: Store, settings: SetI, anggota: Users, belajar: GraduationCap, kalender: CalendarDays, file: FileUp };
const dayKey = (iso) => new Date(iso).toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const KIND = {
  tambah: { label: "Tambah", cls: "bg-[#DCE9DF] text-[#234F37]" }, ubah: { label: "Ubah", cls: "bg-[#F6E7C8] text-[#6F4A0E]" },
  hapus: { label: "Hapus", cls: "bg-blush text-bata" }, lain: { label: "Lainnya", cls: "bg-cream text-ink/70" },
};
const dmy = (ymd) => (ymd ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}/${ymd.slice(0, 4)}` : "");

export default function HistoryPage() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [cat, setCat] = useState("");
  const [by, setBy] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(100);
  const [kind, setKind] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ limit: String(limit) });
      if (cat) p.set("category", cat);
      if (by) p.set("by", by);
      if (q.trim()) p.set("q", q.trim());
      if (kind) p.set("kind", kind);
      if (from) p.set("date_from", from);
      if (to) p.set("date_to", to);
      api(`/audit?${p}`).then(setData).catch((e) => toast(e.message, "bad"));
    }, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [cat, by, q, limit, kind, from, to]); // eslint-disable-line

  const groups = useMemo(() => {
    const g = [];
    (data?.rows || []).forEach((r) => {
      const k = r.tanggal ? dayKey(r.tanggal + "T12:00:00") : dayKey(r.at);
      if (!g.length || g[g.length - 1].day !== k) g.push({ day: k, rows: [] });
      g[g.length - 1].rows.push(r);
    });
    return g;
  }, [data]);

  if (!data) return <Loader text="Membuka riwayat…" />;
  const cats = data.categories || {};

  const exportCsv = () => {
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [["Tanggal", "Jam (WIB)", "Nama", "Role", "Jenis", "Kategori", "Aksi", "Objek", "Detail", "File"].join(";")]
      .concat(data.rows.map((r) => [dmy(r.tanggal), r.jam, r.byName, r.role, KIND[r.kind]?.label, cats[r.category] || r.category, r.action, r.target, r.detail, r.file].map(esc).join(";")));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + lines.join("\n")], { type: "text/csv" }));
    a.download = "riwayat-perubahan.csv"; a.click();
  };

  return (
    <div className="space-y-4">
      <Title a="Riwayat" b="perubahan" sub="Siapa menambah, mengubah, atau menghapus apa — nama, tanggal, dan jam"
        right={<button className="btn-soft" onClick={exportCsv} disabled={!data.rows.length}><Download size={16} /><span className="hidden sm:inline">Unduh CSV</span></button>} />

      <div className="card p-3 space-y-3">
        <div className="flex gap-1.5 overflow-x-auto -mx-1 px-1 pb-1">
          {[["", "Semua"], ...Object.entries(cats)].map(([k, l]) => (
            <button key={k} onClick={() => setCat(k)}
              className={`shrink-0 h-9 px-3.5 rounded-full text-[13px] font-semibold border ${cat === k ? "bg-bata text-cream border-bata" : "border-line text-ink/70 bg-paper"}`}>{l}</button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] font-bold text-ink/55 mr-1">Jenis</span>
          {[["", "Semua"], ["tambah", "Tambah"], ["ubah", "Ubah"], ["hapus", "Hapus"]].map(([k, l]) => (
            <button key={k} onClick={() => setKind(k)} aria-pressed={kind === k}
              className={`h-9 px-3.5 rounded-full text-[13px] font-semibold border ${kind === k ? "bg-ink text-cream border-ink" : "border-line text-ink/70 bg-paper"}`}>{l}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div><label className="lbl" htmlFor="h-from">Dari tanggal</label><input id="h-from" type="date" className="field" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} /></div>
          <div><label className="lbl" htmlFor="h-to">Sampai tanggal</label><input id="h-to" type="date" className="field" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} /></div>
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

      {data.summary?.length > 0 && (
        <section className="card p-3">
          <div className="flex items-baseline justify-between gap-2 mb-2">
            <div className="font-extrabold">Rekap per orang</div>
            <div className="text-[12px] text-ink/55">{data.total} catatan{from || to ? ` · ${from ? dmy(from) : "awal"} – ${to ? dmy(to) : "hari ini"}` : ""}</div>
          </div>
          <div className="overflow-x-auto -mx-1 px-1">
            <table className="w-full text-[13.5px] min-w-[260px]">
              <thead><tr className="text-left text-[12px] text-ink/55">
                <th className="font-semibold py-1 pr-2">Nama</th><th className="font-semibold px-2 text-right">Tambah</th><th className="font-semibold px-2 text-right">Ubah</th>
                <th className="font-semibold px-2 text-right">Hapus</th><th className="font-semibold pl-2 text-right hidden sm:table-cell">Terakhir</th></tr></thead>
              <tbody>
                {data.summary.map((x) => (
                  <tr key={x.id || x.name} className="border-t border-line">
                    <td className="py-1.5 pr-2"><button className="font-bold text-left hover:text-bata" onClick={() => setBy(by === x.id ? "" : x.id || "")}>{x.name}</button>
                      <div className="text-[11.5px] text-ink/50">{x.role}</div></td>
                    <td className="px-2 text-right num">{x.tambah}</td><td className="px-2 text-right num">{x.ubah}</td>
                    <td className={`px-2 text-right num ${x.hapus ? "text-bata font-bold" : ""}`}>{x.hapus}</td>
                    <td className="pl-2 text-right text-[12px] text-ink/60 whitespace-nowrap hidden sm:table-cell">{new Date(x.last).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!groups.length ? (
        <Empty title="Belum ada riwayat" text={cat || by || q || kind || from || to ? "Tidak ada perubahan yang cocok dengan filter ini." : "Setiap perubahan produk, biaya platform, promo, anggota, dan file yang diimport akan tercatat di sini."} />
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
                    <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-ink/50 mt-1">
                      <span className={`rounded-full px-2 py-0.5 font-bold ${KIND[r.kind]?.cls || ""}`}>{KIND[r.kind]?.label}</span>
                      <span>{[r.role, cats[r.category]].filter(Boolean).join(" · ")}</span>
                    </div>
                  </div>
                  <time className="text-right leading-tight tabular-nums" dateTime={r.at}>
                    <div className="text-[13px] font-bold text-ink/70">{r.jam?.slice(0, 5)}</div>
                    <div className="text-[11px] text-ink/50">{dmy(r.tanggal)}</div>
                  </time>
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
