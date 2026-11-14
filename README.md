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
3. Hostinger → hPanel → Domains → `crkgroup.app` → DNS Zone → tambah CNAME `promodashboard` → alamat dari Railway (Settings → Networking → Custom Domain).
4. Buka `https://promodashboard.crkgroup.app/api/health`. Harus muncul `"db":"mongo"`.
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
| Viewer | Lihat promo (harga, label skor, status, jadwal) dan komentar. Tidak menerima HPP, CM/GM, contribution, atau rincian potongan; kalkulator dan rekomendasi tertutup |

## Catatan
- Biaya platform bawaan adalah asumsi publik per Nov 2026 dan ditandai "Belum divalidasi". Selama belum divalidasi, Gate maksimal **GO WITH CONDITION**.
- Biaya pembayaran QRIS di profil Offline default 0%. Isi di Platform & Biaya bila ingin ikut dihitung.
- Kalkulator memanggil `/api/calc` dengan jeda 260 ms setiap kali form berubah, bukan memakai salinan rumus di JavaScript, supaya angka selalu satu sumber.
- Hasil aktual: contribution dihitung dari tambahan revenue × rasio CM/revenue skenario Target − biaya tetap aktual (estimasi). Untuk angka persis, isi potongan platform dari laporan settlement.

## Pendaftaran anggota
- **Hanya lewat link undangan.** Marketing Manager membuat link di Settings → Undang anggota. Satu link untuk satu orang, berlaku 7 hari (env `INVITE_DAYS`), bisa dikunci ke satu email, dan bisa dibatalkan. Tanpa link, form daftar tidak muncul dan API menolak (403).
- Login dengan mengetik nama atau email kantor + PIN. Daftar nama anggota tidak lagi tampil di halaman publik.
- Salah PIN 5× per akun atau 20× per alamat IP dalam 15 menit → dikunci 15 menit. Kunci disimpan di database, jadi tidak hilang saat restart.
- Login PIN Admin cadangan mati, kecuali env `ENABLE_ADMIN_PIN=true`.
- Slot mandiri: 2 slot: **Marketing Team Leader** (1) dan **Revenue Growth Specialist** (1). Slot yang sudah terisi atau menunggu approval tidak bisa dipakai lagi. Kalau pendaftaran ditolak, slotnya terbuka kembali.
- Email wajib `@citarasakuliner.com`. Domain bisa diganti lewat env `EMAIL_DOMAIN`.
- Akun baru berstatus **menunggu** dan tidak bisa login sampai disetujui di **Settings → Approval anggota baru**.
- Role lain (Promo Planner, Finance, Channel PIC, Viewer) hanya bisa diberikan Marketing Manager lewat daftar Anggota.

## Event (konser, bazaar, kampus/mall/CFD, corporate)
- Empat profil event di **Platform & Biaya**. Masing-masing berisi harga event (+% dari outlet), revenue share EO, biaya cashless/QRIS, asumsi default (hari, jam, pengunjung, capture, conversion, kapasitas booth), dan template biaya tetap (sewa booth, transport, POSM, crew, genset, konsumsi, izin).
- Hitungan event: transaksi/hari = pengunjung × mampir × beli, dibatasi kapasitas booth. Output: break-even transaksi, event contribution, cost per transaksi, cost per CRM, stok yang dibawa (+20%), dan target per jam.
- Event Scorecard 8 kriteria (≥ 3,8 lanjut, 3,0–3,8 negosiasi, < 3,0 tolak) masuk ke Gate. Event contribution negatif → HOLD, kecuali ada alasan strategis.
- Database lama otomatis mendapat 4 profil event saat aplikasi start. Profil yang sudah ada tidak diubah.

## Kalender promo
Menu **Kalender**: tampilan Bulan dan Timeline per platform. Isinya momen otomatis (tanggal kembar, gajian 25–28, Harbolnas, hari besar; * = perkiraan) dan momen brand sendiri, plus peringatan bentrok, beda harga, dan padat. Klik tanggal untuk membuat promo mulai tanggal itu.

## Asisten timing promo
Menu **Asisten** atau tombol bot di pojok kanan bawah. Tanya dengan bahasa biasa ("kapan promo AOV mozza di GoFood 2 minggu bulan depan?", "cek 1–14 des") atau klik pilihan.
- **Yang dinilai:** pola hari per channel (weekday vs weekend), gajian (25–3), tanggal tua (15–24), musim (Desember, libur sekolah, musim hujan untuk delivery), momen (tanggal kembar dan Harbolnas untuk marketplace, Ramadan, Idul Fitri), objective promo (trial/AOV cari hari ramai, isi jam sepi cari hari sepi), bentrok dan jeda ≥ 14 hari dari promo produk yang sama, maksimal 2 promo bersamaan per platform, persiapan minimal H-7 (event H-14), dan histori achievement promo yang sudah selesai.
- **Skor 0–100 relatif** terhadap semua tanggal mulai dalam rentang yang dinilai. Hasilnya 1 waktu terbaik, 2 alternatif, 1 yang sebaiknya dihindari, dan heatmap skor per tanggal.
- **Dari kalkulator:** tombol "Kapan sebaiknya?". Rekomendasi bisa langsung dipakai ke kalkulator atau dibuka di kalender.
- **Indeks permintaan** adalah asumsi awal di `backend/app/timing.py`. Akan lebih tajam setelah hasil aktual promo diisi.

## Rekomendasi durasi promo
`duration_advice` di `backend/app/timing.py` memberi durasi saran dan rentang wajar. Tampil di kalkulator (kartu "Durasi promo" dengan tombol pakai saran), kartu rekomendasi promo, dan jawaban bot.
- Dasar: tujuan promo, mekanisme (flash sale 1–3 hari, beli-gratis 3–7, bundle/tebus murah 14–30, happy hour 14–28, stamp card ≥ 30), channel (marketplace 1–7 hari, event mengikuti hari event), kedalaman diskon (≥ 30% maks. 7 hari, ≥ 20% maks. 14 hari), skor Sehat, batas investasi strategis, dan histori promo sejenis yang capai target.
- Angka rentang adalah aturan awal; ubah di `DUR_OBJECTIVE` dan `DUR_MECH`.

## Data belajar (hasil promo nyata)
Menu **Data belajar**: masukkan hasil promo yang pernah dijalankan lewat form atau import CSV (template tersedia; pemisah `;` atau `,`). Promo yang ditutup di dashboard dengan hasil aktual ikut masuk otomatis.
- Ukuran hasil: pencapaian vs target (%), atau penilaian 1–5 (Gagal … Sangat berhasil), atau kenaikan revenue (%). Opsional: take rate, diskon, catatan.
- Dipakai oleh: bot timing (pengaruh gajian, momen/hari besar, dan bulan per jenis channel; aktif setelah ≥ 3 hasil per jenis channel; bot juga mengutip promo serupa), rekomendasi promo (pengali performa per jenis promo × platform dan kalibrasi skor Menarik dari take rate, ≥ 3 hasil), dan saran durasi (rata-rata durasi promo sejenis yang capai target, ≥ 3 hasil).
- Settings → **Unduh backup**: semua data dalam satu file JSON (tanpa PIN).
