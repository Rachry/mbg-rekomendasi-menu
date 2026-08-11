# Sistem Rekomendasi Menu MBG

Aplikasi web yang menyajikan rekomendasi menu Program Makan Bergizi Gratis
untuk 36 provinsi di Indonesia. Menu disusun per provinsi dengan
mempertimbangkan profil kesehatan peserta didik, kecukupan gizi, dan
ketersediaan bahan di daerah masing-masing.

Dibangun sebagai skripsi Program Studi Informatika, Universitas Gunadarma.

## Latar

Menu seragam secara nasional sulit dijalankan karena dua hal. Kebutuhan gizi
berbeda antarjenjang pendidikan, dan bahan yang mudah didapat di satu provinsi
belum tentu mudah didapat di provinsi lain.

Sistem ini mengelompokkan provinsi menurut profil kesehatan peserta didik
dengan K-Means, membobot kriteria kewaspadaan dengan AHP, lalu menyusun menu
yang lolos ketiga syarat: aman terhadap alergi dan intoleransi, sesuai pola
pangan wilayah, dan memenuhi Angka Kecukupan Gizi.

Perhitungan dikerjakan di luar aplikasi pada pipeline Google Colab. Aplikasi
ini hanya membaca hasilnya dari SQLite dan menyajikannya. Tidak ada model yang
dijalankan saat halaman dibuka.

## Isi

| | |
|---|---|
| Menu | 945 |
| Provinsi | 36 |
| Jenjang | SD, SMP, SMA, SMK |
| Bahan | 119, dengan 95 di antaranya terpakai pada menu |
| Data produksi pangan | 15.743 baris, 95 komoditas, 2019 sampai 2025 |

Angka di atas dibaca dari basis data lewat `db.ringkasan()`, bukan ditulis
tangan di template.

## Menjalankan

Butuh Python 3.11 atau lebih baru.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export MBG_SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
gunicorn app:app                   # Windows: python -m waitress --port=5000 app:app
```

Aplikasi menolak berjalan pada mode produksi tanpa `MBG_SECRET_KEY`. Untuk
pengembangan, jalankan `FLASK_ENV=development python app.py`.

Pengguna Windows dapat memakai `setup.bat` sekali, lalu `run.bat`. Rinciannya
di [SETUP_VENV.md](SETUP_VENV.md).

### Container

```bash
docker build -t mbg .
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e MBG_SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") \
  mbg
```

## Konfigurasi

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `MBG_SECRET_KEY` | tidak ada | Wajib di produksi |
| `MBG_TRUSTED_PROXIES` | `0` | Jumlah proxy tepercaya di depan aplikasi |
| `PORT` | `5000` | Disuntikkan platform hosting |
| `WEB_CONCURRENCY` | `1` | Jumlah worker Gunicorn |
| `MBG_RATE_LIMIT` | `240` | Permintaan per IP per menit |
| `MBG_DB_PATH` | `data/…db` | Jalur basis data |

Contoh lengkap di [`deploy/contoh.env`](deploy/contoh.env).

`MBG_TRUSTED_PROXIES` menentukan berapa entri terakhir pada `X-Forwarded-For`
yang dipercaya. Nilai yang terlalu tinggi membuat header itu dapat dipalsukan
sehingga rate limiter dapat dilewati. Isi sesuai jumlah proxy yang benar-benar
ada, dan verifikasi lewat log setelah deploy.

## Struktur

```
app.py              titik masuk, gerbang alur, header keamanan, rate limit
api.py              22 endpoint JSON
pages.py            11 route halaman
db.py               akses SQLite, dibuka read-only
config.py           ambang, label, normalisasi nama provinsi
gunicorn.conf.py    konfigurasi server produksi
data/               basis data hasil pipeline
templates/          14 template Jinja2
static/             CSS, JS, Leaflet, geometri provinsi
tests/              430 kasus uji
```

Basis data dibuka dengan URI `mode=ro`, sehingga aplikasi tidak dapat mengubah
data penelitian. Berkasnya ikut di dalam repositori agar angka yang tampil
terikat pada commit yang sama dengan angka yang dilaporkan.

Leaflet disimpan di `static/vendor/`, bukan dimuat dari CDN, agar peta tetap
berfungsi tanpa koneksi keluar dan Content Security Policy tidak perlu
mengizinkan domain luar.

## API

Seluruh endpoint mengembalikan JSON, tanpa autentikasi, berawalan `/api/`.

```
GET  /api/ringkasan                   angka pokok sistem
GET  /api/menus                       galeri menu, saring provinsi/jenjang/tingkat
GET  /api/menu/<menu_id>              rincian satu menu
GET  /api/recommend                   penyaring lengkap
GET  /api/opsi-filter                 pilihan penyaring yang tersedia
GET  /api/ingredients                 bahan beserta penanda alergen dan halal
GET  /api/provinces                   data pewarnaan peta
GET  /api/province/<int:kode>         rincian satu provinsi
GET  /api/clusters                    profil hasil K-Means
GET  /api/isl/<provinsi>              Indeks Sumber Lokal tiap bahan
GET  /api/produksi-peta               total produksi per provinsi
GET  /api/profil-pangan               Indeks Pola Pangan Wilayah
GET  /health                          probe kesehatan
```

Daftar selengkapnya ada di `api.py`.

## Alur penjelasan

Pengunjung baru diarahkan melewati tiga halaman berurutan sebelum peta dan menu
terbuka: Tentang, Data Mentah, lalu Metodologi. Urutannya ditegakkan di sisi
server, bukan lewat JavaScript.

Tujuannya memastikan pembaca menemui batasan penelitian lebih dulu, sebelum
melihat keluaran yang tampak meyakinkan. Ini bukan kendali akses; data tetap
dapat diambil langsung lewat `/api/`.

## Pengujian

```bash
pip install -r requirements-dev.lock
pytest
coverage run -m pytest && coverage report
```

430 kasus uji, 426 dijalankan dan 4 dilewati. Cakupan kode aplikasi 97 persen.
Urutan pengujian diacak pada tiap jalan agar ketergantungan tersembunyi
antaruji ikut ketahuan.

Setiap push memicu pengujian pada Python 3.11 dan 3.12, pemeriksaan CVE dengan
pip-audit, pemindaian kode dengan Bandit, pemindaian image dengan Trivy, dan
uji asap terhadap container.

## Deployment

Dockerfile di akar repositori berjalan tanpa penyesuaian di Render, Fly.io,
Railway, Koyeb, dan Hugging Face Spaces. Untuk Render tersedia `render.yaml`
yang dapat dipakai lewat menu Blueprint.

Langkah lengkap dan penanganan masalah ada di
[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

## Batasan

Keluaran sistem ini hasil penelitian akademik, bukan pedoman gizi resmi.

Menu tidak memperhitungkan harga; ketersediaan bahan diukur dari produksi, dan
bahan yang banyak diproduksi belum tentu murah di tingkat sekolah. Indeks
Sumber Lokal memperkirakan ketersediaan dari produksi provinsi tanpa
memperhitungkan perdagangan antardaerah, penyimpanan, maupun musim. Data
produksi mencakup 2019 sampai 2025.

Delapan menu mengandung bahan non-halal. Menu tersebut ditandai dan dapat
disaring, tetapi perlu diperhatikan saat menafsirkan hasil.

Rate limiter menyimpan status di memori proses, sehingga batasnya berlaku per
worker. Perilakunya sesuai harapan selama `WEB_CONCURRENCY=1`.

## Lisensi

Kode dilisensikan MIT, lihat [LICENSE](LICENSE).

Data produksi pangan berasal dari Badan Pusat Statistik dan kementerian
terkait, tunduk pada ketentuan penggunaan masing-masing sumber. Rujukan
lengkap ada pada halaman Data Mentah di aplikasi.

Peta menggunakan [Leaflet](https://leafletjs.com/) dengan ubin dari
OpenStreetMap dan CARTO.

Laporan keamanan: lihat [SECURITY.md](SECURITY.md).
