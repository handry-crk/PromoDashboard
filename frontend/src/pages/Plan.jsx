import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles, Calculator, Save, Check, AlertTriangle, CalendarDays, Lock } from "lucide-react";
import { api, rp, pc, fmtDate, CH_LABEL } from "../lib";
import { Title, Loader, Badge, useToast, fireConfetti, Empty } from "../ui";
import { go } from "../App";

const STORE = "crk_plan_v1";
const CH_COLOR = { offline: "#B42F27", online_food: "#2F6B4A", marketplace: "#B8741A" };

export default function Plan({ st, reload }) {
  const toast = useToast();
  const profiles = st.profiles.filter((p) => p.channelType !== "event" && !p.label.endsWith("(lama)"));
  const canSave = st.user.isAdmin || ["head", "planner", "channel_pic"].includes(st.user.perm);
  const saved0 = (() => { try { return JSON.parse(sessionStorage.getItem(STORE) || "null"); } catch { return null; } })();
  const pre = (() => { try { const v = sessionStorage.getItem("crk_plan_platform"); sessionStorage.removeItem("crk_plan_platform"); return v; } catch { return null; } })();
  const [sel, setSel] = useState(pre ? [pre] : saved0?.sel || ["offline_gerobak", "offline_kios", "gofood"].filter((id) => profiles.some((p) => p.id === id)));
  const [maxDisc, setMaxDisc] = useState(saved0?.maxDisc || 20);
  const [plans, setPlans] = useState(pre ? null : saved0?.plans || null);
  const [busy, setBusy] = useState(null);
  const [done, setDone] = useState(saved0?.done || {});
  const [saving, setSaving] = useState(false);

  useEffect(() => { try { sessionStorage.setItem(STORE, JSON.stringify({ sel, maxDisc, plans, done })); } catch { /* */ } }, [sel, maxDisc, plans, done]);

  const build = async (ids = sel) => {
    if (!ids.length) { toast("Pilih minimal satu channel.", "bad"); return; }
    const out = [];
    setPlans(null); setDone({});
    try {
      for (const id of ids) {
        setBusy(profiles.find((p) => p.id === id)?.label || id);
        out.push(await api("/plan", { method: "POST", body: { platformProfileId: id, maxDiscountPct: maxDisc, months: 3 } }));
      }
      setPlans(out);
      if (out.some((p) => p.items.length)) fireConfetti();
    } catch (e) { toast(e.message, "bad"); } finally { setBusy(null); }
  };
  useEffect(() => { if (pre) build([pre]); }, []); // eslint-disable-line

  const items = useMemo(() => (plans || []).flatMap((p) => p.items).sort((a, b) => a.promo.periodStart.localeCompare(b.promo.periodStart)), [plans]);
  const months = useMemo(() => {
    const m = [];
    items.forEach((x) => { let g = m.find((y) => y.key === x.month); if (!g) { g = { key: x.month, label: x.monthLabel, items: [] }; m.push(g); } g.items.push(x); });
    return m;
  }, [items]);
  const existing = useMemo(() => {
    const seen = new Set();
    return (plans || []).flatMap((p) => p.existing.map((e) => ({ ...e, platformLabel: p.platformLabel }))).filter((e) => { const k = e.id; if (seen.has(k)) return false; seen.add(k); return true; });
  }, [plans]);

  const open = (x) => { sessionStorage.setItem("crk_prefill", JSON.stringify({ ...x.promo, _fromCalendar: true })); go("/hitung"); };
  const saveOne = async (x, quiet) => {
    const p = await api("/promos", { method: "POST", body: x.promo });
    setDone((d) => ({ ...d, [x.key]: p.id }));
    if (!quiet) { toast("Tersimpan sebagai draft"); reload(); }
    return p;
  };
  const saveAll = async () => {
    setSaving(true);
    let n = 0;
    try {
      for (const x of items) { if (!done[x.key]) { await saveOne(x, true); n += 1; } }
      toast(`${n} promo tersimpan sebagai draft`); reload();
    } catch (e) { toast(e.message, "bad"); } finally { setSaving(false); }
  };
  const left = items.filter((x) => !done[x.key]).length;
  const range = plans?.[0] ? `${fmtDate(plans[0].from)} – ${fmtDate(plans[0].to)}` : "";
  const learningOff = (plans || []).filter((p) => !p.learning.active);

  return (
    <div className="space-y-4">
      <Title a="Rencana" b="promo 3 bulan" sub="Usulan promo per channel dan area, disusun dari margin, momen, dan jadwal yang sudah ada"
        right={<a href="#/kalender" className="btn-soft"><CalendarDays size={16} /><span className="hidden sm:inline">Kalender</span></a>} />

      <section className="card p-4 space-y-3">
        <div>
          <span className="lbl">Channel</span>
          <div className="flex flex-wrap gap-2">
            {profiles.map((p) => {
              const on = sel.includes(p.id);
              return <button key={p.id} type="button" aria-pressed={on} onClick={() => setSel(on ? sel.filter((x) => x !== p.id) : [...sel, p.id])}
                className={`rounded-full px-3.5 min-h-[38px] text-[13.5px] font-semibold border ${on ? "bg-bata text-cream border-bata" : "border-line bg-white/60 text-ink/75"}`}>{p.label}</button>;
            })}
          </div>
        </div>
        <div>
          <div className="flex justify-between"><span className="lbl">Diskon maksimal</span><span className="text-[14px] font-extrabold text-bata num">{maxDisc}%</span></div>
          <input type="range" min="5" max="50" step="5" className="w-full accent-bata" aria-label="Diskon maksimal" value={maxDisc} onChange={(e) => setMaxDisc(+e.target.value)} />
        </div>
        <button className="btn-primary w-full sm:w-auto" onClick={() => build()} disabled={!!busy}><Sparkles size={18} />{busy ? "Menyusun…" : plans ? "Susun ulang" : "Susun rencana 3 bulan"}</button>
      </section>

      {busy && <div className="card"><Loader text={`Menyusun rencana ${busy}…`} /></div>}

      {!busy && !plans && (
        <div className="card p-5 text-[14.5px] text-ink/70">
          Pilih channel, lalu tekan <b>Susun rencana 3 bulan</b>. Sistem menyusun satu promo utama per channel per area dalam satu waktu, memberi jeda minimal 14 hari untuk produk yang sama,
          dan tidak menimpa promo yang sudah Approved, Running, atau sedang direview. Tidak ada yang berjalan otomatis: setiap usulan Anda simpan sebagai draft dulu.
        </div>
      )}

      {!busy && plans && !items.length && <Empty title="Belum ada usulan" text="Tidak ada promo yang tetap untung dengan batas diskon ini. Naikkan diskon maksimal atau pilih channel lain." />}

      {!busy && plans && items.length > 0 && (<>
        <section className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-extrabold text-[17px]">{items.length} usulan promo · {range}</div>
              <div className="text-[13px] text-ink/60">{months.map((m) => `${m.label}: ${m.items.length}`).join(" · ")}</div>
            </div>
            {canSave && <button className="btn-primary" onClick={saveAll} disabled={saving || !left}><Save size={17} />{saving ? "Menyimpan…" : left ? `Simpan ${left} sebagai draft` : "Semua tersimpan"}</button>}
          </div>
          <ul className="mt-3 text-[13px] text-ink/65 space-y-0.5 list-disc pl-5">
            {plans[0].rules.map((r) => <li key={r}>{r}</li>)}
            <li>Bulan kedua dan ketiga adalah arah; susun ulang tiap bulan supaya mengikuti data terbaru</li>
          </ul>
          {learningOff.length > 0 && (
            <div className="mt-3 flex gap-2 rounded-2xl bg-[#F6E7C8] px-3 py-2 text-[13px]"><AlertTriangle size={16} className="shrink-0 mt-0.5 text-[#8A5A12]" />
              <span>Waktu promo untuk {learningOff.map((p) => p.platformLabel).join(", ")} masih memakai asumsi awal karena hasil promo di Data belajar belum cukup (minimal 3 per jenis channel).</span></div>
          )}
          {existing.length > 0 && (
            <div className="mt-3 flex gap-2 rounded-2xl bg-cream px-3 py-2 text-[13px]"><Lock size={15} className="shrink-0 mt-0.5 text-ink/55" />
              <span>Sudah terjadwal dan tidak ditimpa: {existing.map((e) => `${e.nama} (${e.platformLabel}, ${e.range})`).join("; ")}.</span></div>
          )}
        </section>

        {months.map((m) => (
          <section key={m.key}>
            <div className="sticky top-14 z-10 -mx-4 px-4 py-1.5 bg-cream/95 backdrop-blur font-extrabold text-[15px]">{m.label} <span className="text-ink/50 font-semibold text-[13px]">· {m.items.length} promo</span></div>
            <div className="space-y-2.5">
              {m.items.map((x, i) => {
                const u = x.result.unit;
                return (
                  <motion.article key={x.key} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.05 }}
                    className="card p-3.5 grid grid-cols-[auto_minmax(0,1fr)] gap-3" style={{ borderLeft: `5px solid ${CH_COLOR[x.channelType] || "#B42F27"}` }}>
                    <div className="w-[62px] text-center rounded-2xl bg-cream/80 py-2 self-start">
                      <div className="text-[22px] font-extrabold leading-none num">{x.promo.periodStart.slice(8)}</div>
                      <div className="text-[11px] font-semibold text-ink/60 mt-0.5">{x.monthLabel.slice(0, 3)}</div>
                      <div className="text-[11px] text-ink/55 mt-1">{x.days} hari</div>
                    </div>
                    <div className="min-w-0">
                      <div className="text-[12px] font-bold text-ink/60">{x.platformLabel} · {x.areaLabel} · {x.range}</div>
                      <h3 className="font-extrabold text-[16px] leading-snug break-words">{x.promo.nama}</h3>
                      <div className="text-[12.5px] text-ink/60">{x.mechanismLabel} · {x.objectiveLabel}</div>
                      <div className="grid grid-cols-2 gap-1.5 mt-2 text-[13px]">
                        <div className="rounded-xl bg-cream/70 px-2.5 py-1.5"><div className="text-[11px] text-ink/55 font-semibold">Harga</div><div className="font-bold num">{rp(u.listPrice)} → {rp(u.customerPays)}</div></div>
                        <div className="rounded-xl bg-cream/70 px-2.5 py-1.5"><div className="text-[11px] text-ink/55 font-semibold">CM per unit</div><div className="font-bold num">{rp(u.cm)} ({pc(u.cmPct)})</div></div>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 mt-2 text-[12px] font-semibold">
                        <Badge label={x.result.gate} />
                        <span className="pill">Sehat: {x.result.health.label}</span><span className="pill">Margin: {x.result.margin.label}</span><span className="pill">Menarik: {x.result.menarik.label}</span>
                      </div>
                      {x.timing && (
                        <ul className="mt-2 space-y-0.5 text-[13px]">
                          {x.timing.reasons.slice(0, 2).map((r, k) => <li key={k} className="flex gap-1.5"><Check size={14} className="text-ok mt-0.5 shrink-0" />{r}</li>)}
                          {x.timing.cautions.slice(0, 2).map((r, k) => <li key={"c" + k} className="flex gap-1.5 text-bata"><AlertTriangle size={14} className="mt-0.5 shrink-0" />{r}</li>)}
                        </ul>
                      )}
                      <div className="flex flex-wrap gap-2 mt-2.5">
                        {done[x.key]
                          ? <a href={`#/promo/${done[x.key]}`} className="btn-soft !min-h-[36px] !text-[13px]"><Check size={15} />Tersimpan, buka draft</a>
                          : canSave && <button className="btn-primary !min-h-[36px] !text-[13px]" onClick={() => saveOne(x).catch((e) => toast(e.message, "bad"))}><Save size={15} />Simpan draft</button>}
                        <button className="btn-ghost !min-h-[36px] !text-[13px]" onClick={() => open(x)}><Calculator size={15} />Buka di kalkulator</button>
                      </div>
                    </div>
                  </motion.article>
                );
              })}
            </div>
          </section>
        ))}
        <div className="text-[12px] text-ink/50">Channel: {[...new Set(items.map((x) => CH_LABEL[x.channelType]))].join(", ")}. Angka CM dihitung dari HPP dan biaya platform saat ini.</div>
      </>)}
    </div>
  );
}
