import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Pencil, Send, Check, Undo2, X, Trash2, MessageCircle, RefreshCw } from "lucide-react";
import { api, rp, pc, num, STATUS, fmtDate } from "../lib";
import { CimolBall, Badge, Waterfall, Loader, useToast, fireConfetti, Sheet } from "../ui";
import { NumInput } from "./Calculator";
import { go } from "../App";

const FLOW = ["draft", "review_finance", "review_head", "approved", "running", "done"];
const ACT = { run_direct: "Dijalankan langsung oleh Manager", create: "Dibuat", recalc: "Dihitung ulang", submit: "Diajukan ke Finance", review_ok: "Lolos review Finance", return: "Dikembalikan Finance",
  approve: "Disetujui Marketing Manager", reject: "Ditolak", actual_input: "Hasil aktual diisi", edit: "Diubah" };

export default function PromoDetail({ st, reload, id }) {
  const toast = useToast();
  const [p, setP] = useState(null);
  const [area, setArea] = useState(null);
  const [dlg, setDlg] = useState(null);
  const [note, setNote] = useState("");
  const [comment, setComment] = useState("");
  const [act, setAct] = useState({});
  const u = st.user;
  const can = (...r) => u.isAdmin || r.includes(u.perm);

  const load = async () => {
    try { const d = await api(`/promos/${id}`); setP(d); setArea((a) => a || Object.keys(d.results || {})[0]); setAct(d.actual || {}); }
    catch (e) { toast(e.message, "bad"); go("/library"); }
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line
  if (!p) return <Loader text="Membuka promo…" />;

  const o = p.results?.[area];
  const prof = st.profiles.find((x) => x.id === p.platformProfileId);
  const step = p.status === "rejected" ? -1 : FLOW.indexOf(p.waitingActual ? "running" : p.effectiveStatus);

  const call = async (path, body, msg, celebrate) => {
    try { const d = await api(`/promos/${id}/${path}`, { method: "POST", body }); setP(d); setDlg(null); setNote(""); toast(msg); reload(); if (celebrate) fireConfetti(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const recalc = async () => {
    try { const d = await api(`/promos/${id}`, { method: "PUT", body: {} }); setP(d); toast("Dihitung ulang dengan HPP & biaya terbaru"); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const del = async () => { if (!confirm("Hapus promo ini?")) return; try { await api(`/promos/${id}`, { method: "DELETE" }); reload(); go("/library"); } catch (e) { toast(e.message, "bad"); } };

  const sm = p.targets || p.summary?.[area];
  const ad = p.actual?.achievementDetail;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[13px] text-ink/60 font-semibold">{p.kode} · {prof?.label} · {st.mechanisms[p.mechanism]} · {st.objectives[p.objective]}</div>
          <h2 className="text-[26px] font-extrabold leading-tight">{p.nama}</h2>
          <div className="text-[13px] text-ink/60">{fmtDate(p.periodStart)} – {fmtDate(p.periodEnd)} · dibuat {p.createdBy}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {can("planner", "channel_pic", "head") && p.status !== "done" && <a href={`#/hitung/${p.id}`} className="btn-ghost"><Pencil size={16} />Edit</a>}
          {can("planner", "channel_pic", "head") && p.status === "draft" && <button className="btn-primary" onClick={() => call("submit", {}, "Diajukan ke Finance")}><Send size={16} />Ajukan review</button>}
          {can("finance") && p.status === "review_finance" && <button className="btn-primary" onClick={() => setDlg("review")}><Check size={16} />Review margin</button>}
          {can("head") && p.status === "review_head" && <button className="btn-primary" onClick={() => setDlg("approve")}><Check size={16} />Keputusan</button>}
          {u.isAdmin && <button className="btn-soft" onClick={del} aria-label="Hapus promo"><Trash2 size={16} /></button>}
        </div>
      </div>

      {/* status flow */}
      <div className="card p-4">
        {p.status === "rejected" ? (
          <div className="text-bata font-bold">Ditolak{p.rejectNote ? `: ${p.rejectNote}` : ""}</div>
        ) : (
          <div className="relative">
            <div className="absolute left-3 right-3 top-[13px] h-1 rounded-full bg-line" />
            <motion.div className="absolute left-3 top-[13px] h-1 rounded-full bg-bata" initial={{ width: 0 }} animate={{ width: `calc(${(Math.max(step, 0) / (FLOW.length - 1)) * 100}% - ${(Math.max(step, 0) / (FLOW.length - 1)) * 24}px)` }} transition={{ duration: 0.8 }} />
            <div className="relative flex justify-between">
              {FLOW.map((s, i) => (
                <div key={s} className="flex flex-col items-center w-14 text-center">
                  <motion.div className={`w-7 h-7 rounded-full border-[3px] ${i <= step ? "bg-bata border-bata" : "bg-paper border-line"} flex items-center justify-center`}
                    initial={{ scale: 0.6 }} animate={{ scale: i === step ? [1, 1.2, 1] : 1 }} transition={{ delay: i * 0.08, duration: i === step ? 1.4 : 0.3, repeat: i === step ? Infinity : 0, repeatDelay: 1 }}>
                    {i < step && <Check size={14} className="text-cream" />}
                  </motion.div>
                  <div className={`text-[11px] mt-1 font-semibold ${i === step ? "text-bata" : "text-ink/55"}`}>{STATUS[s]}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {p.waitingActual && <div className="mt-3 text-[14px] font-semibold text-warn">Periode promo sudah selesai — isi hasil aktual di bawah.</div>}
      </div>

      {p.stale && (
        <div className="card p-3 flex items-center justify-between gap-3 border-warn">
          <div className="text-[14px] font-semibold text-warn">HPP atau biaya platform berubah sejak promo ini dihitung.</div>
          {p.status !== "done" && can("planner", "channel_pic", "head") && <button className="btn-soft" onClick={recalc}><RefreshCw size={16} />Hitung ulang</button>}
        </div>
      )}

      {Object.keys(p.results || {}).length > 1 && (
        <div className="flex gap-2">{Object.keys(p.results).map((a) => (
          <button key={a} onClick={() => setArea(a)} className={`px-4 h-10 rounded-full font-semibold border ${area === a ? "bg-bata text-cream border-bata" : "border-line"}`}>{a === "bandung" ? "Bandung Raya" : "Jabodetabek"}</button>
        ))}</div>
      )}

      {o && (
        <div className="grid lg:grid-cols-2 gap-4">
          <section className="card p-4">
            <div className="grid grid-cols-3"><CimolBall title="Sehat" score={o.health.score} label={o.health.label} />
              <CimolBall title="Margin" score={o.margin.score} label={o.margin.label} /><CimolBall title="Menarik" score={o.menarik.score} label={o.menarik.label} /></div>
            <div className="mt-3 flex gap-2 items-center"><Badge big label={o.gate.status} /><span className="pill">{o.quadrant}</span></div>
            <p className="mt-3 text-[15px]">{o.takeaway}</p>
            {!!o.gate.conditions.length && <ul className="mt-2 text-[13px] text-ink/70 space-y-1">{o.gate.conditions.map((c) => <li key={c}>● {c}</li>)}</ul>}
          </section>
          {o.unit ? <section className="card p-4"><div className="font-extrabold mb-2">Unit economics</div><Waterfall unit={o.unit} /></section>
            : <section className="card p-4">
                <div className="font-extrabold mb-2">Harga promo</div>
                <div className="text-[15px] num">Harga normal <b>{rp(o.price.listPrice)}</b> → harga promo <b>{rp(o.price.customerPays)}</b></div>
                <div className="text-[14px] text-ink/70 num">Customer hemat {rp(o.price.discountTotal)} ({pc(o.price.discountPct, 0)})</div>
                <p className="text-[12px] text-ink/55 mt-2">Rincian HPP dan margin hanya untuk tim promo, Finance, dan Marketing Manager.</p>
              </section>}
        </div>
      )}

      {/* planned vs actual */}
      {(p.effectiveStatus === "running" || p.status === "done" || p.waitingActual) && (
        <section className="card p-4">
          <div className="font-extrabold text-[17px] mb-1"><b>Planned</b> vs Actual</div>
          {Object.keys(p.summary || {}).length > 1 && <div className="text-[12px] text-ink/55 mb-3">Target = gabungan semua area.</div>}
          {ad && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              {[["Unit", sm?.targetUnits, p.actual.units, ad.units], ["Tambahan revenue", sm?.targetIncRevenue, p.actual.incRevenue, ad.incRevenue, true],
                ["Take rate", sm?.targetTakeRate, p.actual.takeRate, ad.takeRate, false, "%"], ["Contribution", sm?.targetContribution, p.actual.contribution, ad.contribution, true]]
                .filter(([l]) => u.isAdmin || u.perm !== "viewer" || !["Tambahan revenue", "Contribution"].includes(l)).map(([l, t, a, r, money, suf]) => (
                <div key={l} className="rounded-2xl bg-cream/70 p-3">
                  <div className="text-[12px] font-semibold text-ink/60">{l}</div>
                  <div className="text-[13px] num">Target {money ? rp(t) : `${num(t)}${suf || ""}`}</div>
                  <div className="text-[15px] font-extrabold num">Actual {a == null || a === "" ? "–" : money ? rp(a) : `${num(a)}${suf || ""}`}</div>
                  <div className="mt-1.5 h-2 rounded-full bg-paper overflow-hidden">
                    <motion.div className="h-full rounded-full" style={{ background: (r || 0) >= 1 ? "#2F6B4A" : (r || 0) >= 0.8 ? "#B8741A" : "#B42F27" }}
                      initial={{ width: 0 }} animate={{ width: `${Math.min((r || 0) * 100, 100)}%` }} />
                  </div>
                  <div className="text-[12px] font-bold mt-1">{r == null ? "–" : `${pc(r, 0)} achievement`}</div>
                </div>
              ))}
            </div>
          )}
          {p.actual?.learningHeadline && <div className="mb-3"><div className="italic font-extrabold">{p.actual.learningHeadline}</div><div className="text-[14px]">{p.actual.learning}</div>
            {p.actual.nextAction && <div className="text-[14px] mt-1"><b>Next action:</b> {p.actual.nextAction}</div>}</div>}
          {p.status !== "done" && can("planner", "channel_pic", "head", "finance") && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[["units", "Unit terjual"], ["orders", "Order/transaksi"], ["revenue", "Revenue", "Rp"], ["incRevenue", "Tambahan revenue vs baseline", "Rp"],
                ["takeRate", "Take rate", null, "%"], ["merchantDiscount", "Diskon ditanggung kita", "Rp"], ["platformFees", "Potongan platform (settlement)", "Rp"],
                ["fixedCost", "Biaya tetap aktual", "Rp"], ["repeat30d", "Repeat 30D", null, "%"]].map(([k, l, pre, suf]) => (
                <div key={k}><label className="lbl">{l}</label><NumInput prefix={pre || undefined} suffix={suf || undefined} value={act[k] ?? ""} onChange={(v) => setAct({ ...act, [k]: v })} /></div>
              ))}
              <div className="col-span-2 md:col-span-4 grid md:grid-cols-3 gap-3">
                <input className="field italic" placeholder="Learning headline (English), mis. Bundle beats discount" value={act.learningHeadline || ""} onChange={(e) => setAct({ ...act, learningHeadline: e.target.value })} />
                <input className="field" placeholder="Penyebab → dampak → implikasi" value={act.learning || ""} onChange={(e) => setAct({ ...act, learning: e.target.value })} />
                <input className="field" placeholder="Next action" value={act.nextAction || ""} onChange={(e) => setAct({ ...act, nextAction: e.target.value })} />
              </div>
              <div className="col-span-2 md:col-span-4 flex flex-wrap gap-2">
                <button className="btn-ghost" onClick={() => call("actual", act, "Hasil aktual tersimpan")}>Simpan hasil</button>
                <button className="btn-primary" onClick={() => call("actual", { ...act, finish: true }, "Promo ditutup — hasilnya masuk Data belajar", true)}>Simpan & tutup promo</button>
              </div>
            </div>
          )}
        </section>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <section className="card p-4">
          <div className="font-extrabold mb-2">Riwayat</div>
          <ol className="relative border-l-2 border-line ml-2 space-y-3">
            {p.timeline.map((t, i) => (
              <motion.li key={i} className="ml-4" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                <span className="absolute -left-[7px] mt-1.5 w-3 h-3 rounded-full bg-bata" />
                <div className="text-[14px] font-semibold">{ACT[t.action] || t.action} <span className="text-ink/55 font-normal">· {t.byName}</span></div>
                <div className="text-[12px] text-ink/55">{new Date(t.at).toLocaleString("id-ID")}</div>
                {t.note && <div className="text-[13px] mt-0.5">{t.note}</div>}
              </motion.li>
            ))}
          </ol>
        </section>
        <section className="card p-4">
          <div className="font-extrabold mb-2 flex items-center gap-2"><MessageCircle size={18} className="text-bata" />Komentar</div>
          <div className="space-y-2 mb-3">
            {p.comments.map((c, i) => (
              <div key={i} className="rounded-2xl bg-cream/70 px-3 py-2"><div className="text-[12px] font-bold">{c.byName} <span className="font-normal text-ink/50">{new Date(c.at).toLocaleString("id-ID")}</span></div><div className="text-[14px]">{c.text}</div></div>
            ))}
            {!p.comments.length && <div className="text-[13px] text-ink/55">Belum ada komentar.</div>}
          </div>
          <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); try { setP(await api(`/promos/${id}/comments`, { method: "POST", body: { text: comment } })); setComment(""); } catch (er) { toast(er.message, "bad"); } }}>
            <input className="field" placeholder="Tulis komentar" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Komentar" />
            <button className="btn-primary" aria-label="Kirim komentar"><Send size={16} /></button>
          </form>
        </section>
      </div>

      <Sheet open={!!dlg} onClose={() => setDlg(null)} title={dlg === "review" ? "Review margin (Finance)" : "Keputusan Marketing Manager"}>
        <textarea className="field min-h-[100px]" placeholder="Catatan (wajib bila dikembalikan/ditolak)" value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="flex flex-wrap gap-2 mt-3">
          {dlg === "review" ? (<>
            <button className="btn-primary" onClick={() => call("review", { decision: "approve", note }, "Lolos review Finance")}><Check size={16} />Approve</button>
            <button className="btn-ghost" onClick={() => call("review", { decision: "return", note }, "Dikembalikan ke draft")}><Undo2 size={16} />Kembalikan</button>
          </>) : (<>
            <button className="btn-primary" onClick={() => call("approve", { decision: "approve", note }, "Promo disetujui", true)}><Check size={16} />Setujui</button>
            <button className="btn-ghost" onClick={() => call("approve", { decision: "reject", note }, "Promo ditolak")}><X size={16} />Tolak</button>
          </>)}
        </div>
      </Sheet>
    </div>
  );
}
