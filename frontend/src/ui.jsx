import { useEffect, useRef, useState, createContext, useContext } from "react";
import { motion, AnimatePresence, animate, useReducedMotion } from "framer-motion";
import confetti from "canvas-confetti";
import { X, Check, AlertTriangle } from "lucide-react";
import { TONE_HEX, toneOf, rp, pc } from "./lib";

/* ---------- animated number ---------- */
export function CountUp({ value, format = (v) => Math.round(v).toLocaleString("id-ID"), duration = 0.7, className = "" }) {
  const ref = useRef(null);
  const prev = useRef(0);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (value == null || isNaN(value) || !isFinite(value)) { if (ref.current) ref.current.textContent = "–"; return; }
    if (reduce) { ref.current.textContent = format(value); prev.current = value; return; }
    const c = animate(prev.current, value, {
      duration, ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => { if (ref.current) ref.current.textContent = format(v); },
    });
    prev.current = value;
    return () => c.stop();
  }, [value]); // eslint-disable-line
  return <span ref={ref} className={`num ${className}`}>{format(value || 0)}</span>;
}

/* ---------- the cimol ball gauge (signature element) ---------- */
const MOUTH = {
  ok: "M34 60 Q50 74 66 60",
  warn: "M36 63 Q50 64 64 63",
  bad: "M35 67 Q50 55 65 67",
};
export function CimolBall({ score = 0, label = "", title, size = 104, hint }) {
  const tone = toneOf(label);
  const color = TONE_HEX[tone] || TONE_HEX.none;
  const level = Math.max(0, Math.min(100, score));
  const reduce = useReducedMotion();
  const fillY = 100 - level; // 0..100 viewbox
  const id = useRef(`c${Math.random().toString(36).slice(2, 8)}`).current;
  return (
    <div className="flex flex-col items-center text-center" title={hint}>
      <div className="text-[13px] font-bold text-ink/80 mb-1">{title}</div>
      <motion.svg width={size} height={size} viewBox="0 0 100 100" className="drop-shadow-[0_6px_0_rgba(33,33,33,.08)]"
        animate={reduce ? {} : { y: [0, -3, 0] }} transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}>
        <defs>
          <clipPath id={id}><circle cx="50" cy="50" r="44" /></clipPath>
          <radialGradient id={`${id}g`} cx="35%" cy="30%" r="75%">
            <stop offset="0%" stopColor="#fff" stopOpacity=".55" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx="50" cy="50" r="44" fill="#F6F1E7" stroke={color} strokeWidth="3" />
        <g clipPath={`url(#${id})`}>
          <motion.g initial={{ y: 100 }} animate={{ y: fillY }} transition={{ type: "spring", stiffness: 60, damping: 14 }}>
            <motion.path fill={color} fillOpacity=".9"
              d="M-100 4 Q-87.5 -4 -75 4 T-50 4 T-25 4 T0 4 T25 4 T50 4 T75 4 T100 4 T125 4 T150 4 T175 4 T200 4 V120 H-100 Z"
              animate={reduce ? {} : { x: [0, 50] }} transition={{ duration: 2.2, repeat: Infinity, ease: "linear" }} />
          </motion.g>
        </g>
        <circle cx="50" cy="50" r="44" fill={`url(#${id}g)`} />
        {/* face */}
        <motion.g animate={reduce ? {} : { scaleY: [1, 1, 0.1, 1, 1] }} transition={{ duration: 4.2, repeat: Infinity, times: [0, .46, .5, .54, 1] }}
          style={{ transformOrigin: "50px 42px" }}>
          <ellipse cx="38" cy="42" rx="4" ry="5" fill="#212121" />
          <ellipse cx="62" cy="42" rx="4" ry="5" fill="#212121" />
          <circle cx="39.3" cy="40.3" r="1.4" fill="#fff" />
          <circle cx="63.3" cy="40.3" r="1.4" fill="#fff" />
        </motion.g>
        {tone === "ok" && <><ellipse cx="29" cy="53" rx="5" ry="3" fill="#B42F27" opacity=".25" /><ellipse cx="71" cy="53" rx="5" ry="3" fill="#B42F27" opacity=".25" /></>}
        <motion.path d={MOUTH[tone] || MOUTH.warn} animate={{ d: MOUTH[tone] || MOUTH.warn }} transition={{ duration: 0.4 }}
          stroke="#212121" strokeWidth="3.4" fill="none" strokeLinecap="round" />
      </motion.svg>
      <div className="mt-1 text-[26px] font-extrabold leading-none" style={{ color }}><CountUp value={score} /></div>
      <AnimatePresence mode="wait">
        <motion.div key={label} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
          className="mt-1 text-[13px] font-bold" style={{ color }}>{label || "–"}</motion.div>
      </AnimatePresence>
    </div>
  );
}

/* compact ball for lists */
export function MiniBall({ label, score, title }) {
  const tone = toneOf(label);
  const c = TONE_HEX[tone];
  return (
    <div className="flex items-center gap-1.5" title={`${title}: ${label} (${score})`}>
      <svg width="22" height="22" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="44" fill={c} />
        <circle cx="38" cy="42" r="5" fill="#ECE4D4" /><circle cx="62" cy="42" r="5" fill="#ECE4D4" />
        <path d={MOUTH[tone] || MOUTH.warn} stroke="#ECE4D4" strokeWidth="6" fill="none" strokeLinecap="round" />
      </svg>
      <span className="text-[12px] font-semibold" style={{ color: c }}>{label}</span>
    </div>
  );
}

export function Badge({ label, big }) {
  const c = TONE_HEX[toneOf(label)];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-extrabold whitespace-nowrap ${big ? "px-4 py-1.5 text-[15px]" : "px-2.5 py-0.5 text-[12px]"}`}
      style={{ background: c, color: "#ECE4D4" }}>{label}</span>
  );
}

export function Title({ a, b, sub, right }) {
  return (
    <div className="flex items-end justify-between gap-3 mb-3">
      <div>
        <h2 className="title"><b>{a}</b> {b}</h2>
        {sub && <div className="text-[13px] font-semibold text-ink/60 mt-0.5 inline-block border-b-2 border-bata/70 pb-0.5">{sub}</div>}
      </div>
      {right}
    </div>
  );
}

/* bouncing cimol loader */
export function Loader({ text = "Menghitung…" }) {
  return (
    <div className="flex items-center gap-3 text-ink/60 text-[14px] font-semibold py-6 justify-center">
      <div className="flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="block w-3.5 h-3.5 rounded-full bg-bata"
            animate={{ y: [0, -10, 0], scaleX: [1, 0.9, 1.15, 1] }} transition={{ duration: 0.7, repeat: Infinity, delay: i * 0.12 }} />
        ))}
      </div>
      {text}
    </div>
  );
}

/* toast */
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = (msg, tone = "ok") => {
    const id = Math.random();
    setItems((x) => [...x, { id, msg, tone }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 3600);
  };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed z-[80] left-0 right-0 top-3 flex flex-col items-center gap-2 pointer-events-none px-3">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div key={t.id} initial={{ opacity: 0, y: -20, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -10 }}
              className="pointer-events-auto max-w-md rounded-2xl px-4 py-3 shadow-lg text-[14px] font-semibold flex items-start gap-2"
              style={{ background: t.tone === "bad" ? "#B42F27" : "#212121", color: "#ECE4D4" }} role="status">
              {t.tone === "bad" ? <AlertTriangle size={18} /> : <Check size={18} />}{t.msg}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}

/* bottom sheet / modal */
export function Sheet({ open, onClose, title, children, wide }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[70] flex items-end md:items-center justify-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
          <motion.div role="dialog" aria-label={title}
            initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }} transition={{ type: "spring", damping: 26, stiffness: 300 }}
            className={`relative bg-cream w-full ${wide ? "md:max-w-4xl" : "md:max-w-lg"} max-h-[90vh] overflow-y-auto rounded-t-[28px] md:rounded-[28px] p-5 safe-b`}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[18px] font-extrabold">{title}</h3>
              <button onClick={onClose} className="w-10 h-10 rounded-full hover:bg-blush flex items-center justify-center" aria-label="Tutup"><X size={20} /></button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function fireConfetti() {
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  const colors = ["#B42F27", "#ECE4D4", "#2F6B4A", "#E0BFB1", "#F6F1E7"];
  confetti({ particleCount: 90, spread: 75, origin: { y: 0.35 }, colors, shapes: ["circle"], scalar: 1.1 });
  setTimeout(() => confetti({ particleCount: 50, spread: 110, origin: { y: 0.3 }, colors, shapes: ["circle"] }), 220);
}

/* waterfall: harga → potongan → CM */
export function Waterfall({ unit }) {
  if (!unit) return null;
  const steps = [];
  steps.push({ label: "Harga normal", v: unit.listPrice, kind: "total" });
  if (unit.platformDiscount) steps.push({ label: "Diskon ditanggung platform", v: -unit.platformDiscount, kind: "info" });
  if (unit.merchantDiscount) steps.push({ label: "Diskon ditanggung kita", v: -unit.merchantDiscount, kind: "minus" });
  if (unit.packagingFeeToCustomer) steps.push({ label: "Biaya kemasan dari customer", v: unit.packagingFeeToCustomer, kind: "plus" });
  steps.push({ label: "Pendapatan kotor", v: unit.merchantGross, kind: "total" });
  (unit.feeLines || []).forEach((f) => f.amount && steps.push({ label: f.label, v: -f.amount, kind: "fee" }));
  (unit.costLines || []).forEach((f) => f.amount && steps.push({ label: f.label, v: -f.amount, kind: "fee" }));
  if (unit.adsCost) steps.push({ label: "Ads", v: -unit.adsCost, kind: "fee" });
  steps.push({ label: "HPP", v: -unit.hpp, kind: "minus" });
  if (unit.extraCost) steps.push({ label: unit.extraLabel || "Biaya mekanisme", v: -unit.extraCost, kind: "minus" });
  if (unit.variableCost) steps.push({ label: "Biaya variabel", v: -unit.variableCost, kind: "minus" });
  steps.push({ label: "Contribution margin", v: unit.cm, kind: "result" });
  const max = Math.max(unit.listPrice, unit.merchantGross, 1);
  let run = 0;
  return (
    <div className="space-y-1.5">
      {steps.map((s, i) => {
        let left, width;
        if (s.kind === "total" || s.kind === "result") { left = 0; width = Math.abs(s.v) / max; run = s.v; }
        else if (s.kind === "info") { left = (run + s.v) / max; width = -s.v / max; }
        else { const from = run; run = run + s.v; left = Math.min(from, run) / max; width = Math.abs(s.v) / max; }
        const color = s.kind === "result" ? (s.v > 0 ? "#2F6B4A" : "#B42F27") : s.kind === "total" ? "#212121" : s.kind === "fee" ? "#E0BFB1" : s.kind === "info" ? "transparent" : s.kind === "plus" ? "#2F6B4A" : "#B42F27";
        return (
          <div key={i} className="grid grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_auto] items-center gap-2 text-[13px]">
            <div className={`leading-tight break-words ${s.kind === "total" || s.kind === "result" ? "font-extrabold" : "text-ink/75"}`}>{s.label}</div>
            <div className="relative h-4 rounded-full bg-cream/70 overflow-hidden">
              <motion.div className="absolute top-0 bottom-0 rounded-full" style={{ background: color, border: s.kind === "info" ? "1.5px dashed #B42F27" : "none" }}
                initial={{ left: `${Math.max(0, left) * 100}%`, width: 0 }} animate={{ left: `${Math.max(0, left) * 100}%`, width: `${Math.max(width * 100, s.v ? 1 : 0)}%` }}
                transition={{ delay: i * 0.05, type: "spring", stiffness: 120, damping: 20 }} />
            </div>
            <div className={`num text-right ${s.kind === "result" ? "font-extrabold" : "font-semibold"}`} style={{ color: s.kind === "result" ? color : undefined }}>
              {s.kind === "info" ? `(${rp(-s.v)})` : rp(s.v)}
            </div>
          </div>
        );
      })}
      <div className="flex flex-wrap gap-3 pt-2 text-[11px] text-ink/60">
        <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-full bg-tint inline-block" /> Potongan platform</span>
        <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-full bg-bata inline-block" /> HPP & diskon kita</span>
        <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-full border border-dashed border-bata inline-block" /> Ditanggung platform (customer tetap hemat)</span>
      </div>
    </div>
  );
}

/* quadrant 2x2: x = margin score, y = menarik score */
export function Quadrant({ points = [], current }) {
  const W = 300, Hh = 220, pad = 22;
  const px = (m) => pad + 12 + (Math.max(0, Math.min(100, m)) / 100) * (W - pad * 2 - 24);
  const py = (a) => Hh - pad - 12 - (Math.max(0, Math.min(100, a)) / 100) * (Hh - pad * 2 - 24);
  return (
    <svg viewBox={`0 0 ${W} ${Hh}`} className="w-full h-auto" role="img" aria-label="Kuadran margin vs menarik">
      <rect x={pad} y={pad} width={(W - pad * 2) / 2} height={(Hh - pad * 2) / 2} fill="#F1DCD3" rx="10" />
      <rect x={W / 2} y={pad} width={(W - pad * 2) / 2} height={(Hh - pad * 2) / 2} fill="#2F6B4A" fillOpacity=".12" rx="10" />
      <rect x={pad} y={Hh / 2} width={(W - pad * 2) / 2} height={(Hh - pad * 2) / 2} fill="#21212110" rx="10" />
      <rect x={W / 2} y={Hh / 2} width={(W - pad * 2) / 2} height={(Hh - pad * 2) / 2} fill="#B8741A" fillOpacity=".12" rx="10" />
      <text x={pad + 8} y={pad + 16} fontSize="11" fontWeight="800" fill="#B42F27">Margin Trap</text>
      <text x={W - pad - 8} y={pad + 16} fontSize="11" fontWeight="800" fill="#2F6B4A" textAnchor="end">Star</text>
      <text x={pad + 8} y={Hh - pad - 8} fontSize="11" fontWeight="800" fill="#212121" opacity=".6">Avoid</text>
      <text x={W - pad - 8} y={Hh - pad - 8} fontSize="11" fontWeight="800" fill="#B8741A" textAnchor="end">Sleeper</text>
      <text x={W / 2} y={Hh - 4} fontSize="10" textAnchor="middle" fill="#212121" opacity=".6">Margin →</text>
      <text x="8" y={Hh / 2} fontSize="10" textAnchor="middle" fill="#212121" opacity=".6" transform={`rotate(-90 8 ${Hh / 2})`}>Menarik →</text>
      {points.map((p, i) => (
        <motion.circle key={p.id || i} cx={px(p.m)} cy={py(p.a)} r="5" fill="#B42F27" fillOpacity=".28"
          initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.02 * i }}>
          <title>{p.label}</title>
        </motion.circle>
      ))}
      {current && (
        <motion.g animate={{ x: px(current.m), y: py(current.a) }} initial={false} transition={{ type: "spring", stiffness: 140, damping: 14 }}>
          <motion.circle r="15" fill="#B42F27" fillOpacity=".18" animate={{ scale: [1, 1.5, 1] }} transition={{ duration: 1.8, repeat: Infinity }} />
          <circle r="9" fill="#B42F27" stroke="#ECE4D4" strokeWidth="2.5" />
        </motion.g>
      )}
    </svg>
  );
}

export function Empty({ title, text, action }) {
  return (
    <div className="card p-8 text-center">
      <motion.div className="mx-auto mb-3 w-16 h-16" animate={{ rotate: [0, -8, 8, 0] }} transition={{ duration: 2.4, repeat: Infinity }}>
        <svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" fill="#E0BFB1" /><circle cx="38" cy="44" r="5" fill="#212121" /><circle cx="62" cy="44" r="5" fill="#212121" /><circle cx="50" cy="64" r="5" fill="#212121" /></svg>
      </motion.div>
      <div className="font-extrabold text-[17px]">{title}</div>
      <div className="text-[14px] text-ink/65 mt-1 max-w-sm mx-auto">{text}</div>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Stat({ label, value, format, sub, tone }) {
  return (
    <div className="card p-3.5">
      <div className="text-[12px] font-semibold text-ink/60 leading-tight">{label}</div>
      <div className="text-[24px] font-extrabold leading-tight mt-1" style={{ color: tone ? TONE_HEX[tone] : "#B42F27" }}>
        {typeof value === "number" ? <CountUp value={value} format={format} /> : value}
      </div>
      {sub && <div className="text-[12px] text-ink/55 mt-0.5">{sub}</div>}
    </div>
  );
}

export const fmtRp = (v) => rp(v);
export const fmtPc = (v) => pc(v);
