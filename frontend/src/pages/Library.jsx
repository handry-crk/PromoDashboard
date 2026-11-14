import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Columns3, Download } from "lucide-react";
import { rp, pc, STATUS, fmtDate, getToken } from "../lib";
import { Title, MiniBall, Badge, Empty, Sheet } from "../ui";

export default function Library({ st }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [plat, setPlat] = useState("");
  const [sel, setSel] = useState([]);
  const [cmp, setCmp] = useState(false);
  const profs = Object.fromEntries(st.profiles.map((p) => [p.id, p]));
  const list = useMemo(() => st.promos.filter((p) =>
    (!q || `${p.nama} ${p.kode}`.toLowerCase().includes(q.toLowerCase())) &&
    (!status || p.effectiveStatus === status) && (!plat || p.platformProfileId === plat)), [st.promos, q, status, plat]);
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 3 ? s : [...s, id]));
  const canExport = st.user.isAdmin || ["head", "finance"].includes(st.user.perm);

  return (
    <div>
      <Title a="Library" b="promo" sub={`${st.promos.length} promo tersimpan`}
        right={canExport && <a className="btn-soft" href={`/api/export/promos.csv?token=${getToken()}`}><Download size={16} />Export</a>} />
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
        <input className="field" placeholder="Cari nama atau kode" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari promo" />
        <select className="field" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter status">
          <option value="">Semua status</option>{Object.entries(STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <select className="field" value={plat} onChange={(e) => setPlat(e.target.value)} aria-label="Filter platform">
          <option value="">Semua platform</option>{st.profiles.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </div>
      {!list.length && <Empty title="Belum ada promo" text="Promo yang disimpan dari kalkulator atau rekomendasi muncul di sini." action={st.user.isAdmin || st.user.perm !== "viewer" ? <a href="#/hitung" className="btn-primary">Hitung promo</a> : null} />}
      <div className="grid md:grid-cols-2 gap-3">
        {list.map((p, i) => {
          const entries = Object.entries(p.summary || {});
          return (
            <motion.div key={p.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * 0.03 }}
              className={`card p-4 ${sel.includes(p.id) ? "ring-2 ring-bata" : ""}`}>
              <div className="flex items-start justify-between gap-2">
                <a href={`#/promo/${p.id}`} className="min-w-0">
                  <div className="font-extrabold text-[16px] truncate hover:text-bata">{p.nama}</div>
                  <div className="text-[12px] text-ink/60">{p.kode} · {profs[p.platformProfileId]?.label} · {fmtDate(p.periodStart)}</div>
                </a>
                <span className="pill shrink-0">{p.waitingActual ? "Isi hasil aktual" : STATUS[p.effectiveStatus]}</span>
              </div>
              {entries.map(([a, s]) => (
                <div key={a} className="mt-2.5 rounded-2xl bg-cream/60 px-3 py-2">
                  <div className="flex justify-between text-[12px] font-semibold text-ink/60"><span>{a === "bandung" ? "Bandung Raya" : "Jabodetabek"}</span>
                    <span className="num">{rp(s.listPrice)} → {rp(s.customerPays)}{s.cm != null ? ` · CM ${rp(s.cm)} (${pc(s.cmPct)})` : ` · hemat ${pc(s.discountPct, 0)}`}</span></div>
                  <div className="flex flex-wrap gap-3 mt-1 items-center">
                    <MiniBall title="Sehat" label={s.health.label} score={s.health.score} />
                    <MiniBall title="Margin" label={s.margin.label} score={s.margin.score} />
                    <MiniBall title="Menarik" label={s.menarik.label} score={s.menarik.score} />
                    <Badge label={s.gate} />
                  </div>
                </div>
              ))}
              <label className="mt-2 flex items-center gap-2 text-[13px] font-semibold text-ink/70 min-h-[36px]">
                <input type="checkbox" className="w-4 h-4 accent-bata" checked={sel.includes(p.id)} onChange={() => toggle(p.id)} />Bandingkan
              </label>
            </motion.div>
          );
        })}
      </div>
      <AnimatePresence>
        {sel.length > 1 && (
          <motion.div initial={{ y: 80 }} animate={{ y: 0 }} exit={{ y: 80 }} className="fixed bottom-20 lg:bottom-6 inset-x-0 z-40 flex justify-center px-4">
            <button className="btn-primary shadow-xl" onClick={() => setCmp(true)}><Columns3 size={18} />Bandingkan {sel.length} promo</button>
          </motion.div>
        )}
      </AnimatePresence>
      <Sheet open={cmp} onClose={() => setCmp(false)} title="Bandingkan promo" wide>
        <Compare promos={st.promos.filter((p) => sel.includes(p.id))} profs={profs} viewer={!st.user.isAdmin && st.user.perm === "viewer"} />
      </Sheet>
    </div>
  );
}

function Compare({ promos, profs, viewer }) {
  const cols = promos.flatMap((p) => Object.entries(p.summary || {}).slice(0, 1).map(([a, s]) => ({ p, a, s })));
  const rows = [
    ["Platform", (c) => profs[c.p.platformProfileId]?.label],
    ["Harga normal", (c) => rp(c.s.listPrice)],
    ["Customer bayar", (c) => rp(c.s.customerPays)],
    ["Hemat", (c) => pc(c.s.discountPct), (c) => c.s.discountPct],
    ["CM per unit", (c) => rp(c.s.cm), (c) => c.s.cm],
    ["CM %", (c) => pc(c.s.cmPct), (c) => c.s.cmPct],
    ["Potongan platform", (c) => (c.s.effectiveTakeRate == null ? "0%" : pc(c.s.effectiveTakeRate)), (c) => -(c.s.effectiveTakeRate || 0)],
    ["Skor Sehat", (c) => `${c.s.health.score} · ${c.s.health.label}`, (c) => c.s.health.score],
    ["Skor Margin", (c) => `${c.s.margin.score} · ${c.s.margin.label}`, (c) => c.s.margin.score],
    ["Skor Menarik", (c) => `${c.s.menarik.score} · ${c.s.menarik.label}`, (c) => c.s.menarik.score],
    ["Contribution Target", (c) => rp(c.s.targetContribution), (c) => c.s.targetContribution],
    ["Gate", (c) => c.s.gate],
  ].filter(([l]) => !viewer || !["CM per unit", "CM %", "Potongan platform", "Contribution Target"].includes(l));
  return (
    <div className="scroll-x">
      <table className="w-full min-w-[520px]">
        <thead><tr><th className="th rounded-tl-xl"></th>{cols.map((c, i) => <th key={i} className={`th ${i === cols.length - 1 ? "rounded-tr-xl" : ""}`}>{c.p.nama}</th>)}</tr></thead>
        <tbody>{rows.map(([l, f, score]) => {
          const best = score ? Math.max(...cols.map(score)) : null;
          return <tr key={l}><td className="td text-ink/65 text-[13px]">{l}</td>{cols.map((c, i) => (
            <td key={i} className={`td num ${score && score(c) === best ? "font-extrabold text-ok" : ""}`}>{f(c)}</td>
          ))}</tr>;
        })}</tbody>
      </table>
    </div>
  );
}
