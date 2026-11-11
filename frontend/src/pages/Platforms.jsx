import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Pencil, ShieldCheck, Copy as Dup, Calculator, Plus, Trash2, AlertTriangle } from "lucide-react";
import { api, rp, pc, CH_LABEL } from "../lib";
import { Title, Sheet, useToast, Waterfall } from "../ui";
import { NumInput } from "./Calculator";

const TYPES = { percent: "% dari harga", percent_capped: "% dengan batas/order", fixed_per_order: "Rp per order", fixed_per_unit: "Rp per item" };
const BASES = { gross_list: "Harga normal", net_after_merchant_discount: "Setelah diskon kita", net_after_all_discount: "Setelah semua diskon" };
const WHEN = { always: "Selalu", promo_only: "Hanya saat promo", program_opt_in: "Bila ikut program" };

function example(c) {
  const base = 20000;
  if (c.type === "percent" || c.type === "percent_capped") { const v = (c.rate / 100) * base; return c.cap ? Math.min(v, c.cap) : v; }
  return c.amount || 0;
}

export default function Platforms({ st, reload }) {
  const toast = useToast();
  const [edit, setEdit] = useState(null);
  const [sim, setSim] = useState(null);
  const u = st.user;
  const canEdit = (p) => u.isAdmin || ["finance", "head"].includes(u.perm) || (u.perm === "channel_pic" && (u.platforms || []).includes(p.id));

  const save = async () => {
    try { const { id, ...body } = edit; await api(`/platform-profiles/${id}`, { method: "PUT", body }); toast("Profil tersimpan — perlu divalidasi ulang"); setEdit(null); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const verify = async (p) => {
    const note = prompt("Sumber validasi (mis. Merchant Center 12 Nov 2026, settlement Oktober):", p.sourceNote || "");
    if (note === null) return;
    try { await api(`/platform-profiles/${p.id}/verify`, { method: "POST", body: { sourceNote: note } }); toast(`${p.label} sudah divalidasi`); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const dup = async (p) => { try { await api(`/platform-profiles/${p.id}/duplicate`, { method: "POST" }); toast("Profil diduplikat"); reload(); } catch (e) { toast(e.message, "bad"); } };

  return (
    <div>
      <Title a="Platform" b="& biaya" sub="Komisi, biaya per order, program, packaging, ads — semua bisa diubah di sini" />
      {["online_food", "marketplace", "event", "offline"].map((g) => (
        <section key={g} className="mb-6">
          <h3 className="font-extrabold text-[17px] mb-2">{CH_LABEL[g]}</h3>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {st.profiles.filter((p) => p.channelType === g).map((p, i) => {
              const fees = (p.feeComponents || []).filter((c) => c.active !== false);
              return (
                <motion.div key={p.id} className="card p-4" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-extrabold text-[16px]">{p.label}</div>
                      <div className={`text-[12px] font-bold flex items-center gap-1 ${p.verified ? "text-ok" : "text-warn"}`}>
                        {p.verified ? <ShieldCheck size={14} /> : <AlertTriangle size={14} />}{p.verified ? "Sudah divalidasi" : "Belum divalidasi"} · v{p.version || 1}
                      </div>
                    </div>
                    {canEdit(p) && <button aria-label={`Edit ${p.label}`} onClick={() => setEdit(JSON.parse(JSON.stringify(p)))} className="w-9 h-9 rounded-full hover:bg-blush flex items-center justify-center"><Pencil size={15} /></button>}
                  </div>
                  <div className="text-[12px] text-ink/55 mt-0.5">{p.sourceNote}</div>
                  <ul className="mt-3 space-y-1 text-[13px]">
                    {fees.length ? fees.map((c) => (
                      <li key={c.key} className="flex justify-between gap-2">
                        <span className="text-ink/75">{c.label}{c.appliesWhen === "program_opt_in" && <span className="text-ink/45"> (program)</span>}</span>
                        <span className="font-bold num whitespace-nowrap">{c.type.startsWith("percent") ? `${(c.rate || 0).toLocaleString("id-ID")}%` : rp(c.amount)}</span>
                      </li>
                    )) : <li className="text-ink/55">Tanpa potongan platform</li>}
                    {!!p.ppnPct && <li className="flex justify-between"><span className="text-ink/75">PPN atas biaya</span><b>{p.ppnPct}%</b></li>}
                    {!!p.costs?.extraPackagingPerOrder && <li className="flex justify-between"><span className="text-ink/75">Packaging/order</span><b className="num">{rp(p.costs.extraPackagingPerOrder)}</b></li>}
                    {p.ads?.model === "roas" && <li className="flex justify-between"><span className="text-ink/75">Ads ROAS target</span><b>{p.ads.roas}</b></li>}
                    {!!p.pricing?.markupPct && <li className="flex justify-between"><span className="text-ink/75">{g === "event" ? "Harga event" : "Markup harga app"}</span><b>+{p.pricing.markupPct}%</b></li>}
                    {!!p.costs?.paymentFeePct && <li className="flex justify-between"><span className="text-ink/75">Biaya pembayaran / cashless</span><b>{String(p.costs.paymentFeePct).replace(".", ",")}%</b></li>}
                    {g === "event" && <li className="flex justify-between"><span className="text-ink/75">Template biaya tetap</span><b className="num">{rp((p.eventFixedTemplate || []).reduce((a, x) => a + (x.amount || 0), 0))}</b></li>}
                    {g === "event" && p.eventDefaults && <li className="text-ink/55 text-[12px]">{p.eventDefaults.days} hari · {Number(p.eventDefaults.footfallPerDay).toLocaleString("id-ID")} pengunjung/hari · capture {p.eventDefaults.capturePct}% · beli {p.eventDefaults.conversionPct}%</li>}
                  </ul>
                  <div className="flex flex-wrap gap-2 mt-3">
                    {(g === "online_food" || g === "marketplace") && <button className="btn-soft !min-h-[38px] !text-[13px]" onClick={() => setSim({ profileId: p.id, items: [{ productId: st.products.find((x) => (x.channels || []).includes(p.productChannel))?.id, qty: 1 }], discountPct: 0, merchantPct: 100, area: "jakarta", res: null })}><Calculator size={15} />Simulasi 1 order</button>}
                    {canEdit(p) && !p.verified && <button className="btn-ghost !min-h-[38px] !text-[13px]" onClick={() => verify(p)}><ShieldCheck size={15} />Tandai divalidasi</button>}
                    {(u.isAdmin || ["finance", "head"].includes(u.perm)) && <button className="btn-soft !min-h-[38px] !text-[13px]" onClick={() => dup(p)}><Dup size={15} />Duplikat</button>}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </section>
      ))}

      <Sheet open={!!edit} onClose={() => setEdit(null)} title={`Edit ${edit?.label || ""}`} wide>
        {edit && <ProfileForm p={edit} set={setEdit} onSave={save} />}
      </Sheet>
      <Sheet open={!!sim} onClose={() => setSim(null)} title="Simulasi 1 order" wide>
        {sim && <SimOrder st={st} sim={sim} setSim={setSim} />}
      </Sheet>
    </div>
  );
}

function ProfileForm({ p, set, onSave }) {
  const upC = (i, patch) => { const x = [...p.feeComponents]; x[i] = { ...x[i], ...patch }; set({ ...p, feeComponents: x }); };
  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-2 gap-3">
        <div><label className="lbl">Nama profil</label><input className="field" value={p.label} onChange={(e) => set({ ...p, label: e.target.value })} /></div>
        <div><label className="lbl">Sumber angka</label><input className="field" value={p.sourceNote || ""} onChange={(e) => set({ ...p, sourceNote: e.target.value })} /></div>
      </div>
      <div>
        <div className="font-extrabold mb-2">Komponen potongan</div>
        <div className="space-y-2">
          {p.feeComponents.map((c, i) => (
            <div key={i} className="rounded-2xl bg-cream/70 p-3 grid grid-cols-2 md:grid-cols-6 gap-2 items-end">
              <div className="col-span-2"><label className="lbl">Nama</label><input className="field" value={c.label} onChange={(e) => upC(i, { label: e.target.value })} /></div>
              <div><label className="lbl">Tipe</label><select className="field" value={c.type} onChange={(e) => upC(i, { type: e.target.value })}>{Object.entries(TYPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
              {c.type.startsWith("percent")
                ? <div><label className="lbl">Tarif</label><NumInput suffix="%" value={c.rate} onChange={(v) => upC(i, { rate: v || 0 })} /></div>
                : <div><label className="lbl">Nominal</label><NumInput prefix="Rp" value={c.amount} onChange={(v) => upC(i, { amount: v || 0 })} /></div>}
              {c.type === "percent_capped" && <div><label className="lbl">Batas/order</label><NumInput prefix="Rp" value={c.cap} onChange={(v) => upC(i, { cap: v || 0 })} /></div>}
              {c.type.startsWith("percent") && <div><label className="lbl">Dihitung dari</label><select className="field" value={c.base} onChange={(e) => upC(i, { base: e.target.value })}>{Object.entries(BASES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>}
              <div><label className="lbl">Berlaku</label><select className="field" value={c.appliesWhen} onChange={(e) => upC(i, { appliesWhen: e.target.value })}>{Object.entries(WHEN).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
              {c.appliesWhen === "program_opt_in" && <div><label className="lbl">Program</label><select className="field" value={c.programKey || ""} onChange={(e) => upC(i, { programKey: e.target.value })}>{(p.programs || []).map((g) => <option key={g.programKey} value={g.programKey}>{g.label}</option>)}</select></div>}
              <div className="col-span-2 md:col-span-6 flex flex-wrap items-center gap-4 text-[13px] font-semibold">
                <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-bata w-4 h-4" checked={!!c.taxable} onChange={(e) => upC(i, { taxable: e.target.checked })} />Kena PPN</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-bata w-4 h-4" checked={c.payer === "customer"} onChange={(e) => upC(i, { payer: e.target.checked ? "customer" : "merchant" })} />Dibayar customer</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-bata w-4 h-4" checked={c.active !== false} onChange={(e) => upC(i, { active: e.target.checked })} />Aktif</label>
                <span className="text-ink/55">Contoh item Rp20.000: <b className="num">{rp(example(c))}</b></span>
                <button type="button" className="ml-auto text-bata flex items-center gap-1" onClick={() => set({ ...p, feeComponents: p.feeComponents.filter((_, j) => j !== i) })}><Trash2 size={14} />Hapus</button>
              </div>
            </div>
          ))}
        </div>
        <button className="btn-soft mt-2" onClick={() => set({ ...p, feeComponents: [...p.feeComponents, { key: `c${Date.now()}`, label: "Biaya baru", type: "percent", rate: 0, amount: 0, base: "net_after_all_discount", appliesWhen: "always", payer: "merchant", active: true }] })}><Plus size={16} />Tambah komponen</button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><label className="lbl">PPN atas biaya</label><NumInput suffix="%" value={p.ppnPct} onChange={(v) => set({ ...p, ppnPct: v || 0 })} /></div>
        <div><label className="lbl">Diskon biaya admin</label><NumInput suffix="%" value={p.adminFeeDiscountPct} onChange={(v) => set({ ...p, adminFeeDiscountPct: v || 0 })} /></div>
        <div><label className="lbl">{p.channelType === "event" ? "Harga event (+%)" : "Markup harga app"}</label><NumInput suffix="%" value={p.pricing?.markupPct} onChange={(v) => set({ ...p, pricing: { ...p.pricing, markupPct: v || 0 } })} /></div>
        <div><label className="lbl">Biaya kemasan ke customer</label><NumInput prefix="Rp" value={p.pricing?.packagingFeeToCustomer} onChange={(v) => set({ ...p, pricing: { ...p.pricing, packagingFeeToCustomer: v || 0 } })} /></div>
        <div><label className="lbl">Porsi per order</label><NumInput value={p.avgUnitsPerOrder} onChange={(v) => set({ ...p, avgUnitsPerOrder: v || 1 })} /></div>
        <div><label className="lbl">Packaging per order</label><NumInput prefix="Rp" value={p.costs?.extraPackagingPerOrder} onChange={(v) => set({ ...p, costs: { ...p.costs, extraPackagingPerOrder: v || 0 } })} /></div>
        <div><label className="lbl">Cadangan retur</label><NumInput suffix="%" value={p.costs?.returnAllowancePct} onChange={(v) => set({ ...p, costs: { ...p.costs, returnAllowancePct: v || 0 } })} /></div>
        <div><label className="lbl">{p.channelType === "event" ? "Biaya cashless/QRIS" : "Biaya pembayaran"}</label><NumInput suffix="%" value={p.costs?.paymentFeePct} onChange={(v) => set({ ...p, costs: { ...p.costs, paymentFeePct: v || 0 } })} /></div>
        <div><label className="lbl">Model ads</label><select className="field" value={p.ads?.model || "none"} onChange={(e) => set({ ...p, ads: { ...p.ads, model: e.target.value } })}>
          <option value="none">Tanpa ads</option><option value="pct_of_sales">% dari penjualan</option><option value="roas">Target ROAS</option><option value="cpc">Biaya per klik</option></select></div>
        {p.ads?.model === "pct_of_sales" && <div><label className="lbl">Ads % penjualan</label><NumInput suffix="%" value={p.ads.pct} onChange={(v) => set({ ...p, ads: { ...p.ads, pct: v || 0 } })} /></div>}
        {p.ads?.model === "roas" && <div><label className="lbl">ROAS</label><NumInput value={p.ads.roas} onChange={(v) => set({ ...p, ads: { ...p.ads, roas: v || 0 } })} /></div>}
        {p.ads?.model === "cpc" && <><div><label className="lbl">CPC</label><NumInput prefix="Rp" value={p.ads.cpc} onChange={(v) => set({ ...p, ads: { ...p.ads, cpc: v || 0 } })} /></div>
          <div><label className="lbl">Konversi</label><NumInput suffix="%" value={p.ads.cvrPct} onChange={(v) => set({ ...p, ads: { ...p.ads, cvrPct: v || 0 } })} /></div></>}
      </div>
      {p.channelType === "event" && (
        <div>
          <div className="font-extrabold mb-2">Asumsi default event</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[["days", "Durasi (hari)"], ["hoursPerDay", "Jam/hari"], ["footfallPerDay", "Pengunjung/hari"], ["fnbTenants", "Tenant F&B"],
              ["capturePct", "Mampir %"], ["conversionPct", "Beli %"], ["boothCapacityPerHour", "Kapasitas porsi/jam"], ["aovEvent", "AOV non-promo"],
              ["unitsPerTrx", "Porsi/transaksi"], ["crmCapturePct", "Data CRM %"]].map(([k, l]) => (
              <div key={k}><label className="lbl">{l}</label><NumInput value={p.eventDefaults?.[k] ?? ""} onChange={(v) => set({ ...p, eventDefaults: { ...p.eventDefaults, [k]: v } })} /></div>
            ))}
          </div>
          <div className="font-extrabold mt-4 mb-2">Template biaya tetap</div>
          {(p.eventFixedTemplate || []).map((x, i) => (
            <div key={i} className="grid grid-cols-[1fr_150px_auto] gap-2 mb-2">
              <input className="field" value={x.label} onChange={(e) => { const t = [...p.eventFixedTemplate]; t[i] = { ...x, label: e.target.value }; set({ ...p, eventFixedTemplate: t }); }} />
              <NumInput prefix="Rp" value={x.amount} onChange={(v) => { const t = [...p.eventFixedTemplate]; t[i] = { ...x, amount: v || 0 }; set({ ...p, eventFixedTemplate: t }); }} />
              <button type="button" aria-label="Hapus biaya" className="h-11 w-11 rounded-xl border border-line flex items-center justify-center" onClick={() => set({ ...p, eventFixedTemplate: p.eventFixedTemplate.filter((_, j) => j !== i) })}><Trash2 size={16} /></button>
            </div>
          ))}
          <button className="btn-soft" onClick={() => set({ ...p, eventFixedTemplate: [...(p.eventFixedTemplate || []), { label: "", amount: 0 }] })}><Plus size={16} />Biaya</button>
        </div>
      )}
      {!!p.programs?.length && <div>
        <div className="font-extrabold mb-2">Program platform</div>
        {p.programs.map((g, i) => (
          <div key={g.programKey} className="grid grid-cols-[1fr_140px] gap-2 mb-2 items-end">
            <div><label className="lbl">Nama program</label><input className="field" value={g.label} onChange={(e) => { const x = [...p.programs]; x[i] = { ...g, label: e.target.value }; set({ ...p, programs: x }); }} /></div>
            <div><label className="lbl">Ditanggung platform</label><NumInput suffix="%" value={g.defaultPlatformFundingPct} onChange={(v) => { const x = [...p.programs]; x[i] = { ...g, defaultPlatformFundingPct: v || 0 }; set({ ...p, programs: x }); }} /></div>
          </div>
        ))}
      </div>}
      <button className="btn-primary w-full" onClick={onSave}>Simpan profil</button>
    </div>
  );
}

function SimOrder({ st, sim, setSim }) {
  const prof = st.profiles.find((p) => p.id === sim.profileId);
  const items = st.products.filter((p) => (p.channels || []).includes(prof.productChannel));
  const run = async (s) => {
    try { const r = await api("/calc/settlement", { method: "POST", body: s }); setSim({ ...s, res: r }); } catch (e) { setSim({ ...s, res: { error: e.message } }); }
  };
  const upd = (patch) => { const s = { ...sim, ...patch, res: sim.res }; setSim(s); run(s); };
  useEffect(() => { run(sim); }, []); // eslint-disable-line
  const r = sim.res;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="space-y-3">
        <div className="text-[13px] text-ink/60">Masukkan isi 1 order, lalu cocokkan hasilnya dengan laporan settlement {prof.label}.</div>
        {sim.items.map((it, i) => (
          <div key={i} className="grid grid-cols-[1fr_70px] gap-2">
            <select className="field" value={it.productId} onChange={(e) => { const x = [...sim.items]; x[i] = { ...it, productId: e.target.value }; upd({ items: x }); }}>{items.map((p) => <option key={p.id} value={p.id}>{p.nama}</option>)}</select>
            <NumInput value={it.qty} onChange={(v) => { const x = [...sim.items]; x[i] = { ...it, qty: v || 1 }; upd({ items: x }); }} />
          </div>
        ))}
        <button className="btn-soft" onClick={() => upd({ items: [...sim.items, { productId: items[0]?.id, qty: 1 }] })}><Plus size={16} />Item</button>
        <div className="grid grid-cols-2 gap-2">
          <div><label className="lbl">Diskon</label><NumInput suffix="%" value={sim.discountPct} onChange={(v) => upd({ discountPct: v || 0 })} /></div>
          <div><label className="lbl">Ditanggung kita</label><NumInput suffix="%" value={sim.merchantPct} onChange={(v) => upd({ merchantPct: v === "" ? 100 : v })} /></div>
        </div>
        <div className="flex gap-2">{["bandung", "jakarta"].map((a) => <button key={a} onClick={() => upd({ area: a })} className={`flex-1 h-10 rounded-xl border font-semibold ${sim.area === a ? "bg-bata text-cream border-bata" : "border-line"}`}>{a === "bandung" ? "Bandung" : "Jakarta"}</button>)}</div>
      </div>
      <div>
        {r?.error && <div className="text-bata font-semibold">{r.error}</div>}
        {r && !r.error && (<>
          <Waterfall unit={{ ...r, customerPays: r.listPrice - r.discount, cm: r.cm }} />
          <div className="mt-3 text-[14px]">Diterima dari platform: <b className="num">{rp(r.merchantGross - r.platformFees)}</b> · potongan efektif <b>{pc(r.effectiveTakeRate)}</b></div>
        </>)}
      </div>
    </div>
  );
}
