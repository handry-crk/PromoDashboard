import { useState } from "react";
import { motion } from "framer-motion";
import { Copy, RefreshCw, KeyRound } from "lucide-react";
import { api, CH_LABEL } from "../lib";
import { Title, useToast, Sheet } from "../ui";
import { NumInput } from "./Calculator";

export default function Settings({ st, reload }) {
  const toast = useToast();
  const s = st.settings;
  const [f, setF] = useState({
    safeDiscountGm: s.safeDiscountGm, lowMarginGm: s.lowMarginGm, offlineMarginFloorPct: s.offlineMarginFloorPct,
    onlineMarginFloorPct: s.onlineMarginFloorPct, marketplaceMarginFloorPct: s.marketplaceMarginFloorPct, roundingStep: s.roundingStep,
    weights: { ...s.weights }, adminEmail: s.adminEmail || "",
  });
  const [bl, setBl] = useState({ platformId: "offline_kios", area: "bandung" });
  const [pin, setPin] = useState(null);
  const isAdmin = st.user.isAdmin || st.user.perm === "head";
  const link = `${window.location.origin}/laporan?t=${s.shareToken}`;
  const baseline = ((s.baselines || {})[bl.platformId] || {})[bl.area] || {};
  const [b, setB] = useState(null);
  const cur = b || baseline;

  const save = async (extra = {}) => {
    try { await api("/settings", { method: "PUT", body: { ...f, ...extra } }); toast("Settings tersimpan"); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const saveBaseline = async () => {
    try { await api("/baselines", { method: "PUT", body: { ...bl, baseline: cur } }); toast("Baseline tersimpan"); setB(null); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const member = async (m, patch) => { try { await api(`/members/${m.id}`, { method: "PUT", body: patch }); reload(); } catch (e) { toast(e.message, "bad"); } };
  const decide = async (m, decision) => {
    try { await api(`/members/${m.id}/approve`, { method: "POST", body: { decision } }); toast(decision === "approve" ? `${m.name} disetujui` : `Pendaftaran ${m.name} ditolak`); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };
  const pending = st.members.filter((m) => m.status === "pending");
  const resetPin = async () => {
    try { await api(`/members/${pin.id}/reset-pin`, { method: "POST", body: { pin: pin.pin } }); toast(`PIN ${pin.name} direset`); setPin(null); }
    catch (e) { toast(e.message, "bad"); }
  };

  if (!isAdmin) return <div className="card p-6">Settings hanya untuk Marketing Manager / Admin.</div>;
  const n = (k, label, props) => <div><label className="lbl">{label}</label><NumInput value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} {...props} /></div>;

  return (
    <div className="space-y-5">
      <Title a="Settings" b="dashboard" />
      <section className="card p-4">
        <div className="font-extrabold mb-1">Approval anggota baru</div>
        <p className="text-[13px] text-ink/60 mb-3">Slot pendaftaran: {(st.slots || []).map((s) => `${s.label} ${s.used}/${s.quota}`).join(" · ")}. Wajib email @{st.emailDomain}.</p>
        {pending.length ? pending.map((m) => (
          <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-blush px-3 py-2.5 mb-2">
            <div><div className="font-bold">{m.name} <span className="pill ml-1">{st.roles[m.role]}</span></div><div className="text-[12px] text-ink/60">{m.email} {m.phone}</div></div>
            <div className="flex gap-2">
              <button className="btn-primary !min-h-[38px]" onClick={() => decide(m, "approve")}>Setujui</button>
              <button className="btn-ghost !min-h-[38px]" onClick={() => decide(m, "reject")}>Tolak</button>
            </div>
          </motion.div>
        )) : <div className="text-[14px] text-ink/55">Tidak ada pendaftaran yang menunggu.</div>}
      </section>
      <section className="card p-4">
        <div className="font-extrabold mb-2">Link Reporting (tanpa login)</div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input className="field text-[13px]" readOnly value={link} aria-label="Link reporting" />
          <button className="btn-soft" onClick={() => navigator.clipboard?.writeText(link).then(() => toast("Link tersalin"))}><Copy size={16} />Copy link</button>
          <button className="btn-ghost" onClick={() => save({ regenerateShareToken: true })}><RefreshCw size={16} />Buat ulang</button>
        </div>
        <p className="text-[12px] text-ink/55 mt-1">Halaman ini tidak menampilkan HPP, potongan platform, atau CM dalam rupiah.</p>
      </section>

      <section className="card p-4">
        <div className="font-extrabold mb-3">Ambang skor</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {n("safeDiscountGm", "GM aman diskon ≥", { suffix: "%" })}
          {n("lowMarginGm", "GM hindari gratis <", { suffix: "%" })}
          {n("offlineMarginFloorPct", "Batas CM offline", { suffix: "%" })}
          {n("onlineMarginFloorPct", "Batas CM online food", { suffix: "%" })}
          {n("marketplaceMarginFloorPct", "Batas CM marketplace", { suffix: "%" })}
          {n("roundingStep", "Pembulatan harga", { prefix: "Rp" })}
        </div>
        <div className="font-extrabold mt-4 mb-2">Bobot rekomendasi</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[["sehat", "Sehat"], ["margin", "Margin"], ["menarik", "Menarik"], ["fit", "Fit objective"]].map(([k, l]) => (
            <div key={k}><label className="lbl">{l}</label><NumInput suffix="%" value={Math.round((f.weights[k] || 0) * 100)} onChange={(v) => setF({ ...f, weights: { ...f.weights, [k]: (v || 0) / 100 } })} /></div>
          ))}
        </div>
        <div className="mt-3 max-w-sm"><label className="lbl">Email admin (CC)</label><input className="field" value={f.adminEmail} onChange={(e) => setF({ ...f, adminEmail: e.target.value })} /></div>
        <button className="btn-primary mt-4" onClick={() => save()}>Simpan settings</button>
      </section>

      <section className="card p-4">
        <div className="font-extrabold mb-1">Baseline per channel</div>
        <p className="text-[13px] text-ink/60 mb-3">Dipakai untuk skenario dan "CM vs transaksi rata-rata". Isi dari data POS.</p>
        <div className="grid grid-cols-2 gap-2 mb-3 max-w-md">
          <select className="field" value={bl.platformId} onChange={(e) => { setBl({ ...bl, platformId: e.target.value }); setB(null); }}>
            {st.profiles.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          <select className="field" value={bl.area} onChange={(e) => { setBl({ ...bl, area: e.target.value }); setB(null); }}>
            <option value="bandung">Bandung Raya</option><option value="jakarta">Jabodetabek</option>
          </select>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[["gpPerTrx", "CM per transaksi", "Rp"], ["aovNormal", "AOV normal", "Rp"], ["trxPerOutletDay", "Trx/outlet/hari"], ["outlets", "Jumlah outlet"], ["openRate", "Open rate", null, "%"]].map(([k, l, pre, suf]) => (
            <div key={k}><label className="lbl">{l}</label><NumInput prefix={pre || undefined} suffix={suf || undefined} value={cur[k] ?? ""} onChange={(v) => setB({ ...cur, [k]: v === "" ? undefined : v })} /></div>
          ))}
        </div>
        <button className="btn-primary mt-3" onClick={saveBaseline}>Simpan baseline</button>
      </section>

      <section className="card p-4">
        <div className="font-extrabold mb-3">Anggota</div>
        <div className="space-y-2">
          {st.members.filter((m) => m.status !== "pending").map((m) => (
            <div key={m.id} className="grid grid-cols-[1fr_auto] md:grid-cols-[1fr_220px_200px_auto] gap-2 items-center rounded-2xl bg-cream/60 px-3 py-2">
              <div><div className="font-bold">{m.name}{m.isAdmin && <span className="pill ml-2">Admin</span>}</div><div className="text-[12px] text-ink/55">{m.email} {m.phone}</div></div>
              <select className="field !py-1.5" value={m.role} onChange={(e) => member(m, { role: e.target.value })} aria-label={`Role ${m.name}`}>
                {Object.entries(st.roles).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              {m.role === "channel_pic" ? (
                <select multiple className="field !py-1 text-[13px] h-20" value={m.platforms || []} aria-label={`Platform ${m.name}`}
                  onChange={(e) => member(m, { platforms: [...e.target.selectedOptions].map((o) => o.value) })}>
                  {st.profiles.filter((p) => p.channelType !== "offline").map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              ) : <div className="hidden md:block text-[12px] text-ink/45">—</div>}
              <div className="flex gap-1">
                <button className="btn-soft !min-h-[38px] !px-3" onClick={() => setPin({ ...m, pin: "" })} aria-label={`Reset PIN ${m.name}`}><KeyRound size={15} /></button>
                <button className="btn-soft !min-h-[38px] !px-3 !text-[12px]" onClick={() => member(m, { active: !m.active })}>{m.active ? "Nonaktifkan" : "Aktifkan"}</button>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 max-w-xs"><label className="lbl">Ganti PIN Admin cadangan</label>
          <div className="flex gap-2"><input className="field" type="password" inputMode="numeric" maxLength={6} id="adminpin" />
            <button className="btn-ghost" onClick={() => { const v = document.getElementById("adminpin").value; if (v.length >= 4) save({ adminPin: v }); }}>Simpan</button></div></div>
      </section>

      <Sheet open={!!pin} onClose={() => setPin(null)} title={`Reset PIN ${pin?.name || ""}`}>
        <input className="field tracking-[.4em] text-center text-[20px]" inputMode="numeric" maxLength={6} value={pin?.pin || ""} onChange={(e) => setPin({ ...pin, pin: e.target.value.replace(/\D/g, "") })} aria-label="PIN baru" />
        <button className="btn-primary w-full mt-3" onClick={resetPin}>Reset PIN</button>
      </Sheet>
    </div>
  );
}
