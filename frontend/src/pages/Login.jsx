import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api, setToken } from "../lib";
import { useToast } from "../ui";

const BALLS = [
  { c: "#2F6B4A", t: "Sehat?", mouth: "M34 60 Q50 74 66 60" },
  { c: "#B8741A", t: "Margin?", mouth: "M36 63 Q50 64 64 63" },
  { c: "#B42F27", t: "Menarik?", mouth: "M34 60 Q50 74 66 60" },
];

export default function Login({ onIn }) {
  const [mode, setMode] = useState("login");
  const [info, setInfo] = useState({ members: [], roles: {}, hasAny: true });
  const inviteToken = new URLSearchParams(window.location.search).get("undangan") || "";
  const [invite, setInvite] = useState(null);
  const [f, setF] = useState({ identifier: "", pin: "", name: "", role: "", email: "", phone: "" });
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);
  const canRegister = !info.hasAny || (invite && !invite.error);
  const toast = useToast();

  useEffect(() => {
    api("/public/members").then((d) => { setInfo(d); if (!d.hasAny) setMode("register"); }).catch(() => {});
    if (inviteToken) {
      api(`/public/invite/${encodeURIComponent(inviteToken)}`)
        .then((d) => { setInvite(d); setMode("register"); })
        .catch((e) => setInvite({ error: e.message }));
    }
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      let r;
      if (mode === "login") r = await api("/auth/login", { method: "POST", body: { identifier: f.identifier, pin: f.pin } });
      else if (mode === "admin") r = await api("/auth/admin-login", { method: "POST", body: { pin: f.pin } });
      else r = await api("/auth/register", { method: "POST", body: { name: f.name, email: f.email, phone: f.phone, pin: f.pin, invite: inviteToken } });
      if (r.pending) { setSent(r.message); return; }
      setToken(r.token);
      onIn();
    } catch (err) { toast(err.message, "bad"); }
    finally { setBusy(false); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  return (
    <div className="min-h-screen grid md:grid-cols-[1.1fr_1fr]">
      <section className="bg-bata text-cream px-6 pt-10 pb-12 md:p-14 flex flex-col justify-between relative overflow-hidden">
        <div className="grain absolute inset-0 opacity-30" />
        <div className="relative">
          <div className="text-[12px] font-bold opacity-80">CRK GROUP · Cimol Bojot AA</div>
          <h1 className="text-[40px] md:text-[56px] leading-[1.02] mt-3"><b className="font-extrabold">Promo</b> Calculator</h1>
          <p className="mt-4 text-[16px] md:text-[18px] max-w-md opacity-90">
            Cek dulu sebelum promo jalan: masih untung setelah HPP dan potongan GoFood, Shopee, dan lainnya, dan cukup bikin customer mampir?
          </p>
        </div>
        <div className="relative flex gap-4 md:gap-6 mt-10 items-end" aria-hidden>
          {BALLS.map((b, i) => (
            <motion.div key={i} className="flex flex-col items-center" initial={{ y: -120, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.15 + i * 0.15, type: "spring", stiffness: 180, damping: 9 }}>
              <motion.svg width="84" height="84" viewBox="0 0 100 100" animate={{ y: [0, -14, 0], scaleY: [1, 1.04, 0.94, 1] }}
                transition={{ duration: 1.3, repeat: Infinity, delay: 1 + i * 0.22, ease: "easeInOut" }}>
                <circle cx="50" cy="50" r="44" fill="#ECE4D4" />
                <path d="M7.15 60 A44 44 0 0 0 92.85 60 Z" fill={b.c} fillOpacity=".9" />
                <ellipse cx="38" cy="42" rx="4" ry="5" fill="#212121" /><ellipse cx="62" cy="42" rx="4" ry="5" fill="#212121" />
                <path d={b.mouth} stroke="#212121" strokeWidth="3.4" fill="none" strokeLinecap="round" />
              </motion.svg>
              <div className="mt-2 text-[14px] font-bold">{b.t}</div>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="px-6 py-10 md:p-14 flex items-center">
        {sent ? (
          <motion.div className="w-full max-w-sm mx-auto text-center" initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
            <motion.svg width="96" height="96" viewBox="0 0 100 100" className="mx-auto" animate={{ rotate: [0, -6, 6, 0] }} transition={{ duration: 2, repeat: Infinity }}>
              <circle cx="50" cy="50" r="44" fill="#B8741A" /><circle cx="38" cy="42" r="5" fill="#212121" /><circle cx="62" cy="42" r="5" fill="#212121" />
              <path d="M36 63 Q50 64 64 63" stroke="#212121" strokeWidth="3.4" fill="none" strokeLinecap="round" />
            </motion.svg>
            <div className="text-[20px] font-extrabold mt-3">Menunggu approval</div>
            <p className="text-[15px] text-ink/70 mt-1">{sent}</p>
            <button className="btn-ghost mt-5" onClick={() => { setSent(null); setMode("login"); }}>Kembali ke login</button>
          </motion.div>
        ) : (
        <form onSubmit={submit} className="w-full max-w-sm mx-auto">
          <div className="flex gap-1 p-1 rounded-full bg-paper border border-line mb-6">
            {[["login", "Login"], ...(canRegister ? [["register", "Daftar"]] : []), ...(info.adminPin ? [["admin", "PIN Admin"]] : [])].map(([k, l]) => (
              <button type="button" key={k} onClick={() => setMode(k)}
                className={`relative flex-1 h-10 rounded-full text-[14px] font-semibold ${mode === k ? "text-cream" : "text-ink/70"}`}>
                {mode === k && <motion.span layoutId="authtab" className="absolute inset-0 rounded-full bg-bata" />}
                <span className="relative">{l}</span>
              </button>
            ))}
          </div>
          {!info.hasAny && mode === "register" && (
            <div className="card p-3 text-[13px] mb-4">Belum ada anggota. Orang pertama yang daftar otomatis menjadi <b>Admin (Marketing Manager)</b>.</div>
          )}
          <div className="space-y-4">
            {invite?.error && mode === "login" && <div className="card p-3 text-[13px] text-bata">{invite.error}</div>}
            {mode === "login" && (
              <div>
                <label className="lbl" htmlFor="m">Nama atau email kantor</label>
                <input id="m" className="field" autoComplete="username" value={f.identifier} onChange={set("identifier")} required />
              </div>
            )}
            {mode === "register" && (<>
              {invite && !invite.error && (
                <div className="card p-3 text-[14px]">Undangan sebagai <b>{invite.label}</b>. Berlaku sampai {new Date(invite.expiresAt).toLocaleDateString("id-ID", { day: "numeric", month: "long" })}.</div>
              )}
              <div><label className="lbl" htmlFor="n">Nama lengkap</label><input id="n" className="field" value={f.name} onChange={set("name")} required /></div>
              <div><label className="lbl" htmlFor="e">Email kantor</label>
                <input id="e" type="email" className="field" placeholder={`nama@${info.emailDomain || "citarasakuliner.com"}`} value={f.email} onChange={set("email")} required
                  pattern={`^[^@\\s]+@${(info.emailDomain || "citarasakuliner.com").replace(/\./g, "\\.")}$`} title={`Wajib email @${info.emailDomain || "citarasakuliner.com"}`} /></div>
              <div><label className="lbl" htmlFor="w">WhatsApp</label><input id="w" inputMode="tel" placeholder="08…" className="field" value={f.phone} onChange={set("phone")} /></div>
              {info.hasAny && <p className="text-[12px] text-ink/60">Akun aktif setelah disetujui Marketing Manager.</p>}
            </>)}
            {mode === "login" && <p className="text-[12px] text-ink/55">Belum punya akun? Minta link undangan ke Marketing Manager.</p>}
            <div>
              <label className="lbl" htmlFor="p">{mode === "admin" ? "PIN Admin" : "PIN (4–6 angka)"}</label>
              <input id="p" className="field tracking-[.4em] text-center text-[20px] font-bold" type="password" inputMode="numeric" maxLength={6}
                value={f.pin} onChange={(e) => setF({ ...f, pin: e.target.value.replace(/\D/g, "") })} required />
            </div>
            <button className="btn-primary w-full" disabled={busy}>
              {busy ? "Memeriksa…" : mode === "register" ? (info.hasAny ? "Kirim pendaftaran" : "Daftar & masuk") : "Masuk"}</button>
          </div>
        </form>
        )}
      </section>
    </div>
  );
}
