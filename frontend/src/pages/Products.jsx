import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Pencil, Upload, Download, History, Plus } from "lucide-react";
import { api, rp, getToken, fmtDate } from "../lib";
import { Title, Sheet, useToast } from "../ui";
import { NumInput } from "./Calculator";

const KAT = { reguler: "Cimol Reguler", mix: "Cimol Mix", kuah_keju: "Kuah Keju", new_series: "New Series", frozen: "Frozen", minuman: "Minuman", addon: "Add-on" };
const CHANNELS = [["kios", "Kios"], ["gerobak", "Gerobak"], ["online_food", "Online Food"], ["marketplace", "Marketplace"], ["event", "Event"]];

export default function Products({ st, reload }) {
  const toast = useToast();
  const [edit, setEdit] = useState(null);
  const [hist, setHist] = useState(null);
  const [q, setQ] = useState("");
  const canEdit = st.user.isAdmin || ["finance", "head"].includes(st.user.perm);
  const groups = useMemo(() => {
    const g = {};
    st.products.filter((p) => !q || p.nama.toLowerCase().includes(q.toLowerCase())).forEach((p) => { (g[p.kategori] = g[p.kategori] || []).push(p); });
    return g;
  }, [st.products, q]);

  const save = async () => {
    try {
      const body = { ...edit };
      if (edit.isNew) await api("/products", { method: "POST", body });
      else await api(`/products/${edit.id}`, { method: "PUT", body: { nama: body.nama, hpp: body.hpp, prices: body.prices, channels: body.channels, active: body.active, kategori: body.kategori } });
      toast("Produk tersimpan — versi harga baru dibuat"); setEdit(null); reload();
    } catch (e) { toast(e.message, "bad"); }
  };
  const importCsv = async (file) => {
    try { const r = await api("/products/import", { method: "POST", body: await file.text(), raw: true }); toast(`${r.imported} produk diimport`); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };
  useEffect(() => { if (hist === "load") api("/price-versions").then(setHist).catch(() => setHist([])); }, [hist]);

  return (
    <div>
      <Title a="Produk" b={canEdit || st.products[0]?.hpp != null ? "& HPP" : "& harga"} sub={`Acuan Price Structure · versi ${st.settings.priceVersion || 1}`}
        right={<div className="flex flex-wrap gap-2">
          {st.products[0]?.hpp != null && <button className="btn-soft" onClick={() => setHist("load")}><History size={16} /><span className="hidden sm:inline">Riwayat</span></button>}
          {canEdit && <a className="btn-soft" href={`/api/export/products.csv?token=${getToken()}`}><Download size={16} /><span className="hidden sm:inline">Export</span></a>}
          {canEdit && <label className="btn-soft cursor-pointer"><Upload size={16} /><span className="hidden sm:inline">Import CSV</span><input type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files[0] && importCsv(e.target.files[0])} /></label>}
          {canEdit && <button className="btn-primary" onClick={() => setEdit({ isNew: true, nama: "", kategori: "reguler", hpp: "", prices: {}, channels: ["kios"] })}><Plus size={16} />Produk</button>}
        </div>} />
      <input className="field mb-4 max-w-sm" placeholder="Cari produk" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari produk" />
      <div className="space-y-5">
        {Object.entries(groups).map(([k, items]) => (
          <section key={k}>
            <h3 className="font-extrabold text-[17px] mb-2">{KAT[k] || k}</h3>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {items.map((p, i) => (
                <motion.div key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }} className="card p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-bold leading-snug">{p.nama}</div>
                    {canEdit && <button aria-label={`Edit ${p.nama}`} className="w-9 h-9 rounded-full hover:bg-blush flex items-center justify-center shrink-0" onClick={() => setEdit(JSON.parse(JSON.stringify(p)))}><Pencil size={15} /></button>}
                  </div>
                  <div className="text-[13px] text-ink/65 num">{p.hpp != null ? `HPP ${rp(p.hpp)} · ` : ""}Bdg {rp(p.prices?.bandung)} · Jkt {rp(p.prices?.jakarta)}</div>
                  {p.gmPct != null && <div className="flex items-center gap-2 mt-2">
                    <div className="flex-1 h-2.5 rounded-full bg-cream overflow-hidden">
                      <motion.div className="h-full rounded-full" style={{ background: p.amanDiskon ? "#2F6B4A" : p.hindariGratis ? "#B42F27" : "#B8741A" }}
                        initial={{ width: 0 }} animate={{ width: `${p.gmPct}%` }} transition={{ delay: 0.1 + i * 0.02, type: "spring", stiffness: 80 }} />
                    </div>
                    <span className="text-[13px] font-extrabold num w-12 text-right">{p.gmPct.toLocaleString("id-ID")}%</span>
                  </div>}
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {p.amanDiskon && <span className="pill border-ok text-ok">Aman diskon</span>}
                    {p.hindariGratis && <span className="pill">Hindari gratis</span>}
                    {p.active === false && <span className="pill border-ink/40 text-ink/50">Nonaktif</span>}
                  </div>
                </motion.div>
              ))}
            </div>
          </section>
        ))}
      </div>

      <Sheet open={!!edit} onClose={() => setEdit(null)} title={edit?.isNew ? "Produk baru" : `Edit ${edit?.nama}`}>
        {edit && (
          <div className="space-y-3">
            <div><label className="lbl">Nama</label><input className="field" value={edit.nama} onChange={(e) => setEdit({ ...edit, nama: e.target.value })} /></div>
            <div><label className="lbl">Kategori</label><select className="field" value={edit.kategori} onChange={(e) => setEdit({ ...edit, kategori: e.target.value })}>{Object.entries(KAT).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
            <div className="grid grid-cols-3 gap-2">
              <div><label className="lbl">HPP</label><NumInput prefix="Rp" value={edit.hpp} onChange={(v) => setEdit({ ...edit, hpp: v })} /></div>
              <div><label className="lbl">Harga Bdg</label><NumInput prefix="Rp" value={edit.prices?.bandung ?? ""} onChange={(v) => setEdit({ ...edit, prices: { ...edit.prices, bandung: v === "" ? null : v } })} /></div>
              <div><label className="lbl">Harga Jkt</label><NumInput prefix="Rp" value={edit.prices?.jakarta ?? ""} onChange={(v) => setEdit({ ...edit, prices: { ...edit.prices, jakarta: v === "" ? null : v } })} /></div>
            </div>
            <div><span className="lbl">Dijual di</span><div className="flex flex-wrap gap-2">{CHANNELS.map(([k, l]) => {
              const on = (edit.channels || []).includes(k);
              return <button key={k} type="button" onClick={() => setEdit({ ...edit, channels: on ? edit.channels.filter((x) => x !== k) : [...(edit.channels || []), k] })}
                className={`px-3 min-h-[38px] rounded-full text-[13px] font-semibold border ${on ? "bg-bata text-cream border-bata" : "border-line"}`}>{l}</button>;
            })}</div></div>
            {!edit.isNew && <label className="flex items-center gap-2 font-semibold text-[14px]"><input type="checkbox" className="w-5 h-5 accent-bata" checked={edit.active !== false} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} />Aktif</label>}
            <button className="btn-primary w-full" onClick={save}>Simpan</button>
            <p className="text-[12px] text-ink/55">Setiap perubahan membuat versi harga baru. Promo lama tetap memakai angka lama sampai dihitung ulang.</p>
          </div>
        )}
      </Sheet>
      <Sheet open={!!hist} onClose={() => setHist(null)} title="Riwayat versi harga">
        {Array.isArray(hist) ? <ol className="space-y-2">{hist.map((h) => <li key={h.version} className="card px-3 py-2"><b>v{h.version}</b> · {fmtDate(h.at)} · {h.by}<div className="text-[13px] text-ink/65">{h.note}</div></li>)}</ol> : null}
      </Sheet>
    </div>
  );
}
