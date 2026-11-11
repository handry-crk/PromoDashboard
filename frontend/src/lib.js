// API client + formatting helpers
let token = null;
try { token = localStorage.getItem("crk_promo_token"); } catch { /* storage blocked */ }

export function setToken(t) {
  token = t;
  try { t ? localStorage.setItem("crk_promo_token", t) : localStorage.removeItem("crk_promo_token"); } catch { /* ignore */ }
}
export const getToken = () => token;

export async function api(path, { method = "GET", body, raw } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined && !raw) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, { method, headers, body: raw ? body : body !== undefined ? JSON.stringify(body) : undefined });
  const isJson = (res.headers.get("content-type") || "").includes("json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (isJson && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || "Terjadi kesalahan. Coba lagi.";
    const e = new Error(msg); e.status = res.status; throw e;
  }
  return data;
}

const nf = new Intl.NumberFormat("id-ID");
export const rp = (x) => (x == null || isNaN(x) ? "–" : (x < 0 ? "−Rp" : "Rp") + nf.format(Math.round(Math.abs(x))));
export const num = (x) => (x == null || isNaN(x) ? "–" : nf.format(Math.round(x)));
export const pc = (x, d = 1) => (x == null || isNaN(x) || !isFinite(x) ? "–" : `${(x * 100).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d })}%`);
export const rpShort = (x) => {
  if (x == null || isNaN(x)) return "–";
  const a = Math.abs(x), s = x < 0 ? "−" : "";
  if (a >= 1e9) return `${s}Rp${(a / 1e9).toLocaleString("id-ID", { maximumFractionDigits: 2 })} miliar`;
  if (a >= 1e6) return `${s}Rp${(a / 1e6).toLocaleString("id-ID", { maximumFractionDigits: 1 })} juta`;
  return rp(x);
};
export const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" }) : "–");

export const LABEL_TONE = {
  Sehat: "ok", Bagus: "ok", Menarik: "ok", GO: "ok", Star: "ok",
  Waspada: "warn", Cukup: "warn", "GO WITH CONDITION": "warn", Sleeper: "warn",
  "Tidak Sehat": "bad", "Tidak Sehat — Strategis": "warn", Buruk: "bad", Kurang: "bad", HOLD: "bad", "Margin Trap": "bad", Avoid: "bad",
};
export const TONE_HEX = { ok: "#2F6B4A", warn: "#B8741A", bad: "#B42F27", none: "#212121" };
export const toneOf = (label) => LABEL_TONE[label] || "none";

export const STATUS = {
  draft: "Draft", review_finance: "Review Finance", review_head: "Review Manager", approved: "Approved",
  running: "Running", done: "Selesai", rejected: "Ditolak",
};

export const CH_LABEL = { offline: "Offline", online_food: "Online Food", marketplace: "Marketplace" };

export function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
