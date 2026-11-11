# CRK Promo Calculator

Dashboard untuk menghitung apakah promo Cimol Bojot AA **sehat**, **margin-nya bagus**, dan **menarik untuk customer**, setelah HPP dan semua potongan platform (GoFood, GrabFood, ShopeeFood, Shopee, Tokopedia/TikTok Shop). Dashboard ini juga memberi rekomendasi promo terbaik. Spec lengkap ada di `CRK-promo-calculator-emergent-build-spec.md` (project CRK).

Stack: React + Tailwind + framer-motion (frontend), FastAPI (backend), MongoDB. Satu `Dockerfile` untuk Railway: React di-build, lalu disajikan oleh FastAPI di `/`, dengan API di `/api`.

## Isi
- `backend/app/engine.py` — semua rumus: unit economics, potongan platform, skor Sehat/Margin/Menarik, Gate, skenario, saran perbaikan, rekomendasi. Murni Python, tanpa database.
- `backend/app/main.py` — API, login PIN, role, approval flow, laporan publik.
- `backend/app/seed.py` — data dari Price Structure v2 (10 Nov 2026), 8 profil platform, baseline, dan 3 promo contoh.
- `backend/tests/` — 14 test, termasuk semua angka acceptance test di spec.
- `frontend/src/` — halaman Beranda, Kalkulator, Rekomendasi, Library, Detail promo, Produk & HPP, Platform & Biaya, Settings, dan Reporting publik.

## Jalankan lokal
```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --port 8000          # tanpa MONGO_URL → database in-memory
cd ../frontend && npm install && npm run dev   # buka http://localhost:5173
pytest -q backend/tests                    # jalankan dari folder backend
```

## Go-live Railway + Hostinger
1. Push repo ini ke GitHub (mis. `handry-crk/PromoCalculator`), lalu buka Railway → New Project → Deploy from GitHub. Railway akan memakai `Dockerfile`.
2. Railway → + New → Database → MongoDB. Lalu isi variable berikut:
   - `MONGO_URL` (dari plugin MongoDB)
   - `DB_NAME=crk_promo`
   - `USE_MOCK_DB=false`
   - `SECRET_KEY` (teks acak panjang)
   - `DEFAULT_ADMIN_PIN` (bukan 1234)
   - `METRICS_API_KEY`
   - `PUBLIC_BASE_URL`
   - `TZ=Asia/Jakarta`
3. Hostinger → hPanel → Domains → `crkgroup.app` → DNS Zone → tambah CNAME `promo` → alamat dari Railway (Settings → Networking → Custom Domain).
4. Buka `https://promo.crkgroup.app/api/health`. Harus muncul `"db":"mongo"`.
5. Marketing Manager daftar pertama (otomatis jadi Admin) → klik **Import data CRK**.
6. Finance cek **Produk & HPP**. PIC Delivery/Marketplace cocokkan **Platform & Biaya** dengan Merchant/Seller Center, lalu klik **Tandai divalidasi**.
7. Settings → Copy link Reporting → bagikan ke Direksi.

## Role
| Role | Bisa |
|---|---|
| Marketing Manager (Admin) | Semua akses + keputusan akhir + approval anggota + Settings |
| Marketing Team Leader (1 slot) | Sama dengan Promo Planner |
| Revenue Growth Specialist (1 slot) | Sama dengan Finance: review margin, HPP, biaya platform |
| Promo Planner | Hitung, simpan, ajukan, isi hasil aktual |
| Finance | Ubah HPP/harga dan profil biaya platform, review margin |
| Channel PIC | Ubah profil platform yang dia pegang, buat promo channel-nya |
| Viewer | Lihat dan komentar |

## Catatan
- Biaya platform bawaan adalah asumsi publik per Nov 2026 dan ditandai "Belum divalidasi". Selama belum divalidasi, Gate maksimal **GO WITH CONDITION**.
- Biaya pembayaran QRIS di profil Offline default 0%. Isi di Platform & Biaya bila ingin ikut dihitung.
- Kalkulator memanggil `/api/calc` dengan jeda 260 ms setiap kali form berubah, bukan memakai salinan rumus di JavaScript, supaya angka selalu satu sumber.
- Hasil aktual: contribution dihitung dari tambahan revenue × rasio CM/revenue skenario Target − biaya tetap aktual (estimasi). Untuk angka persis, isi potongan platform dari laporan settlement.

## Pendaftaran anggota
- Pendaftaran mandiri hanya untuk 2 slot: **Marketing Team Leader** (1) dan **Revenue Growth Specialist** (1). Slot yang sudah terisi atau menunggu approval tidak bisa dipakai lagi. Kalau pendaftaran ditolak, slotnya terbuka kembali.
- Email wajib `@citarasakuliner.com`. Domain bisa diganti lewat env `EMAIL_DOMAIN`.
- Akun baru berstatus **menunggu** dan tidak bisa login sampai disetujui di **Settings → Approval anggota baru**.
- Role lain (Promo Planner, Finance, Channel PIC, Viewer) hanya bisa diberikan Marketing Manager lewat daftar Anggota.
