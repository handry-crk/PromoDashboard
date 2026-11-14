import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, CalendarDays, Calculator, RotateCcw, AlertTriangle, Check } from "lucide-react";
import { api } from "../lib";
import { useToast, CountUp } from "../ui";
import { go } from "../App";

const STORE = "crk_bot_chat";
const SUGGEST = [
  "Kapan promo AOV mozza di GoFood 2 minggu bulan depan?",
  "Kapan promo isi jam sepi di gerobak Bandung?",
  "Shopee frozen 3 hari bulan Desember",
  "Kapan bazaar weekend yang paling bagus?",
];

export function BotFace({ size = 40, talking = false }) {
  return (
    <motion.svg width={size} height={size} viewBox="0 0 100 100" animate={talking ? { rotate: [0, -6, 6, 0] } : { y: [0, -2, 0] }}
      transition={{ duration: talking ? 0.6 : 2.4, repeat: Infinity }} aria-hidden>
      <line x1="50" y1="14" x2="50" y2="4" stroke="#212121" strokeWidth="3" strokeLinecap="round" />
      <motion.circle cx="50" cy="4" r="5" fill="#B42F27" animate={{ opacity: [1, 0.35, 1] }} transition={{ duration: 1.2, repeat: Infinity }} />
      <circle cx="50" cy="56" r="40" fill="#ECE4D4" stroke="#B42F27" strokeWidth="4" />
      <path d="M14 66 A40 40 0 0 0 86 66 Z" fill="#B42F27" opacity=".9" />
      <motion.g animate={{ scaleY: [1, 1, 0.1, 1] }} transition={{ duration: 3.6, repeat: Infinity, times: [0, 0.9, 0.95, 1] }} style={{ transformOrigin: "50px 46px" }}>
        <ellipse cx="37" cy="46" rx="5" ry="6" fill="#212121" /><ellipse cx="63" cy="46" rx="5" ry="6" fill="#212121" />
      </motion.g>
      <path d="M38 60 Q50 70 62 60" stroke="#212121" strokeWidth="3.5" fill="none" strokeLinecap="round" />
    </motion.svg>
  );
}

function rich(text) {
  return (text || "").split("\n\n").map((para, i) => (
    <p key={i} className={i ? "mt-2" : ""}>
      {para.split(/(\*\*[^*]+\*\*)/g).map((s, j) => (s.startsWith("**") ? <b key={j}>{s.slice(2, -2)}</b> : <span key={j}>{s}</span>))}
    </p>
  ));
}

function ScoreRing({ score, size = 54 }) {
  const r = 22, c = 2 * Math.PI * r;
  const col = score >= 75 ? "#2F6B4A" : score >= 50 ? "#B8741A" : "#B42F27";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 54 54" width={size} height={size}>
        <circle cx="27" cy="27" r={r} fill="none" stroke="#E0BFB1" strokeWidth="5" />
        <motion.circle cx="27" cy="27" r={r} fill="none" stroke={col} strokeWidth="5" strokeLinecap="round" transform="rotate(-90 27 27)"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - score / 100) }} transition={{ duration: 0.9, ease: "easeOut" }} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-[15px] font-extrabold" style={{ color: col }}><CountUp value={score} /></div>
    </div>
  );
}

function Heat({ heat, picks }) {
  if (!heat?.length) return null;
  const pickSet = new Set(picks.map((p) => p.start));
  const first = heat[0].date, last = heat[heat.length - 1].date;
  return (
    <div className="mt-3">
      <div className="text-[11px] text-ink/55 font-semibold mb-1">Skor tiap tanggal mulai ({first.slice(8)}/{first.slice(5, 7)} – {last.slice(8)}/{last.slice(5, 7)})</div>
      <div className="flex flex-wrap gap-[2px]">
        {heat.map((h, i) => {
          const col = h.score >= 75 ? "#2F6B4A" : h.score >= 50 ? "#B8741A" : "#E0BFB1";
          return (
            <motion.i key={h.date} title={`${h.date}: ${h.score}`} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: i * 0.004 }}
              className="block w-[9px] h-[18px] rounded-[3px]" style={{ background: col, opacity: 0.35 + (h.score / 100) * 0.65, outline: pickSet.has(h.date) ? "2px solid #212121" : "none" }} />
          );
        })}
      </div>
    </div>
  );
}

function RecCard({ rec, ctx, i, onApply }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.1 }}
      className={`rounded-2xl border px-3 py-3 ${i === 0 ? "border-bata bg-blush/60" : "border-line bg-paper"}`}>
      <div className="flex items-center gap-3">
        <ScoreRing score={rec.score} />
        <div className="min-w-0">
          <div className={`text-[11px] font-extrabold ${i === 0 ? "text-bata" : "text-ink/55"}`}>{rec.label}{rec.verdict ? ` · ${rec.verdict}` : ""}</div>
          <div className="font-extrabold text-[16px] leading-tight">{rec.range}</div>
          <div className="text-[12px] text-ink/60">Mulai {rec.startDay}</div>
        </div>
      </div>
      <ul className="mt-2 space-y-0.5 text-[13px]">
        {rec.reasons.map((r, k) => <li key={k} className="flex gap-1.5"><Check size={14} className="text-ok mt-0.5 shrink-0" />{r}</li>)}
        {rec.cautions.map((r, k) => <li key={"c" + k} className="flex gap-1.5 text-bata"><AlertTriangle size={14} className="mt-0.5 shrink-0" />{r}</li>)}
      </ul>
      <div className="flex flex-wrap gap-2 mt-2">
        <button className="btn-primary !min-h-[36px] !text-[13px]" onClick={() => onApply(rec)}><Calculator size={15} />Pakai di kalkulator</button>
        <button className="btn-soft !min-h-[36px] !text-[13px]" onClick={() => { sessionStorage.setItem("crk_cal_month", rec.start.slice(0, 7)); go("/kalender"); }}><CalendarDays size={15} />Lihat di kalender</button>
      </div>
    </motion.div>
  );
}

export default function Assistant({ st }) {
  const toast = useToast();
  const [msgs, setMsgs] = useState(() => { try { return JSON.parse(sessionStorage.getItem(STORE) || "null")?.msgs || []; } catch { return []; } });
  const [ctx, setCtx] = useState(() => { try { return JSON.parse(sessionStorage.getItem(STORE) || "null")?.ctx || {}; } catch { return {}; } });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const promos = st.promos.filter((p) => !["rejected", "done"].includes(p.effectiveStatus));

  useEffect(() => { sessionStorage.setItem(STORE, JSON.stringify({ msgs: msgs.slice(-30), ctx })); endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, ctx]);

  const ask = async ({ message = "", set, promoId, prefill, show }) => {
    if (busy) return;
    const shown = show ?? message;
    if (shown) setMsgs((m) => [...m, { from: "me", text: shown }]);
    setBusy(true);
    try {
      const t0 = Date.now();
      const r = await api("/bot", { method: "POST", body: { message, context: ctx, set, promoId, prefill } });
      await new Promise((ok) => setTimeout(ok, Math.max(0, 650 - (Date.now() - t0))));
      setCtx(r.context);
      setMsgs((m) => [...m, { from: "bot", text: r.reply, result: r.result, chips: r.chips, ctx: r.context }]);
    } catch (e) { setMsgs((m) => [...m, { from: "bot", text: e.message, error: true }]); }
    finally { setBusy(false); }
  };

  // opened from calculator / promo detail
  useEffect(() => {
    let pre = null;
    try { pre = JSON.parse(sessionStorage.getItem("crk_bot_prefill") || "null"); sessionStorage.removeItem("crk_bot_prefill"); } catch { /* */ }
    if (pre) { setCtx({}); setMsgs([]); setTimeout(() => ask({ prefill: pre, show: pre._question || "Kapan sebaiknya promo ini dijalankan?" }), 50); }
  }, []); // eslint-disable-line

  const apply = (rec, c) => {
    const p = {
      periodStart: rec.start, periodEnd: rec.end, _fromCalendar: true,
      ...(c.platformProfileId ? { platformProfileId: c.platformProfileId } : {}), ...(c.objective ? { objective: c.objective } : {}),
      ...(c.areas ? { areas: c.areas } : {}),
    };
    if (c.excludeId) {
      // existing promo: open it in the calculator with new dates
      sessionStorage.setItem("crk_date_patch", JSON.stringify({ periodStart: rec.start, periodEnd: rec.end }));
      go(`/hitung/${c.excludeId}`);
      toast("Tanggal baru diisi — simpan untuk menerapkan");
      return;
    }
    if (c.products?.length) p.items = c.products.slice(0, 2).map((id) => ({ productId: id, qty: 1 }));
    sessionStorage.setItem("crk_prefill", JSON.stringify(p));
    go("/hitung");
  };

  const reset = () => { setMsgs([]); setCtx({}); sessionStorage.removeItem(STORE); };

  return (
    <div className="max-w-3xl mx-auto flex flex-col min-h-[calc(100vh-160px)]">
      <div className="flex items-center gap-3 mb-3">
        <BotFace size={52} talking={busy} />
        <div className="flex-1">
          <h2 className="title"><b>Asisten</b> timing promo</h2>
          <div className="text-[13px] text-ink/60">Tanya kapan promo sebaiknya jalan. Saya baca momen, pola hari, jadwal promo lain, dan hasil promo sebelumnya.</div>
        </div>
        {!!msgs.length && <button onClick={reset} className="btn-soft !min-h-[38px] !px-3" aria-label="Mulai percakapan baru"><RotateCcw size={16} /></button>}
      </div>

      <div className="flex-1 space-y-3 pb-24 md:pb-16">
        {!msgs.length && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-4">
            <div className="font-bold mb-2">Contoh pertanyaan</div>
            <div className="flex flex-wrap gap-2">
              {SUGGEST.map((s) => <button key={s} onClick={() => ask({ message: s })} className="text-left rounded-2xl border border-line bg-white/60 px-3 py-2 text-[14px] hover:border-bata">{s}</button>)}
            </div>
            {!!promos.length && (
              <div className="mt-4">
                <div className="font-bold mb-2">Atau cek promo yang sudah ada</div>
                <div className="flex flex-wrap gap-2">
                  {promos.slice(0, 8).map((p) => (
                    <button key={p.id} onClick={() => ask({ promoId: p.id, show: `Cek timing ${p.nama}` })} className="pill !py-1.5 !text-[13px] hover:bg-blush">{p.nama}</button>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}

        <AnimatePresence initial={false}>
          {msgs.map((m, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className={`flex gap-2 ${m.from === "me" ? "justify-end" : ""}`}>
              {m.from === "bot" && <div className="mt-1"><BotFace size={30} /></div>}
              <div className={`max-w-[88%] ${m.from === "me" ? "bg-bata text-cream rounded-[20px] rounded-br-md px-4 py-2.5" : "bg-paper border border-line rounded-[20px] rounded-tl-md px-4 py-3"} text-[14.5px] leading-relaxed`}>
                {m.from === "me" ? m.text : rich(m.text)}
                {m.result && (
                  <div className="mt-3 space-y-2">
                    {m.result.check && <RecCard rec={m.result.check} ctx={m.ctx} i={0} onApply={(r) => apply(r, m.ctx)} />}
                    {m.result.recommendations.map((r, k) => <RecCard key={r.start} rec={r} ctx={m.ctx} i={m.result.check ? k + 1 : k} onApply={(rr) => apply(rr, m.ctx)} />)}
                    <Heat heat={m.result.heat} picks={m.result.recommendations} />
                  </div>
                )}
                {m.chips?.length > 0 && i === msgs.length - 1 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {m.chips.map((c) => (
                      <button key={c.label} onClick={() => ask({ message: c.message || "", set: c.set, show: c.label })}
                        className="rounded-full border border-bata/60 text-bata px-3 min-h-[34px] text-[13px] font-semibold hover:bg-blush">{c.label}</button>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {busy && (
          <div className="flex gap-2 items-center"><BotFace size={30} talking />
            <div className="bg-paper border border-line rounded-[20px] px-4 py-3 flex gap-1.5">
              {[0, 1, 2].map((k) => <motion.span key={k} className="w-2.5 h-2.5 rounded-full bg-bata block" animate={{ y: [0, -6, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: k * 0.12 }} />)}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { ask({ message: text.trim() }); setText(""); } }}
        className="sticky bottom-20 lg:bottom-4 flex gap-2 bg-cream/90 backdrop-blur py-2">
        <input className="field !rounded-full" placeholder="Tanya, mis. kapan promo GoFood 2 minggu bulan depan?" value={text} onChange={(e) => setText(e.target.value)} aria-label="Pertanyaan" />
        <button className="btn-primary !px-4" disabled={busy || !text.trim()} aria-label="Kirim"><Send size={18} /></button>
      </form>
    </div>
  );
}
