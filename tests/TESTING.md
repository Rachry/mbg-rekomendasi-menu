# Laporan Pengujian: Web Rekomendasi Menu MBG

**Terakhir dijalankan:** 11 Agustus 2026
**Basis data yang diuji:** `mbg_recommendations_provinsi.db`, 19 tabel, 945 menu,
5.561 baris komposisi, 130 baris provinsi, 15.743 baris produksi
**Perkakas:** pytest 8.3.3, coverage.py 7.6.1
**Hasil:** **417 kasus uji, seluruhnya lulus**, waktu jalan sekitar 32 detik

---

## 1. Ringkasan

| Golongan | Kasus Uji | Bagian |
|---|---|---|
| Whitebox | 204 | 49 persen |
| Blackbox | 213 | 51 persen |
| **Jumlah** | **417** | **100 persen** |

| Ukuran cakupan | Hasil |
|---|---|
| Cakupan pernyataan | **97 persen** dari 1.141 pernyataan |
| Cakupan cabang | **97 persen** dari 308 cabang |
| Pernyataan tidak teruji | 31 |
| Cabang tidak teruji sebagian | 16 |

Cakupan cabang biasanya lebih rendah daripada cakupan pernyataan, sebab satu
pernyataan bercabang dapat terlewati sebagian. Pada aplikasi ini keduanya sama
tinggi, yang berarti percabangan keputusan benar-benar diuji pada kedua
kemungkinannya, bukan hanya pada jalur yang lazim dilalui.

---

## 2. Pengujian Whitebox

Pengujian whitebox menguji dengan melihat isi kode, sehingga dapat menyasar
cabang keputusan, jalur galat, dan keadaan batas yang tidak terlihat dari luar.
Seluruhnya memanggil fungsi modul secara langsung tanpa melewati lapisan HTTP.

| Berkas | Sasaran | Kasus |
|---|---|---|
| `test_db.py` | Lapisan basis data, termasuk `recommend()` dan Indeks Sumber Lokal | 77 |
| `test_skrip.py` | Sintaks skrip, variabel tak dideklarasikan, keutuhan tema | 33 |
| `test_galat.py` | Jalur kegagalan dan penangan galat | 24 |
| `test_produksi.py` (bagian whitebox) | Kueri produksi dan koreksi data di hulu | 20 |
| `test_data_produksi.py` (bagian whitebox) | Kueri produksi berpenyaring dan angka ringkasan | 17 |
| `test_agregat.py` | Kesetaraan tabel agregat terhadap tabel dasar | 16 |
| `test_galat.py` tambahan | Pemangkasan gema pesan galat | (termasuk di atas) |
| `test_config.py` | Fungsi murni dan konstanta pada `config.py` | 10 |
| `test_notebook_mandiri.py` | Keterjalanan sel notebook secara mandiri | 4 |
| **Jumlah** | | **204** |

### Teknik yang dipakai

**Cakupan pernyataan dan cabang.** Diukur dengan `coverage.py` pada dua mode.
Hasilnya dilaporkan apa adanya pada Bagian 4, termasuk daftar baris yang tidak
teruji beserta alasannya.

**Analisis nilai batas.** Diterapkan pada parameter yang punya rentang sah:

| Yang diuji | Nilai batas yang diuji |
|---|---|
| Batas baris tabel produksi | 0, 1, 100, 500, 999999 |
| Offset pemuatan bertahap | −5, 0, total−10, total |
| Ambang skor risiko bahan | Tepat pada ambang dan satu takik di atasnya |
| Rasio kecukupan gizi | 0,80 dan 1,20 sebagai batas terima |

**Pengujian kesetaraan.** Tabel agregat memuat angka turunan yang seharusnya
sama dengan hasil hitung langsung dari tabel dasar. Kesetaraan itu diuji pada
865 kombinasi penyaring. Uji ini penting sebab tabel agregat dapat menjadi basi
tanpa gejala apa pun.

Struktur, nama, bilangan bulat, dan urutan baris dibandingkan persis. Angka
pecahan dibandingkan sampai ketelitian yang ditampilkan, yaitu satu satuan pada
desimal terakhir. Pelonggaran itu diperlukan sebab kedua jalur memakai algoritma
penjumlahan yang berbeda: pipeline menjumlah dengan pandas, sedangkan jalur
cadangan memakai SUM() milik SQLite yang sejak versi 3.45 memakai penjumlahan
Kahan-Babuska. Bila nilai sebenarnya jatuh tepat di titik pembulatan, keduanya
membulatkan ke sisi berlawanan. Toleransinya tetap ketat, dan diuji tersendiri
bahwa ia masih menolak selisih sepuluh kali lebih besar, perbedaan bilangan
bulat, perbedaan nama, maupun pertukaran urutan.

**Pengujian keteraturan urutan.** Pengurutan yang tidak pasti saat nilainya
seri pernah membuat tampilan berubah antar pemuatan meski datanya sama. Uji
mengunci agar tiap kueri memiliki pemecah seri yang tetap.

---

## 3. Pengujian Blackbox

Pengujian blackbox menguji lewat antarmuka tanpa melihat kodenya, menilai
apakah aplikasi berperilaku sesuai kebutuhan yang ditetapkan. Seluruhnya
melewati klien HTTP, sama seperti yang dialami pengunjung.

| Berkas | Sasaran | Kasus |
|---|---|---|
| `test_produksi.py` (bagian blackbox) | Halaman produksi dan alamat datanya | 21 |
| `test_api.py` | Alamat data JSON dan pemeriksaan parameter | 36 |
| `test_cari_bahan.py` | Penyaring cari bahan dan penanda lokal pada kartu | 30 |
| `test_app.py` | Kepala tanggapan, singgahan, pembatas laju permintaan | 29 |
| `test_klaim_halaman.py` | Kesesuaian pernyataan halaman dengan isi basis data | 27 |
| `test_navigasi.py` | Remah navigasi, penanda bahan lokal, daftar istilah | 25 |
| `test_gerbang.py` | Alur penjelasan wajib tiga langkah | 23 |
| `test_data_produksi.py` (bagian blackbox) | Alamat dan tampilan tab produksi | 22 |
| **Jumlah** | | **213** |

### Teknik yang dipakai

**Partisi ekuivalensi.** Masukan tiap parameter dibagi menjadi tiga golongan,
lalu diambil satu wakil tiap golongan.

| Golongan | Contoh masukan | Perilaku yang diharapkan |
|---|---|---|
| Sah | `provinsi=Aceh`, `tahun=2023` | Balasan 200 berisi data yang menyempit |
| Tidak sah | `provinsi=Wakanda`, `tahun=1900`, `batas=abc` | Balasan 400 disertai nama parameternya |
| Kosong | `provinsi=`, tanpa parameter | Dianggap tidak menyaring, bukan galat |

Penetapan ini penting. Versi aplikasi terdahulu membalas 200 disertai seluruh
nilai nol ketika parameternya keliru, sehingga kekeliruan pengetikan
menghasilkan jawaban yang tampak sah padahal seluruhnya kosong.

**Analisis nilai batas.** Diterapkan pada batas jumlah baris, batas tahun 2019
dan 2025 sebagai ujung rentang data, serta panjang kata kunci pencarian.

**Pengujian kesesuaian pernyataan terhadap data.** Golongan uji yang baru
ditambahkan pada 10 Agustus 2026. Tiap pernyataan berangka pada halaman
penjelasan dicocokkan langsung ke basis data saat pengujian berjalan, bukan
dicocokkan ke angka yang ditulis pada berkas uji. Dengan begitu halaman tidak
dapat lagi menyatakan sesuatu yang bertentangan dengan datanya.

**Pengujian regresi cacat.** Sebagian kasus uji ditulis khusus untuk mengunci
cacat yang pernah ditemukan, sehingga tidak dapat muncul kembali tanpa
ketahuan. Rinciannya pada Bagian 6.

---

## 4. Cakupan Kode

### Cakupan pernyataan

| Modul | Pernyataan | Tidak teruji | Cakupan |
|---|---|---|---|
| `db.py` | 564 | 7 | 99 persen |
| `config.py` | 88 | 2 | 98 persen |
| `api.py` | 238 | 10 | 96 persen |
| `app.py` | 171 | 12 | 93 persen |
| `pages.py` | 62 | 0 | 100 persen |
| **Jumlah** | **1.141** | **31** | **97 persen** |

### Cakupan cabang

| Modul | Cabang | Teruji sebagian | Cakupan gabungan |
|---|---|---|---|
| `db.py` | 158 | 6 | 98 persen |
| `config.py` | 20 | 0 | 98 persen |
| `api.py` | 70 | 6 | 95 persen |
| `app.py` | 48 | 4 | 92 persen |
| `pages.py` | 12 | 0 | 100 persen |
| **Jumlah** | **308** | **16** | **97 persen** |

### Baris yang tidak teruji dan alasannya

Tiga puluh satu pernyataan tidak teruji, seluruhnya merupakan jalur yang tidak
dapat dipicu dari dalam proses pengujian. Didaftar terbuka ketimbang dibiarkan
sebagai selisih tanpa keterangan.

| Modul | Baris | Sebab tidak teruji |
|---|---|---|
| `app.py` | 163-164, 181-182 | Pemasangan lapisan pengenal proxy, hanya aktif di belakang server web |
| `app.py` | 223-226 | Penangan galat sistem berkas saat basis data hilang di tengah jalan |
| `app.py` | 360, 392 | Blok penjalanan langsung, tidak dipanggil saat modul diimpor |
| `api.py` | 128-129, 395-398 | Jalur cadangan ketika tabel agregat tidak tersedia |
| `db.py` | 802-803, 960-965 | Jalur cadangan perhitungan langsung bila agregat basi |
| `config.py` | 621-622 | Pembacaan kunci rahasia dari lingkungan produksi |

Jalur cadangan agregat sengaja tidak diuji lewat pengujian biasa sebab
memerlukan basis data yang sengaja dirusak. Kesetaraan hasilnya sudah diuji
tersendiri pada `test_agregat.py` dengan cara membandingkan kedua jalur pada
data yang sama.

---

## 5. Penelusuran Kebutuhan Fungsional

Tiap kebutuhan fungsional pada dokumen spesifikasi dipetakan ke sekurangnya
satu kasus uji. Dinyatakan terbuka pula kebutuhan yang belum terjangkau.

| Kelompok kebutuhan | Kode | Berkas uji | Terjangkau |
|---|---|---|---|
| Alur penjelasan wajib | FR-001 sampai FR-004 | `test_gerbang.py` | Ya |
| Peta interaktif | FR-005 sampai FR-010 | `test_api.py`, `test_produksi.py` | Ya |
| Pencarian dan penyaringan peta | FR-011 sampai FR-014 | `test_api.py` | Ya |
| Detail provinsi | FR-015 sampai FR-017 | `test_navigasi.py` | Ya |
| Penyajian dan penandaan menu | FR-018 sampai FR-023 | `test_db.py`, `test_cari_bahan.py` | Ya |
| Galeri menu | FR-024, FR-025 | `test_app.py` | Ya |
| Penyaringan menurut kebutuhan | FR-026 sampai FR-032 | `test_cari_bahan.py`, `test_db.py` | Ya |
| Halaman data dan rujukan | FR-033 sampai FR-038 | `test_klaim_halaman.py`, `test_data_produksi.py` | Ya |
| Navigasi | FR-039 | `test_navigasi.py` | Ya |
| Data tidak tersedia dan pembedaan nol | FR-040, FR-041 | `test_data_produksi.py`, `test_klaim_halaman.py` | Ya |

Kebutuhan nonfungsional yang terjangkau pengujian otomatis mencakup waktu
tanggap, muatan tiap permintaan, pemuatan bertahap, halaman galat yang tetap
terbaca, pembatas laju permintaan, basis data baca saja, dan kueri berparameter
terikat. Kebutuhan yang tidak terjangkau pengujian otomatis, yaitu keterpakaian
bagi pengguna awam dan keterpindahan antar lingkungan, dinyatakan pada Bagian 7
sebagai batasan.

---

## 6. Cacat yang Terkunci Uji Regresi

Sebagian kasus uji ditulis setelah cacatnya ditemukan, khusus untuk memastikan
cacat itu tidak dapat kembali tanpa ketahuan.

| Cacat yang pernah terjadi | Kini terkunci oleh |
|---|---|
| Halaman galat pernah kosong sepenuhnya | `test_galat.py` |
| Pembatas laju permintaan tidak pulih dalam waktu wajar | `test_app.py` |
| Galat sintaks skrip sisi depan mematikan seluruh skrip satu halaman tanpa satu pun uji gagal | `test_skrip.py` |
| Parameter keliru dibalas 200 berisi nilai nol, bukan 400 | `test_api.py` |
| Pengurutan tidak pasti saat nilai seri membuat tampilan berubah antar pemuatan | `test_db.py`, `test_agregat.py` |
| Pembulatan di SQL dan di Python memakai aturan berbeda, sehingga kedua jalur agregat berselisih pada mesin ber-SQLite 3.45 ke atas | `test_agregat.py` |
| Halaman Tentang menyatakan sebagian data hasil estimasi padahal tidak ada satu pun | `test_klaim_halaman.py` |
| Halaman Metodologi menyebut bobot berasal dari rata-rata geometrik, padahal rata-rata kolom | `test_klaim_halaman.py` |
| Persentase makan siang tertulis 30-35 persen, padahal 32,5 dan 35 persen | `test_klaim_halaman.py` |
| Penyaring provinsi memecah satu provinsi menjadi beberapa pilihan karena beda ejaan | `test_data_produksi.py` |
| Angka desimal ditulis dengan titik, tidak sesuai kaidah bahasa Indonesia | `test_klaim_halaman.py` |
| Pembulatan di SQL dan di Python memakai aturan berbeda, sehingga kedua jalur agregat berselisih pada mesin ber-SQLite 3.45 ke atas | `test_agregat.py` |
| Rujukan ke variabel yang sudah dihapus menghentikan seluruh skrip peta, sehingga kotak Cari provinsi diam tanpa gejala | `test_skrip.py` |
| Pesan galat menggemakan masukan sepanjang apa pun, sehingga muatan balasan dapat diperbesar penyerang | `test_galat.py` |
| Saldo pembatas laju bocor antar kasus uji, sehingga hasil pengujian bergantung urutan | `test_app.py`, `conftest.py` |

---

## 7. Batasan Pengujian

Pengujian ini **tidak mencakup**:

- **Uji beban.** Aplikasi dirancang untuk volume data tetap dan jumlah pengguna
  kecil, sehingga perilakunya pada beban tinggi tidak diuji.
- **Uji lintas peramban.** Skrip sisi depan hanya diperiksa sintaksnya, bukan
  perilakunya pada berbagai peramban dan versi.
- **Uji ketersediaan jangka panjang.** Perilaku aplikasi setelah berjalan
  berhari-hari tanpa henti tidak diuji.
- **Uji keterpakaian dengan pengguna sungguhan.** Syarat bahwa antarmuka dapat
  dipakai tanpa keahlian teknis dinilai lewat telaah, bukan lewat pengamatan
  pengguna.
- **Uji keamanan menyeluruh.** Yang diuji terbatas pada kueri berparameter
  terikat, basis data baca saja, kepala tanggapan keamanan, dan pembatas laju.
  Uji penetrasi tidak dilakukan.

Dua berkas uji memerlukan Node.js untuk memeriksa sintaks JavaScript. Bila Node
tidak terpasang, pengujian itu dilewati disertai alasan yang jelas, bukan
diganti pemeriksaan lemah yang dapat menyesatkan.

---

## 8. Cara Menjalankan

```bash
cd 09_web-mbg/web_mbg_fixed1/web_mbg
pip install -r requirements.txt

python -m pytest tests -q                      # seluruh 417 kasus uji
python -m pytest tests -q -p randomly          # urutan diacak, harus tetap lulus
python -m pytest tests/test_db.py -q           # satu berkas saja
python -m pytest tests -q -k "wb_"             # hanya whitebox tab produksi
python -m pytest tests -q -k "bb_"             # hanya blackbox tab produksi

# cakupan pernyataan
python -m coverage run --source=. --omit="tests/*,venv/*" -m pytest tests -q
python -m coverage report

# cakupan cabang
python -m coverage run --branch --source=. --omit="tests/*,venv/*" -m pytest tests -q
python -m coverage report -m

# bandingkan angka acuan terhadap isi basis data
python tests/angka_acuan.py
```

Angka pokok seperti jumlah menu dan jumlah baris komposisi dipusatkan pada
`tests/angka_acuan.py`. Pembaruan data cukup menyunting berkas itu, dan
pengujian tetap menjalankan fungsinya, yaitu berteriak bila ada fungsi yang
tidak sepakat dengan angka acuan.
