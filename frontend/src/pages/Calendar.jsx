import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, AlertTriangle, Plus, CalendarDays, Rows3, Trash2 } from "lucide-react";
import { api, STATUS, CH_LABEL, fmtDate } from "../lib";
import { Title, Loader, Sheet, useToast, Badge } from "../ui";
import { go } from "../App";

const DAY = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];
const BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const diff = (a, b) => Math.round((parse(b) - parse(a)) / 864e5);

// status → bar style
const STYLE = {
  running: { bg: "#B42F27", fg: "#ECE4D4", label: "Running" },
  approved: { bg: "#2F6B4A", fg: "#ECE4D4", label: "Approved" },
  review_finance: { bg: "#B8741A", fg: "#ECE4D4", label: "Review" },
  review_head: { bg: "#B8741A", fg: "#ECE4D4", label: "Review" },
  draft: { bg: "#E0BFB1", fg: "#212121", label: "Draft", dashed: true },
  done: { bg: "#21212133", fg: "#212121", label: "Selesai" },
  rejected: { bg: "#21212114", fg: "#21212199", label: "Ditolak" },
};
const MOMENT = { libur: "#B42F27", belanja: "#2F6B4A", gajian: "#B8741A", musim: "#7A5BA6", momen: "#212121" };

export default function Calendar({ st }) {
  const toast = useToast();
  const now = new Date();
  const [month, setMonth] = useState(() => {
    const want = sessionStorage.getItem("crk_cal_month");
    sessionStorage.removeItem("crk_cal_month");
    if (want) { const [y, m] = want.split("-").map(Number); return new Date(y, m - 1, 1); }
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [dir, setDir] = useState(0);
  const [view, setView] = useState(window.innerWidth < 768 ? "bulan" : "bulan");
  const [ch, setCh] = useState("all");
  const [area, setArea] = useState("all");
  const [showDraft, setShowDraft] = useState(true);
  const [showRejected, setShowRejected] = useState(false);
  const [data, setData] = useState(null);
  const [day, setDay] = useState(null);
  const [addMo, setAddMo] = useState(null);
  const canPlan = st.user.isAdmin || ["planner", "channel_pic", "head"].includes(st.user.perm);
  const canMoment = st.user.isAdmin || ["planner", "head", "finance"].includes(st.user.perm);

  const gridStart = useMemo(() => addDays(month, -((month.getDay() + 6) % 7)), [month]);
  const monthEnd = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const gridEnd = addDays(monthEnd, 6 - ((monthEnd.getDay() + 6) % 7));
  const weeks = Math.round((gridEnd - gridStart) / 864e5 + 1) / 7;

  const load = () => {
    setData(null);
    api(`/calendar?start=${iso(gridStart)}&end=${iso(gridEnd)}`).then(setData).catch((e) => toast(e.message, "bad"));
  };
  useEffect(load, [month]); // eslint-disable-line

  const conflictIds = useMemo(() => new Set((data?.conflicts || []).flatMap((c) => [c.a, c.b])), [data]);
  const promos = useMemo(() => (data?.promos || []).filter((p) =>
    (ch === "all" || p.channelType === ch) && (area === "all" || p.areas.includes(area)) &&
    (showDraft || !["draft", "review_finance", "review_head"].includes(p.effectiveStatus)) &&
    (showRejected || p.effectiveStatus !== "rejected")), [data, ch, area, showDraft, showRejected]);
  const moments = data?.moments || [];

  const shift = (n) => { setDir(n); setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1)); };
  const newPromoOn = (d) => {
    sessionStorage.setItem("crk_prefill", JSON.stringify({ periodStart: d, periodEnd: iso(addDays(parse(d), 13)), _fromCalendar: true }));
    go("/hitung");
  };
  const momentsOn = (d) => moments.filter((m) => d >= m.date && d <= (m.end || m.date));
  const promosOn = (d) => promos.filter((p) => d >= p.periodStart && d <= p.periodEnd);

  return (
    <div className="space-y-4">
      <Title a="Kalender" b="promo" sub="Jadwal promo, momen penting, dan bentrok antar promo"
        right={<div className="flex gap-1 p-1 rounded-full bg-paper border border-line">
          {[["bulan", "Bulan", CalendarDays], ["timeline", "Timeline", Rows3]].map(([k, l, I]) => (
            <button key={k} onClick={() => setView(k)} className={`relative h-9 px-3 rounded-full text-[13px] font-bold flex items-center gap-1 ${view === k ? "text-cream" : "text-ink/70"}`}>
              {view === k && <motion.span layoutId="calview" className="absolute inset-0 rounded-full bg-ink" />}
              <I size={15} className="relative" /><span className="relative hidden sm:inline">{l}</span>
            </button>
          ))}
        </div>} />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <button onClick={() => shift(-1)} className="w-10 h-10 rounded-full border border-line hover:bg-blush flex items-center justify-center" aria-label="Bulan sebelumnya"><ChevronLeft size={18} /></button>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={iso(month)} initial={{ opacity: 0, y: dir > 0 ? 8 : -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="min-w-[150px] text-center text-[18px] font-extrabold">{BULAN[month.getMonth()]} {month.getFullYear()}</motion.div>
          </AnimatePresence>
          <button onClick={() => shift(1)} className="w-10 h-10 rounded-full border border-line hover:bg-blush flex items-center justify-center" aria-label="Bulan berikutnya"><ChevronRight size={18} /></button>
          <button onClick={() => { setDir(0); setMonth(new Date(now.getFullYear(), now.getMonth(), 1)); }} className="btn-soft !min-h-[38px] !px-3 !text-[13px]">Hari ini</button>
        </div>
        <select className="field !w-auto !py-2 text-[14px]" value={ch} onChange={(e) => setCh(e.target.value)} aria-label="Filter channel">
          <option value="all">Semua channel</option>{["offline", "online_food", "marketplace", "event"].map((k) => <option key={k} value={k}>{CH_LABEL[k]}</option>)}
        </select>
        <select className="field !w-auto !py-2 text-[14px]" value={area} onChange={(e) => setArea(e.target.value)} aria-label="Filter area">
          <option value="all">Semua area</option><option value="bandung">Bandung Raya</option><option value="jakarta">Jabodetabek</option>
        </select>
        <label className="flex items-center gap-1.5 text-[13px] font-semibold"><input type="checkbox" className="accent-bata w-4 h-4" checked={showDraft} onChange={(e) => setShowDraft(e.target.checked)} />Draft & review</label>
        <label className="flex items-center gap-1.5 text-[13px] font-semibold"><input type="checkbox" className="accent-bata w-4 h-4" checked={showRejected} onChange={(e) => setShowRejected(e.target.checked)} />Ditolak</label>
        {canMoment && <button className="btn-ghost !min-h-[38px] !text-[13px] ml-auto" onClick={() => setAddMo({ date: iso(month), end: "", label: "", type: "momen" })}><Plus size={15} />Momen</button>}
      </div>

      {!!data?.conflicts?.length && (
        <motion.section initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="card p-3 border-bata/50">
          <div className="font-extrabold text-bata flex items-center gap-2 mb-1"><AlertTriangle size={17} />{data.conflicts.length} peringatan jadwal</div>
          <ul className="space-y-1 text-[13px]">
            {data.conflicts.map((c, i) => (
              <li key={i} className="flex flex-wrap gap-x-2">
                <span className={`font-bold ${c.type === "bentrok" ? "text-bata" : "text-warn"}`}>{c.type === "bentrok" ? "Bentrok" : c.type === "harga" ? "Beda harga" : "Padat"}</span>
                <span>{c.message}</span>
                <span className="text-ink/55">({fmtDate(c.from)}{c.to !== c.from ? ` – ${fmtDate(c.to)}` : ""})</span>
                <button className="underline text-bata" onClick={() => go(`/promo/${c.a}`)}>{c.aName}</button>
                {c.b !== c.a && <button className="underline text-bata" onClick={() => go(`/promo/${c.b}`)}>{c.bName}</button>}
              </li>
            ))}
          </ul>
        </motion.section>
      )}

      {!data ? <div className="card"><Loader text="Menyusun kalender…" /></div> : (
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div key={iso(month) + view} initial={{ opacity: 0, x: dir * 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -dir * 30 }} transition={{ duration: 0.2 }}>
            {view === "bulan"
              ? <MonthGrid gridStart={gridStart} weeks={weeks} month={month} promos={promos} momentsOn={momentsOn} conflictIds={conflictIds} onDay={setDay} />
              : <Timeline month={month} monthEnd={monthEnd} promos={promos} moments={moments} conflictIds={conflictIds} onDay={setDay} />}
          </motion.div>
        </AnimatePresence>
      )}

      <div className="flex flex-wrap gap-3 text-[12px] text-ink/65">
        {["running", "approved", "review_finance", "draft", "done"].map((k) => (
          <span key={k} className="flex items-center gap-1.5"><i className="inline-block w-4 h-2.5 rounded-full" style={{ background: STYLE[k].bg, outline: STYLE[k].dashed ? "1px dashed #B42F27" : "none" }} />{STYLE[k].label}</span>
        ))}
        <span className="flex items-center gap-1.5"><AlertTriangle size={13} className="text-bata" />Ada bentrok</span>
        {Object.entries({ libur: "Hari besar", belanja: "Momen belanja", gajian: "Gajian", musim: "Musim" }).map(([k, l]) => (
          <span key={k} className="flex items-center gap-1.5"><i className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: MOMENT[k] }} />{l}</span>
        ))}
        <span>* tanggal perkiraan</span>
      </div>

      {/* agenda (useful on mobile) */}
      {data && view === "bulan" && <Agenda month={month} monthEnd={monthEnd} promos={promos} moments={moments} conflictIds={conflictIds} />}

      <Sheet open={!!day} onClose={() => setDay(null)} title={day ? new Date(parse(day)).toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : ""}>
        {day && (
          <div className="space-y-3">
            {momentsOn(day).map((m, i) => (
              <div key={i} className="flex items-center justify-between rounded-2xl px-3 py-2 text-[14px] font-semibold" style={{ background: `${MOMENT[m.type] || "#212121"}18`, color: MOMENT[m.type] }}>
                <span>{m.label}</span>
                {m.custom && canMoment && <button aria-label="Hapus momen" onClick={async () => { await api(`/moments/${m.id}`, { method: "DELETE" }); setDay(null); load(); }}><Trash2 size={15} /></button>}
              </div>
            ))}
            {promosOn(day).map((p) => (
              <button key={p.id} onClick={() => go(`/promo/${p.id}`)} className="w-full text-left rounded-2xl bg-paper border border-line px-3 py-2.5 hover:bg-blush">
                <div className="flex justify-between gap-2"><b>{p.nama}</b><span className="pill">{STATUS[p.effectiveStatus]}</span></div>
                <div className="text-[12px] text-ink/60">{p.platformLabel} · {p.mechanism} · {fmtDate(p.periodStart)} – {fmtDate(p.periodEnd)}</div>
                <div className="text-[12px] text-ink/60">{p.productNames.join(" + ")}</div>
                <div className="flex gap-2 mt-1 items-center">{p.gate && <Badge label={p.gate} />}{conflictIds.has(p.id) && <span className="text-bata text-[12px] font-bold flex items-center gap-1"><AlertTriangle size={13} />Bentrok</span>}</div>
              </button>
            ))}
            {!promosOn(day).length && !momentsOn(day).length && <div className="text-[14px] text-ink/60">Belum ada promo atau momen di tanggal ini.</div>}
            {canPlan && <button className="btn-primary w-full" onClick={() => newPromoOn(day)}><Plus size={16} />Buat promo mulai tanggal ini</button>}
          </div>
        )}
      </Sheet>

      <Sheet open={!!addMo} onClose={() => setAddMo(null)} title="Tambah momen">
        {addMo && (
          <div className="space-y-3">
            <div><label className="lbl">Nama momen</label><input className="field" placeholder="mis. Anniversary CBAA, Opening Braga 2" value={addMo.label} onChange={(e) => setAddMo({ ...addMo, label: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="lbl">Mulai</label><input type="date" className="field" value={addMo.date} onChange={(e) => setAddMo({ ...addMo, date: e.target.value })} /></div>
              <div><label className="lbl">Selesai (opsional)</label><input type="date" className="field" value={addMo.end} onChange={(e) => setAddMo({ ...addMo, end: e.target.value })} /></div>
            </div>
            <div><label className="lbl">Jenis</label>
              <select className="field" value={addMo.type} onChange={(e) => setAddMo({ ...addMo, type: e.target.value })}>
                <option value="momen">Momen brand</option><option value="belanja">Momen belanja</option><option value="libur">Hari besar</option><option value="musim">Musim</option>
              </select></div>
            <button className="btn-primary w-full" onClick={async () => {
              try { await api("/moments", { method: "POST", body: addMo }); toast("Momen ditambahkan"); setAddMo(null); load(); } catch (e) { toast(e.message, "bad"); }
            }}>Simpan momen</button>
          </div>
        )}
      </Sheet>
    </div>
  );
}

/* lanes: assign each promo (within a range) to the first free row */
function lanes(items, startKey, endKey) {
  const rows = [];
  [...items].sort((a, b) => (a[startKey] < b[startKey] ? -1 : a[startKey] > b[startKey] ? 1 : b[endKey].localeCompare(a[endKey])))
    .forEach((it) => {
      let i = rows.findIndex((r) => r < it[startKey]);
      if (i === -1) { rows.push(it[endKey]); i = rows.length - 1; } else rows[i] = it[endKey];
      it._lane = i;
    });
  return rows.length;
}

function MonthGrid({ gridStart, weeks, month, promos, momentsOn, conflictIds, onDay }) {
  const today = iso(new Date());
  const MAX_LANES = 3;
  return (
    <div className="card overflow-hidden">
      <div className="grid grid-cols-7 bg-bata text-cream text-[12px] font-bold">
        {DAY.map((d) => <div key={d} className="px-2 py-1.5">{d}</div>)}
      </div>
      {Array.from({ length: weeks }).map((_, w) => {
        const ws = addDays(gridStart, w * 7);
        const wsI = iso(ws), weI = iso(addDays(ws, 6));
        const segs = promos.filter((p) => p.periodEnd >= wsI && p.periodStart <= weI).map((p) => ({
          p, s: p.periodStart < wsI ? wsI : p.periodStart, e: p.periodEnd > weI ? weI : p.periodEnd,
          cutL: p.periodStart < wsI, cutR: p.periodEnd > weI,
        }));
        lanes(segs, "s", "e");
        const shown = segs.filter((x) => x._lane < MAX_LANES);
        return (
          <div key={w} className="relative border-t border-line">
            <div className="grid grid-cols-7">
              {Array.from({ length: 7 }).map((__, d) => {
                const dt = addDays(ws, d); const di = iso(dt);
                const out = dt.getMonth() !== month.getMonth();
                const mos = momentsOn(di);
                const hidden = segs.filter((x) => x._lane >= MAX_LANES && di >= x.s && di <= x.e).length;
                return (
                  <button key={d} onClick={() => onDay(di)} aria-label={`Tanggal ${di}`}
                    className={`relative flex flex-col justify-start items-stretch text-left min-h-[110px] sm:min-h-[126px] px-1.5 pt-1 border-l border-line first:border-l-0 hover:bg-blush/60 transition ${out ? "bg-cream/40 text-ink/35" : ""}`}>
                    <div className="flex items-center gap-1">
                      <span className={`text-[12px] font-bold w-6 h-6 rounded-full flex items-center justify-center ${di === today ? "bg-bata text-cream" : ""}`}>{dt.getDate()}</span>
                      {mos.slice(0, 3).map((m, i) => <i key={i} className="w-1.5 h-1.5 rounded-full" style={{ background: MOMENT[m.type] }} title={m.label} />)}
                    </div>
                    {mos[0] && <div className="hidden sm:block text-[10px] font-semibold truncate" style={{ color: MOMENT[mos[0].type] }}>{mos[0].label}</div>}
                    {hidden > 0 && <div className="absolute bottom-0.5 left-1.5 text-[10px] font-bold text-ink/60">+{hidden} lagi</div>}
                  </button>
                );
              })}
            </div>
            <div className="absolute inset-x-0 top-[32px] sm:top-[46px] pointer-events-none">
              {shown.map((x, i) => {
                const left = diff(wsI, x.s), span = diff(x.s, x.e) + 1;
                const sty = STYLE[x.p.effectiveStatus] || STYLE.draft;
                return (
                  <motion.button key={x.p.id + w} onClick={(e) => { e.stopPropagation(); go(`/promo/${x.p.id}`); }}
                    initial={{ scaleX: 0, opacity: 0 }} animate={{ scaleX: 1, opacity: 1 }} transition={{ delay: 0.03 * i + w * 0.02, type: "spring", stiffness: 160, damping: 20 }}
                    style={{ left: `calc(${(left / 7) * 100}% + 3px)`, width: `calc(${(span / 7) * 100}% - 6px)`, top: x._lane * 20, background: sty.bg, color: sty.fg, transformOrigin: "left",
                      outline: sty.dashed ? "1px dashed #B42F27" : "none",
                      borderRadius: `${x.cutL ? 3 : 999}px ${x.cutR ? 3 : 999}px ${x.cutR ? 3 : 999}px ${x.cutL ? 3 : 999}px` }}
                    className="pointer-events-auto absolute h-[17px] px-2 text-[10.5px] font-bold truncate text-left flex items-center gap-1"
                    title={`${x.p.nama} · ${x.p.platformLabel}`}>
                    {conflictIds.has(x.p.id) && <AlertTriangle size={11} className="shrink-0" />}<span className="truncate">{x.p.nama}</span>
                  </motion.button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Timeline({ month, monthEnd, promos, moments, conflictIds, onDay }) {
  const ms = iso(month), me = iso(monthEnd);
  const days = monthEnd.getDate();
  const groups = {};
  promos.filter((p) => p.periodEnd >= ms && p.periodStart <= me).forEach((p) => { (groups[p.platformLabel] = groups[p.platformLabel] || []).push(p); });
  const today = iso(new Date());
  const colW = 34;
  return (
    <div className="card scroll-x">
      <div style={{ minWidth: 180 + days * colW }}>
        <div className="flex sticky top-0 bg-paper z-10 border-b border-line">
          <div className="w-[180px] shrink-0 px-3 py-2 text-[12px] font-bold text-ink/60">Platform</div>
          {Array.from({ length: days }).map((_, i) => {
            const di = iso(addDays(month, i)); const mo = moments.find((m) => di >= m.date && di <= (m.end || m.date));
            const wk = [0, 6].includes(addDays(month, i).getDay());
            return (
              <button key={i} onClick={() => onDay(di)} style={{ width: colW }} title={mo?.label}
                className={`shrink-0 py-1 text-center text-[11px] font-bold ${di === today ? "text-bata" : wk ? "text-ink/45" : "text-ink/70"}`}>
                {i + 1}{mo && <i className="block mx-auto mt-0.5 w-1.5 h-1.5 rounded-full" style={{ background: MOMENT[mo.type] }} />}
              </button>
            );
          })}
        </div>
        {Object.keys(groups).length === 0 && <div className="p-6 text-[14px] text-ink/60">Tidak ada promo di bulan ini dengan filter yang dipilih.</div>}
        {Object.entries(groups).map(([label, list], gi) => {
          const segs = list.map((p) => ({ p, s: p.periodStart < ms ? ms : p.periodStart, e: p.periodEnd > me ? me : p.periodEnd }));
          const n = lanes(segs, "s", "e");
          return (
            <div key={label} className="flex border-b border-line last:border-b-0">
              <div className="w-[180px] shrink-0 px-3 py-2 text-[13px] font-bold">{label}<div className="text-[11px] font-semibold text-ink/50">{list.length} promo</div></div>
              <div className="relative" style={{ width: days * colW, height: Math.max(n, 1) * 26 + 12 }}>
                {Array.from({ length: days }).map((_, i) => (
                  <div key={i} className={`absolute top-0 bottom-0 border-l border-line/60 ${iso(addDays(month, i)) === today ? "bg-bata/10" : ""}`} style={{ left: i * colW, width: colW }} />
                ))}
                {segs.map((x, i) => {
                  const sty = STYLE[x.p.effectiveStatus] || STYLE.draft;
                  return (
                    <motion.button key={x.p.id} onClick={() => go(`/promo/${x.p.id}`)}
                      initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: gi * 0.05 + i * 0.03, type: "spring", stiffness: 140, damping: 18 }}
                      className="absolute h-[22px] rounded-full px-2 text-[11px] font-bold truncate text-left flex items-center gap-1"
                      style={{ left: diff(ms, x.s) * colW + 2, width: (diff(x.s, x.e) + 1) * colW - 4, top: 6 + x._lane * 26, background: sty.bg, color: sty.fg,
                        transformOrigin: "left", outline: sty.dashed ? "1px dashed #B42F27" : "none" }}
                      title={`${x.p.nama} (${STATUS[x.p.effectiveStatus]})`}>
                      {conflictIds.has(x.p.id) && <AlertTriangle size={12} className="shrink-0" />}<span className="truncate">{x.p.nama}</span>
                    </motion.button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Agenda({ month, monthEnd, promos, moments, conflictIds }) {
  const ms = iso(month), me = iso(monthEnd);
  const list = promos.filter((p) => p.periodEnd >= ms && p.periodStart <= me).sort((a, b) => a.periodStart.localeCompare(b.periodStart));
  const mos = moments.filter((m) => (m.end || m.date) >= ms && m.date <= me);
  return (
    <section className="card p-4 md:hidden">
      <div className="font-extrabold mb-2">Agenda bulan ini</div>
      {mos.map((m, i) => (
        <div key={"m" + i} className="text-[13px] flex gap-2 py-1"><i className="mt-1.5 w-2 h-2 rounded-full shrink-0" style={{ background: MOMENT[m.type] }} />
          <span className="text-ink/60 w-24 shrink-0">{fmtDate(m.date).replace(/ \d{4}$/, "")}{m.end && m.end !== m.date ? `–${parse(m.end).getDate()}` : ""}</span><b>{m.label}</b></div>
      ))}
      <div className="mt-2 space-y-2">
        {list.map((p) => {
          const sty = STYLE[p.effectiveStatus] || STYLE.draft;
          return (
            <button key={p.id} onClick={() => go(`/promo/${p.id}`)} className="w-full text-left rounded-2xl px-3 py-2 border border-line bg-cream/50">
              <div className="flex items-center gap-2"><i className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: sty.bg }} /><b className="truncate">{p.nama}</b>
                {conflictIds.has(p.id) && <AlertTriangle size={13} className="text-bata shrink-0" />}</div>
              <div className="text-[12px] text-ink/60">{fmtDate(p.periodStart)} – {fmtDate(p.periodEnd)} · {p.platformLabel} · {STATUS[p.effectiveStatus]}</div>
            </button>
          );
        })}
        {!list.length && <div className="text-[13px] text-ink/60">Belum ada promo bulan ini.</div>}
      </div>
    </section>
  );
}
