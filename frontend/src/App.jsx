import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Home as HomeI, Calculator as CalcI, Sparkles, Library as LibI, MoreHorizontal, Package, Store, Settings as SetI, LogOut, CalendarDays, Bot, GraduationCap, History as HistI } from "lucide-react";
import { api, setToken, getToken } from "./lib";
import { Loader, useToast, Sheet } from "./ui";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Calculator from "./pages/Calculator";
import Recommend from "./pages/Recommend";
import Library from "./pages/Library";
import PromoDetail from "./pages/PromoDetail";
import Products from "./pages/Products";
import Platforms from "./pages/Platforms";
import Settings from "./pages/Settings";
import Report from "./pages/Report";
import CalendarPage from "./pages/Calendar";
import Assistant, { BotFace } from "./pages/Assistant";
import Learning from "./pages/Learning";
import HistoryPage from "./pages/History";

function useHash() {
  const [h, setH] = useState(window.location.hash.slice(1) || "/");
  useEffect(() => {
    const f = () => { setH(window.location.hash.slice(1) || "/"); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return h;
}
export const go = (p) => { window.location.hash = p; };

const NAV = [
  { to: "/", label: "Beranda", icon: HomeI },
  { to: "/hitung", label: "Kalkulator", icon: CalcI },
  { to: "/kalender", label: "Kalender", icon: CalendarDays },
  { to: "/rekomendasi", label: "Rekomendasi", icon: Sparkles },
  { to: "/library", label: "Library", icon: LibI },
];
const MORE = [
  { to: "/asisten", label: "Asisten promo", short: "Asisten", icon: Bot },
  { to: "/belajar", label: "Data belajar", short: "Belajar", icon: GraduationCap },
  { to: "/produk", label: "Produk & HPP", short: "Produk", icon: Package },
  { to: "/platform", label: "Platform & Biaya", short: "Biaya", icon: Store },
  { to: "/riwayat", label: "Riwayat perubahan", short: "Riwayat", icon: HistI },
  { to: "/settings", label: "Settings", icon: SetI },
];

export default function App() {
  if (window.location.pathname.startsWith("/laporan")) return <Report />;
  return <Main />;
}

function Main() {
  const [st, setSt] = useState(null);
  const [loading, setLoading] = useState(!!getToken());
  const [more, setMore] = useState(false);
  const hash = useHash();
  const toast = useToast();

  const load = useCallback(async () => {
    try { setSt(await api("/state")); }
    catch (e) { if (e.status === 401) { setToken(null); setSt(null); } else toast(e.message, "bad"); }
    finally { setLoading(false); }
  }, []); // eslint-disable-line

  useEffect(() => { if (getToken()) load(); }, [load]);
  useEffect(() => {
    if (!st) return;
    const t = setInterval(() => { if (!document.hidden && ["/", "/library"].includes(hash)) load(); }, 8000);
    return () => clearInterval(t);
  }, [st, hash, load]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><Loader text="Menyiapkan dashboard…" /></div>;
  if (!st) return <Login onIn={() => { setLoading(true); load(); }} />;

  const logout = async () => { try { await api("/auth/logout", { method: "POST" }); } catch { /* */ } setToken(null); setSt(null); setMore(false); go("/"); };
  const [path, arg] = (() => { const parts = hash.split("/").filter(Boolean); return ["/" + (parts[0] || ""), parts[1]]; })();
  const props = { st, reload: load };
  let page;
  switch (path) {
    case "/hitung": page = <Calculator key={arg || "new"} {...props} promoId={arg} />; break;
    case "/rekomendasi": page = <Recommend {...props} />; break;
    case "/kalender": page = <CalendarPage {...props} />; break;
    case "/asisten": page = <Assistant {...props} />; break;
    case "/belajar": page = <Learning {...props} />; break;
    case "/riwayat": page = <HistoryPage {...props} />; break;
    case "/library": page = <Library {...props} />; break;
    case "/promo": page = <PromoDetail key={arg} {...props} id={arg} />; break;
    case "/produk": page = <Products {...props} />; break;
    case "/platform": page = <Platforms {...props} />; break;
    case "/settings": page = <Settings {...props} />; break;
    default: page = <Home {...props} />;
  }
  const viewer = !st.user.isAdmin && st.user.perm === "viewer";
  const HIDE = viewer ? ["/hitung", "/rekomendasi", "/settings", "/riwayat"] : [];
  const nav = NAV.filter((n) => !HIDE.includes(n.to));
  const moreNav = MORE.filter((n) => !HIDE.includes(n.to));
  if (viewer && ["/hitung", "/rekomendasi", "/riwayat"].includes(path)) {
    page = <div className="card p-6 text-[15px]">Halaman ini hanya untuk tim yang menghitung promo. Sebagai Viewer, Anda bisa melihat promo di Library dan Kalender.</div>;
  }
  const active = (to) => (to === "/" ? path === "/" : path === to || (to === "/library" && path === "/promo"));

  return (
    <div className="min-h-screen pb-24 xl:pb-10 overflow-x-clip">
      <header className="sticky top-0 z-40 bg-bata text-cream">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-3">
          <a href="#/" className="flex items-center gap-2 shrink-0" aria-label="Beranda">
            <svg width="30" height="30" viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" fill="#ECE4D4" /><circle cx="38" cy="42" r="5" fill="#B42F27" /><circle cx="62" cy="42" r="5" fill="#B42F27" /><path d="M34 60 Q50 74 66 60" stroke="#B42F27" strokeWidth="6" fill="none" strokeLinecap="round" /></svg>
            <div className="leading-none">
              <div className="text-[10px] font-bold opacity-80">CRK GROUP · Cimol Bojot AA</div>
              <div className="text-[17px]"><b className="font-extrabold">Promo</b> Calculator</div>
            </div>
          </a>
          <nav className="hidden xl:flex ml-4 gap-0.5">
            {[...nav, ...moreNav].map((n) => (
              <a key={n.to} href={`#${n.to}`} className={`relative px-2 py-1.5 rounded-full text-[13px] font-semibold whitespace-nowrap ${active(n.to) ? "text-bata" : "text-cream/85 hover:text-cream"}`}>
                {active(n.to) && <motion.span layoutId="navpill" className="absolute inset-0 rounded-full bg-cream" transition={{ type: "spring", stiffness: 400, damping: 30 }} />}
                <span className="relative">{n.short || n.label}</span>
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden xl:block text-right leading-tight whitespace-nowrap">
              <div className="text-[13px] font-bold">{st.user.name}</div>
              <div className="text-[11px] opacity-80">{st.roles[st.user.role]}</div>
            </div>
            <button onClick={logout} className="hidden xl:flex w-10 h-10 rounded-full hover:bg-bata-dark items-center justify-center" aria-label="Logout"><LogOut size={18} /></button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 pt-4">
        <AnimatePresence mode="wait">
          <motion.div key={path + (arg || "")} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
            {page}
          </motion.div>
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {path !== "/asisten" && (
          <motion.a href="#/asisten" aria-label="Buka asisten promo" title="Asisten promo"
            initial={{ scale: 0, rotate: -30 }} animate={{ scale: 1, rotate: 0 }} exit={{ scale: 0 }} whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}
            className={`fixed z-40 right-4 bottom-20 xl:bottom-6 rounded-full bg-paper border-2 border-bata shadow-lg p-1.5 items-center gap-2 pr-3 ${path === "/hitung" ? "hidden lg:flex" : "flex"}`}>
            <BotFace size={40} />
            <span className="hidden md:inline text-[13px] font-extrabold text-bata">Tanya promo</span>
          </motion.a>
        )}
      </AnimatePresence>

      <nav className="xl:hidden fixed bottom-0 inset-x-0 z-40 bg-paper border-t border-line safe-b">
        <div className="grid" style={{ gridTemplateColumns: `repeat(${nav.length + 1}, minmax(0, 1fr))` }}>
          {nav.map((n) => {
            const I = n.icon; const on = active(n.to);
            return (
              <a key={n.to} href={`#${n.to}`} className={`relative flex flex-col items-center justify-center gap-0.5 h-14 text-[10px] font-semibold ${on ? "text-bata" : "text-ink/60"}`}>
                {on && <motion.span layoutId="bnav" className="absolute top-0 h-[3px] w-10 rounded-full bg-bata" />}
                <motion.span animate={on ? { y: [0, -4, 0] } : {}} transition={{ duration: 0.35 }}><I size={20} /></motion.span>{n.label === "Rekomendasi" ? "Saran" : n.label}
              </a>
            );
          })}
          <button onClick={() => setMore(true)} className={`flex flex-col items-center justify-center gap-0.5 h-14 text-[10px] font-semibold ${moreNav.some((m) => active(m.to)) ? "text-bata" : "text-ink/60"}`}>
            <MoreHorizontal size={21} />Lainnya
          </button>
        </div>
      </nav>
      <Sheet open={more} onClose={() => setMore(false)} title={`Halo, ${st.user.name}`}>
        <div className="grid gap-2">
          {moreNav.map((m) => { const I = m.icon; return (
            <a key={m.to} href={`#${m.to}`} onClick={() => setMore(false)} className="card px-4 h-14 flex items-center gap-3 font-semibold"><I size={20} className="text-bata" />{m.label}</a>
          ); })}
          <button onClick={logout} className="card px-4 h-14 flex items-center gap-3 font-semibold text-bata"><LogOut size={20} />Logout</button>
        </div>
      </Sheet>
    </div>
  );
}
