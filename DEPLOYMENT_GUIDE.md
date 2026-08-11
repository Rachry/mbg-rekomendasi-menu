# Panduan Deployment

Web ini di-deploy dari push ke GitHub. Tidak ada langkah manual di server,
tidak ada berkas yang disalin lewat SSH. Satu commit ke `main` memicu build,
dan bila CI hijau, versi barunya menggantikan yang lama.

Panduan ini berlaku untuk platform mana pun yang membangun dari Dockerfile.
Yang berbeda antarplatform hanya tempat mengisi variabel lingkungan.

---

## 1. Sekali di awal: siapkan repo

```bash
cd web_mbg_20260811
git init -b main
git add .
git commit -m "Web MBG: versi siap hosting"
git remote add origin https://github.com/<akun>/<nama-repo>.git
git push -u origin main
```

Periksa dulu bahwa tidak ada yang seharusnya tidak ikut:

```bash
git status --short
git ls-files | grep -iE '\.env$|\.pem$|\.key$'    # harus kosong
```

Basis data `data/mbg_recommendations_provinsi.db` memang ikut ter-commit.
Ukurannya 5,8 MB, jauh di bawah batas berkas GitHub sebesar 100 MB. Ini
disengaja: angka yang tampil di web jadi terikat pada commit yang sama dengan
angka di naskah, dan container tidak membutuhkan volume persisten.

---

## 2. Sekali di awal: patok yang masih longgar

Dua hal sengaja dibiarkan memakai tag, karena memasukkan nilai karangan jauh
lebih berbahaya daripada memakai tag. Kerjakan keduanya dari mesin yang punya
Docker dan koneksi internet.

**Base image ke digest.**

```bash
docker pull python:3.11-slim-bookworm
docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim-bookworm
```

Ganti kedua baris `FROM` di `Dockerfile` dengan hasilnya.

**Action GitHub ke SHA commit.**

```bash
bash deploy/pin-actions.sh            # lihat dulu
bash deploy/pin-actions.sh --tulis    # terapkan
git diff .github/workflows
```

Alasannya ada di dalam kedua berkas itu. Ringkasnya: tag dapat dipindahkan,
SHA tidak. Setelah dipatok, Dependabot yang menjaganya tetap mutakhir lewat
pull request yang bisa dibaca sebelum digabung.

---

## 3. Sambungkan platform

### Render

Cara tercepat memakai `render.yaml` yang sudah ada di repo: **New > Blueprint**,
arahkan ke repo, setujui. Seluruh pengaturan terbaca dari berkas itu, termasuk
pembuatan `MBG_SECRET_KEY` secara acak.

Bila ingin manual: **New > Web Service**, pilih repo, Runtime **Docker**,
Health Check Path `/health`, lalu isi variabel dari tabel di bawah.

### Fly.io, Railway, Koyeb, Hugging Face Spaces

Semuanya membaca `Dockerfile` di akar repo tanpa penyesuaian. Yang perlu
dilakukan hanya mengisi variabel lingkungan lewat antarmuka masing-masing.

Hugging Face Spaces mengharapkan port 7860, jadi tambahkan `PORT=7860` di
sana. Platform lain menyuntikkan `PORT` sendiri.

---

## 4. Variabel lingkungan

| Variabel | Wajib | Nilai | Catatan |
|---|---|---|---|
| `MBG_SECRET_KEY` | **Ya** | 64 karakter heksadesimal acak | Aplikasi menolak start tanpa ini di produksi |
| `MBG_TRUSTED_PROXIES` | Sangat dianjurkan | `1` di belakang satu proxy | Baca peringatan di bawah |
| `FLASK_ENV` | Tidak | `production` | Sudah menjadi bawaan pada image |
| `WEB_CONCURRENCY` | Tidak | `1` | Baca alasannya di `gunicorn.conf.py` |
| `MBG_RATE_LIMIT` | Tidak | `240` | Per alamat IP per menit, per worker |
| `PORT` | Tidak | disuntikkan platform | Isi manual hanya di HF Spaces |

Hasilkan kunci dengan:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Peringatan soal `MBG_TRUSTED_PROXIES`.** Nilainya menentukan berapa entri
terakhir pada header `X-Forwarded-For` yang dipercaya. Diisi terlalu tinggi,
siapa pun cukup mengirim header itu untuk memilih alamat IP-nya sendiri, dan
pembatas laju kehilangan seluruh maknanya. Diisi terlalu rendah, seluruh
pengunjung dihitung sebagai satu alamat dan satu bot dapat memblokir semua
orang. Nilai bawaan nol berarti header tidak dipercaya sama sekali, dan itu
memang bawaan yang benar: salahnya merugikan pengunjung, bukan menguntungkan
penyerang.

Setelah deploy, buka log dan kirim satu permintaan. Bila alamat yang tercatat
adalah alamat internal platform dan bukan alamat Anda, angkanya masih terlalu
rendah.

---

## 5. Verifikasi setelah deploy

```bash
URL=https://<nama>.onrender.com

# Kesehatan dan penanda rilis. `rilis` harus berubah tiap deploy.
curl -s $URL/health

# Alur penjelasan: pengunjung baru harus dilempar ke /tentang
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  -H 'Accept: text/html' $URL/

# Header keamanan
curl -sI $URL/tentang | grep -iE 'content-security|strict-transport|x-frame'

# Mesin pencari tidak diundang
curl -s $URL/robots.txt
```

Yang harus terlihat pada header CSP: `'nonce-...'` dan `'strict-dynamic'` pada
`script-src`, dan **tidak ada** `'unsafe-inline'` di sana.

Lalu buka di peramban dan periksa konsol. Kalau ada pesan yang menyebut
Content Security Policy, berarti ada tag `<script>` yang kehilangan atribut
`nonce`. Gejalanya khas: halaman tampil tetapi tidak ada yang berfungsi, dan
tidak ada pesan galat di sisi server. Periksa dengan:

```bash
grep -o '<script[^>]*>' templates/*.html | grep -v nonce
```

Keluarannya harus kosong.

**Uji terpenting: klik berkali-kali.** Buka alur dari awal sampai akhir, lalu
berpindah antarhalaman sepuluh sampai dua puluh kali. Sebelum revisi ini, kira
kira tiga dari empat klik akan melempar Anda kembali ke halaman Tentang.
Sekarang tidak boleh ada satu pun.

---

## 6. Sebelum sidang

- [ ] Buka web lima sampai sepuluh menit sebelum mulai. Pada tier gratis
      Render, instance yang tidur butuh 10 sampai 30 detik untuk bangun.
- [ ] Siapkan tangkapan layar cadangan seandainya jaringan ruang sidang
      bermasalah.
- [ ] Catat URL dan commit SHA yang sedang berjalan, supaya cocok dengan yang
      tertulis di naskah.
- [ ] Periksa `curl -s $URL/health` menampilkan jumlah menu dan provinsi yang
      sama dengan angka di Bab 4.

---

## 7. Menjalankan container secara lokal

Berguna untuk memastikan yang berjalan di server sama dengan yang diuji.

```bash
docker build -t mbg:lokal .

docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e MBG_SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") \
  -e MBG_RILIS=lokal \
  mbg:lokal
```

Buka http://127.0.0.1:8080. Nomor port sengaja bukan 5000: itulah yang
membuktikan aplikasi benar-benar membaca `PORT` dan bukan angka tetap.

Periksa juga bahwa prosesnya bukan root:

```bash
docker run --rm mbg:lokal id -u     # harus 10001
```

---

## 8. Jalur alternatif: VPS dengan Nginx

Berkas `deploy/nginx.conf` dan `deploy/mbg.service` masih ada untuk jalur ini,
tetapi bukan lagi jalur utama dan tidak ikut diuji CI. Bila dipakai, pastikan
`MBG_TRUSTED_PROXIES=1` dan `MBG_SECRET_KEY` terisi di `EnvironmentFile`, dan
jalankan lewat `gunicorn app:app` supaya `gunicorn.conf.py` ikut terbaca.

---

## 9. Bila terjadi masalah

| Gejala | Penyebab yang paling mungkin |
|---|---|
| Build gagal di langkah pip | Hash pada `requirements.lock` tidak cocok. Jalankan ulang `pip-compile`. |
| "No open ports detected" | `PORT` tidak terbaca. Pastikan `gunicorn.conf.py` ikut ter-commit. |
| Container mati saat start | `MBG_SECRET_KEY` belum diisi. Cek log, pesannya eksplisit. |
| Halaman tampil tetapi mati total | Ada `<script>` tanpa `nonce`. Lihat bagian 5. |
| Terus dilempar ke /tentang | `MBG_RILIS` berbeda antarworker, atau `WEB_CONCURRENCY` dinaikkan. |
| Semua pengunjung kena rate limit | `MBG_TRUSTED_PROXIES` terlalu rendah. |
| Rate limit tidak pernah aktif | `MBG_TRUSTED_PROXIES` terlalu tinggi. |
| Halaman pertama lambat sekali | Instance tidur. Wajar pada tier gratis. |
