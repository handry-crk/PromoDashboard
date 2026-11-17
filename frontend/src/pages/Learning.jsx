import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Plus, Upload, Download, Trash2, GraduationCap, Check, Pencil, ChevronDown } from "lucide-react";
import { api, pc, fmtDate, CH_LABEL, CH_ORDER, safeName } from "../lib";
import { Title, Loader, Sheet, useToast, Empty } from "../ui";
import { NumInput } from "./Calculator";
import { BotFace } from "./Assistant";

const RATING = [[1, "Gagal"], [2, "Kurang"], [3, "Sesuai target"], [4, "Berhasil"], [5, "Sangat berhasil"]];
const TEMPLATE = "nama;platform;jenis_promo;tujuan;tujuan_pendukung;area;mulai;selesai;hasil_1_5;take_rate_pct;kenaikan_revenue_pct;pencapaian_target_pct;diskon_pct;catatan\n" +
  "Diskon Gajian Agustus;gofood;diskon_persen;online;;jakarta;2026-08-25;2026-08-31;4;15;12;;20;Ramai di jam makan siang\n" +
  "Bundle Mozza Juli;offline_gerobak;bundle;aov;trial;bandung;2026-07-01;2026-07-21;;9;;110;10;\n";

const nfId = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const pct = (v, d) => `${d === 0 ? Math.round(v) : nfId.format(v)}%`;
const tone = (perf) => (perf == null ? null : perf >= 1 ? "#2F6B4A" : perf >= 0.8 ? "#B8741A" : "#B42F27");

/* Catatan panjang: ringkas dulu, lalu bisa dibuka. Poin bernomor ("1. … 2. …") ditampilkan sebagai daftar. */
function Note({ text }) {
  const [open, setOpen] = useState(false);
  const clean = text.replace(/\s+/g, " ").trim();
  const parts = clean.split(/\s(?=\d{1,2}\.\s+\p{Lu})/u);
  const numbered = parts.length > 1 && /^\d{1,2}\.\s/.test(parts[1]);
  const intro = numbered && !/^\d{1,2}\.\s/.test(parts[0]) ? parts[0] : null;
  const items = numbered ? parts.filter((x) => /^\d{1,2}\.\s/.test(x)).map((x) => x.replace(/^\d{1,2}\.\s+/, "")) : [];
  const long = clean.length > 110 || numbered;
  return (
    <div className="mt-2 pt-2 border-t border-line text-[13px] text-ink/75 leading-relaxed">
      {!open || !numbered ? (
        <p className="break-words" style={!open && long ? { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" } : undefined}>{clean}</p>
      ) : (<>
        {intro && <div className="font-bold text-ink/80">{intro}</div>}
        <ol className="mt-1 space-y-1.5 list-decimal pl-5 break-words">
          {items.map((x, i) => {
            const k = x.indexOf(": ");
            return <li key={i}>{k > 0 && k < 40 ? <><b className="text-ink/85">{x.slice(0, k)}</b><br />{x.slice(k + 2)}</> : x}</li>;
          })}
        </ol>
      </>)}
      {long && <button type="button" className="mt-1 text-[12.5px] font-bold text-bata" onClick={() => setOpen(!open)}>{open ? "Tutup catatan" : "Lihat catatan lengkap"}</button>}
    </div>
  );
}

const areaText = (areas) => (areas || []).map((a) => (a === "jakarta" ? "Jabodetabek" : "Bandung Raya")).join(" + ");

function Tiles({ r, avg, small }) {
  const tiles = [
    r.achievement != null && ["Pencapaian target", pct(r.achievement * 100, 0), tone(r.perf)],
    r.achievement == null && r.rating && ["Hasil", RATING[Math.round(r.rating) - 1][1], tone(r.perf)],
    r.takeRate != null && ["Take rate", pct(r.takeRate), null],
    r.upliftPct != null && ["Kenaikan revenue", (r.upliftPct >= 0 ? "+" : "") + pct(r.upliftPct), null],
  ].filter(Boolean);
  if (!tiles.length) return null;
  return (
    <div className="mt-2.5">
      <div className="grid grid-cols-3 gap-1.5">
        {tiles.map(([k, v, col]) => (
          <div key={k} className="rounded-xl bg-cream/70 px-2.5 py-1.5 min-w-0">
            <div className="text-[11px] text-ink/55 font-semibold leading-tight">{k}</div>
            <div className={`font-extrabold num leading-tight mt-0.5 ${small ? "text-[14px]" : "text-[15px]"}`} style={col ? { color: col } : undefined}>{v}</div>
          </div>
        ))}
      </div>
      {avg && <div className="text-[11.5px] text-ink/50 mt-1">Rata-rata semua channel. Angka tiap channel ada di detail.</div>}
    </div>
  );
}

/* Satu kartu per promo: hasil yang sama di beberapa channel digabung. */
function groupRecords(records) {
  const map = new Map();
  records.forEach((r) => {
    const key = r.source === "promo" ? `promo:${r.id}` : [String(r.nama || "").trim().toLowerCase(), r.periodStart, r.periodEnd, r.mechanism].join("|");
    if (!map.has(key)) map.set(key, { key, nama: r.nama, rows: [] });
    map.get(key).rows.push(r);
  });
  const mean = (rows, k) => { const v = rows.map((x) => x[k]).filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  return [...map.values()].map((g) => {
    const r0 = g.rows[0];
    const same = g.rows.every((r) => ["achievement", "takeRate", "upliftPct", "rating"].every((k) => (r[k] ?? null) === (r0[k] ?? null)));
    const note = g.rows.every((r) => (r.note || "") === (r0.note || "")) ? r0.note : null;
    const avg = same ? null : { achievement: mean(g.rows, "achievement"), takeRate: mean(g.rows, "takeRate"), upliftPct: mean(g.rows, "upliftPct"),
      rating: mean(g.rows, "rating"), perf: mean(g.rows, "perf") };
    return { ...g, same, note, avg };
  });
}

const blank = (st) => ({
  nama: "", platformProfileIds: [st.profiles[0]?.id].filter(Boolean), mechanism: "diskon_persen", objective: "trial", objective2: "", areas: ["bandung"],
  periodStart: "", periodEnd: "", rating: 3, takeRate: "", upliftPct: "", achievement: "", discountPct: "", note: "",
});

export default function Learning({ st }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [errors, setErrors] = useState(null);
  const [openKey, setOpenKey] = useState(null);
  const [ask, setAsk] = useState(null);
  const canAdd = st.user.isAdmin || ["head", "planner", "finance", "channel_pic"].includes(st.user.perm);
  const load = () => api("/learnings").then(setData).catch((e) => toast(e.message, "bad"));
  useEffect(() => { load(); }, []); // eslint-disable-line

  const save = async () => {
    try {
      const { platformProfileIds, id: editId, origPlatform, ...body } = form;
      if (!platformProfileIds.length) { toast("Pilih minimal satu channel.", "bad"); return; }
      ["takeRate", "upliftPct", "achievement", "discountPct", "rating"].forEach((k) => { if (body[k] === "") body[k] = null; });
      if (form.ids) {
        // edit per promo: channel yang tetap dipilih diperbarui, channel baru ditambah, channel yang dilepas dihapus
        const ids = form.ids;
        delete body.ids;
        for (const pid of platformProfileIds) {
          if (ids[pid]) await api(`/learnings/${ids[pid]}`, { method: "PUT", body: { ...body, platformProfileId: pid } });
          else await api("/learnings", { method: "POST", body: { ...body, platformProfileId: pid } });
        }
        for (const [pid, rid] of Object.entries(ids)) if (!platformProfileIds.includes(pid)) await api(`/learnings/${rid}`, { method: "DELETE" });
        toast("Perubahan tersimpan"); setForm(null); load(); return;
      }
      if (editId) {
        await api(`/learnings/${editId}`, { method: "PUT", body: { ...body, platformProfileId: platformProfileIds[0] } });
        toast("Perubahan tersimpan"); setForm(null); load(); return;
      }
      for (const id of platformProfileIds) await api("/learnings", { method: "POST", body: { ...body, platformProfileId: id } });
      toast(platformProfileIds.length > 1 ? `Hasil promo tersimpan untuk ${platformProfileIds.length} channel` : "Hasil promo tersimpan — asisten ikut belajar"); setForm(null); load();
    } catch (e) { toast(e.message, "bad"); }
  };
  const canEdit = (r) => r.source === "manual" && canAdd && (st.user.isAdmin || st.user.perm === "head" || r.byId === st.user.id);
  const fill = (r) => ({
    nama: r.nama || "", mechanism: r.mechanism, objective: r.objective || "trial", objective2: r.objective2 || "",
    areas: r.areas?.length ? r.areas : ["bandung"], periodStart: r.periodStart, periodEnd: r.periodEnd, rating: r.rating ?? "",
    takeRate: r.takeRate ?? "", upliftPct: r.upliftPct ?? "", achievement: r.achievement != null ? Math.round(r.achievement * 10000) / 100 : "",
    discountPct: r.discountPct ?? "", note: r.note || "",
  });
  // satu channel saja (dari detail channel)
  const edit = (r) => setForm({ ...fill(r), id: r.id, single: true, platformProfileIds: [r.platformProfileId] });
  // seluruh promo: semua channel sekaligus
  const editGroup = (g) => setForm({ ...fill(g.rows[0]), ids: Object.fromEntries(g.rows.map((r) => [r.platformProfileId, r.id])), differs: !g.same,
    platformProfileIds: g.rows.map((r) => r.platformProfileId) });
  const del = async (r) => { try { await api(`/learnings/${r.id}`, { method: "DELETE" }); load(); } catch (e) { toast(e.message, "bad"); } };
  const delGroup = async (g) => {
    try { for (const r of g.rows) await api(`/learnings/${r.id}`, { method: "DELETE" }); toast(`${g.nama} dihapus`); setAsk(null); load(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const importCsv = async (file) => {
    try {
      const r = await api("/learnings/import", { method: "POST", body: await file.text(), raw: true, headers: { "X-Filename": safeName(file.name) } });
      toast(`${r.imported} hasil promo diimport${r.errors.length ? `, ${r.errors.length} baris ditolak` : ""}`, r.imported ? "ok" : "bad");
      setErrors(r.errors.length ? r.errors : null); load();
    } catch (e) { toast(e.message, "bad"); }
  };
  const template = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + TEMPLATE], { type: "text/csv" }));
    a.download = "template-hasil-promo.csv"; a.click();
  };

  if (!data) return <Loader text="Membuka data belajar…" />;
  const groups = groupRecords(data.records);
  const ins = data.insights;
  const set = (patch) => setForm({ ...form, ...patch });

  return (
    <div className="space-y-5">
      <Title a="Data" b="belajar" sub="Hasil promo nyata yang dipakai asisten, rekomendasi, dan saran durasi"
        right={canAdd && <div className="flex flex-wrap gap-2">
          <button className="btn-soft" onClick={template}><Download size={16} /><span className="hidden sm:inline">Template CSV</span></button>
          <label className="btn-soft cursor-pointer"><Upload size={16} /><span className="hidden sm:inline">Import CSV</span>
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { if (e.target.files[0]) importCsv(e.target.files[0]); e.target.value = ""; }} /></label>
          <button className="btn-primary" onClick={() => setForm(blank(st))}><Plus size={16} />Hasil promo</button>
        </div>} />

      {errors && (
        <div className="card p-3 border-bata text-[13px]">
          <div className="font-bold text-bata mb-1">Baris yang ditolak</div>
          {errors.map((e) => <div key={e}>{e}</div>)}
        </div>
      )}

      <section className="card p-4">
        <div className="flex items-center gap-3 mb-3"><BotFace size={44} />
          <div><div className="font-extrabold text-[17px]">Yang sudah dipelajari</div>
            <div className="text-[13px] text-ink/60">{ins.total} hasil promo tercatat. Tiap channel butuh minimal 3 hasil sebelum saran mengikuti data.</div></div>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {CH_ORDER.map((ch, i) => {
            const c = ins.byChannel[ch];
            return (
              <motion.div key={ch} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="rounded-2xl bg-cream/70 p-3">
                <div className="flex items-center justify-between"><b>{CH_LABEL[ch]}</b>
                  <span className={`text-[12px] font-bold ${c.active ? "text-ok" : "text-ink/50"}`}>{c.active ? "Aktif belajar" : `${c.n}/3 data`}</span></div>
                <div className="h-2 rounded-full bg-paper mt-2 overflow-hidden">
                  <motion.div className="h-full rounded-full" style={{ background: c.active ? "#2F6B4A" : "#B8741A" }} initial={{ width: 0 }} animate={{ width: `${Math.min(c.n / 3, 1) * 100}%` }} />
                </div>
                <ul className="mt-2 text-[12.5px] text-ink/75 space-y-1">
                  {c.notes.map((n) => <li key={n} className="flex gap-1.5"><Check size={13} className="text-ok mt-0.5 shrink-0" />{n[0].toUpperCase() + n.slice(1)}</li>)}
                  {c.active && !c.notes.length && <li>Belum ada pola yang berbeda dari asumsi awal.</li>}
                  {!c.active && <li>Masih memakai asumsi awal.</li>}
                </ul>
              </motion.div>
            );
          })}
        </div>
        {!!ins.mechanisms.length && (
          <div className="mt-4 scroll-x">
            <table className="w-full min-w-[520px]">
              <thead><tr><th className="th rounded-tl-xl">Jenis promo</th><th className="th">Channel</th><th className="th">Data</th><th className="th">Hasil</th><th className="th">Take rate</th><th className="th rounded-tr-xl">Durasi yang berhasil</th></tr></thead>
              <tbody>{ins.mechanisms.map((m) => (
                <tr key={m.mechanism + m.platformLabel}>
                  <td className="td font-semibold">{m.label}</td><td className="td">{m.platformLabel}</td><td className="td num">{m.n}</td>
                  <td className="td num font-bold" style={{ color: m.avgPerf >= 1 ? "#2F6B4A" : m.avgPerf >= 0.8 ? "#B8741A" : "#B42F27" }}>{pc(m.avgPerf, 0)} target</td>
                  <td className="td num">{m.avgTakeRate == null ? "–" : `${m.avgTakeRate.toLocaleString("id-ID", { maximumFractionDigits: 1 })}%`}</td>
                  <td className="td num">{m.bestDays ? `${m.bestDays} hari` : "–"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h3 className="font-extrabold text-[17px] mb-2">Riwayat hasil promo</h3>
        {!data.records.length && <Empty title="Belum ada hasil promo" text="Masukkan hasil promo yang pernah dijalankan, atau tutup promo di Library dengan mengisi hasil aktual. Keduanya dipakai sebagai data belajar."
          action={canAdd && <button className="btn-primary" onClick={() => setForm(blank(st))}><GraduationCap size={16} />Masukkan hasil promo</button>} />}
        <div className="grid md:grid-cols-2 gap-2 items-start">
          {groups.map((g, i) => {
            const r0 = g.rows[0];
            const open = openKey === g.key;
            const editable = g.rows.every(canEdit);
            const m = g.same ? r0 : g.avg;
            return (
              <motion.div key={g.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 12) * 0.03 }} className="card p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0"><div className="font-bold truncate">{g.nama}</div>
                    <div className="text-[12px] text-ink/60">{areaText(r0.areas)}{r0.areas?.length ? " · " : ""}{st.mechanisms[r0.mechanism] || r0.mechanism} · {fmtDate(r0.periodStart)} – {fmtDate(r0.periodEnd)} ({r0.days} hari)</div></div>
                  <span className="pill shrink-0">{r0.source === "promo" ? "Dari dashboard" : "Input manual"}</span>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {g.rows.map((r) => <span key={r.id + r.platformProfileId} className="rounded-full bg-ink/85 text-cream px-2.5 py-0.5 text-[12px] font-semibold">{r.platformLabel}</span>)}
                </div>
                <Tiles r={m} avg={!g.same} />
                <div className="flex flex-wrap items-center gap-1.5 mt-2 text-[12px]">
                  {r0.hasPayday && <span className="rounded-full bg-cream px-2 py-0.5 text-ink/65 font-semibold">Mencakup gajian</span>}
                  {r0.hasMoment && <span className="rounded-full bg-cream px-2 py-0.5 text-ink/65 font-semibold">Ada momen</span>}
                  <span className="ml-auto flex items-center gap-1">
                    {r0.source === "promo" && <a className="underline text-bata font-bold px-1" href={`#/promo/${r0.id}`}>Buka</a>}
                    {editable && <button className="inline-flex items-center gap-1 rounded-full border border-bata/60 text-bata px-2.5 min-h-[32px] text-[12.5px] font-bold hover:bg-blush" onClick={() => editGroup(g)} aria-label={`Edit ${g.nama}`}><Pencil size={13} />Edit</button>}
                    {editable && (ask === g.key
                      ? <button className="rounded-full bg-bata text-cream px-2.5 min-h-[32px] text-[12.5px] font-bold" onClick={() => delGroup(g)}>Ya, hapus{g.rows.length > 1 ? ` ${g.rows.length} channel` : ""}</button>
                      : <button className="text-bata p-2" aria-label={`Hapus ${g.nama}`} onClick={() => setAsk(g.key)}><Trash2 size={15} /></button>)}
                  </span>
                </div>
                {g.note && <Note text={g.note} />}
                {r0.source !== "promo" && g.rows.length > 1 && (
                  <button type="button" aria-expanded={open} onClick={() => setOpenKey(open ? null : g.key)}
                    className="mt-2 w-full flex items-center justify-between rounded-xl bg-cream/70 px-3 min-h-[40px] text-[13px] font-bold text-ink/80">
                    <span>Detail per channel ({g.rows.length})</span><ChevronDown size={16} className={`transition-transform ${open ? "rotate-180" : ""}`} />
                  </button>
                )}
                {open && (
                  <div className="mt-2 space-y-2">
                    {g.rows.map((r) => (
                      <div key={r.id} className="rounded-xl border border-line px-3 py-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="font-bold text-[14px] min-w-0 truncate">{r.platformLabel}</div>
                          {canEdit(r) && <span className="flex items-center gap-1 shrink-0">
                            <button className="inline-flex items-center gap-1 text-bata text-[12.5px] font-bold px-1.5 min-h-[32px]" onClick={() => edit(r)} aria-label={`Edit ${g.nama} ${r.platformLabel}`}><Pencil size={13} />Edit</button>
                            {g.rows.length > 1 && <button className="text-bata p-1.5" aria-label={`Hapus ${g.nama} ${r.platformLabel}`} onClick={() => del(r)}><Trash2 size={14} /></button>}
                          </span>}
                        </div>
                        <Tiles r={r} small />
                        {!g.note && r.note && <Note text={r.note} />}
                        <div className="text-[11.5px] text-ink/50 mt-1.5">Diinput {r.by || "-"}{r.editedBy ? ` · diubah ${r.editedBy}` : ""}</div>
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      </section>

      <Sheet open={!!form} onClose={() => setForm(null)} title={form?.id || form?.ids ? "Edit hasil promo" : "Masukkan hasil promo"}>
        {form && (
          <div className="space-y-3">
            <div><label className="lbl">Nama promo</label><input className="field" placeholder="mis. Diskon Gajian Agustus" value={form.nama} onChange={(e) => set({ nama: e.target.value })} /></div>
            <div><span className="lbl">Channel {!form.single && <span className="font-normal text-ink/50">(bisa lebih dari satu)</span>}</span>
              <div className="space-y-1.5">
            {CH_ORDER.map((g) => {
              const list = st.profiles.filter((p) => p.channelType === g);
              if (!list.length) return null;
              return (
                <div key={g}>
                  <div className="text-[11.5px] font-semibold text-ink/50 mb-1">{CH_LABEL[g]}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {list.map((p) => {
                      const on = form.platformProfileIds.includes(p.id);
                      return <button key={p.id} type="button" aria-pressed={on} onClick={() => set({ platformProfileIds: form.single ? [p.id] : on ? form.platformProfileIds.filter((x) => x !== p.id) : [...form.platformProfileIds, p.id] })}
                        className={`rounded-full px-3 min-h-[36px] text-[13px] font-semibold border ${on ? "bg-bata text-cream border-bata" : "border-line bg-white/60 text-ink/75"}`}>{p.label}</button>;
                    })}
                  </div>
                </div>
              );
            })}
          </div>
              {form.single && <p className="text-[12px] text-ink/55 mt-1.5">Anda mengedit hasil untuk satu channel ini saja.</p>}
              {!form.single && form.platformProfileIds.length > 1 && <p className="text-[12px] text-ink/55 mt-1.5">{form.differs ? "Angka tiap channel saat ini berbeda. Menyimpan dari sini menyamakan semuanya; untuk mengubah satu channel saja, pakai Edit di detail channel." : "Satu promo, hasil yang sama dicatat untuk semua channel yang dipilih. Angka per channel bisa diubah lewat detail channel."}</p>}</div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="lbl">Jenis promo</label>
                <select className="field" value={form.mechanism} onChange={(e) => set({ mechanism: e.target.value })}>
                  {Object.entries(st.mechanisms).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select></div>
              <div><label className="lbl">Tujuan</label>
                <select className="field" value={form.objective} onChange={(e) => set({ objective: e.target.value, ...(form.objective2 === e.target.value ? { objective2: "" } : {}) })}>
                  {Object.entries(st.objectives).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select></div>
              <div><label className="lbl">Tujuan pendukung</label>
                <select className="field" value={form.objective2 || ""} onChange={(e) => set({ objective2: e.target.value })}>
                  <option value="">Tidak ada</option>
                  {Object.entries(st.objectives).filter(([k]) => k !== form.objective).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select></div>
              <div className="col-span-2"><span className="lbl">Area <span className="font-normal text-ink/50">(bisa dua)</span></span>
                <div className="grid grid-cols-2 gap-1.5">
                  {[["bandung", "Bandung Raya"], ["jakarta", "Jabodetabek"]].map(([k, l]) => {
                    const on = form.areas.includes(k);
                    return <button key={k} type="button" aria-pressed={on}
                      onClick={() => { const next = on ? form.areas.filter((x) => x !== k) : [...form.areas, k]; if (next.length) set({ areas: next }); }}
                      className={`rounded-xl min-h-[46px] px-1 text-[13px] font-semibold border leading-tight ${on ? "bg-bata text-cream border-bata" : "border-line bg-white/60 text-ink/75"}`}>{l}</button>;
                  })}
                </div></div>
              <div><label className="lbl">Mulai</label><input type="date" className="field" value={form.periodStart} onChange={(e) => set({ periodStart: e.target.value })} /></div>
              <div><label className="lbl">Selesai</label><input type="date" className="field" value={form.periodEnd} onChange={(e) => set({ periodEnd: e.target.value })} /></div>
            </div>
            <div><span className="lbl">Hasilnya bagaimana?</span>
              <div className="grid grid-cols-5 gap-1.5">
                {RATING.map(([n, l]) => (
                  <button key={n} type="button" onClick={() => set({ rating: n })}
                    className={`rounded-xl border px-1 py-2 text-[11.5px] font-bold leading-tight ${form.rating === n ? "bg-bata text-cream border-bata" : "border-line bg-white/60"}`}>{l}</button>
                ))}
              </div></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="lbl">Take rate (opsional)</label><NumInput suffix="%" value={form.takeRate} onChange={(v) => set({ takeRate: v })} /></div>
              <div><label className="lbl">Kenaikan revenue (opsional)</label><NumInput suffix="%" value={form.upliftPct} onChange={(v) => set({ upliftPct: v })} /></div>
              <div><label className="lbl">Pencapaian vs target (opsional)</label><NumInput suffix="%" value={form.achievement} placeholder="mis. 110" onChange={(v) => set({ achievement: v })} /></div>
              <div><label className="lbl">Diskon (opsional)</label><NumInput suffix="%" value={form.discountPct} onChange={(v) => set({ discountPct: v })} /></div>
            </div>
            <div><label className="lbl">Catatan</label><textarea className="field min-h-[70px]" placeholder="Apa yang berhasil atau tidak" value={form.note} onChange={(e) => set({ note: e.target.value })} /></div>
            <p className="text-[12px] text-ink/55">Bila pencapaian vs target diisi, angka itu dipakai. Bila tidak, penilaian di atas yang dipakai.</p>
            <button className="btn-primary w-full" onClick={save}>{form.id || form.ids ? "Simpan perubahan" : "Simpan hasil promo"}</button>
          </div>
        )}
      </Sheet>
    </div>
  );
}
