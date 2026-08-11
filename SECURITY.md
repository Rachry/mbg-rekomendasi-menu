# Kebijakan Keamanan

## Apa yang dilindungi

Aplikasi ini melayani data publik hasil penelitian dan tidak menyimpan data
pribadi siapa pun. Tidak ada akun, tidak ada login, tidak ada formulir yang
menerima unggahan. Basis datanya dibuka dalam mode baca-saja dan tidak pernah
ditulis saat aplikasi berjalan.

Dampak terburuk dari celah keamanan di sini karena itu bukan kebocoran data
pribadi, melainkan halaman yang dirusak atau layanan yang dibuat tidak
tersedia. Meski begitu, laporan tetap dihargai.

## Melaporkan celah

Laporkan lewat tab Security pada repositori ini, menu Report a vulnerability.
Jalur itu bersifat privat sampai laporannya ditanggapi.
Bila tab tersebut tidak tersedia, buka issue dengan judul diawali `[KEAMANAN]`
tanpa menyertakan rincian yang memudahkan penyalahgunaan.

Sertakan langkah untuk mereproduksi, dampak yang Anda perkirakan, dan versi
atau commit yang diuji. Balasan diusahakan dalam tujuh hari.

## Yang sudah diterapkan

| Lapisan | Tindakan |
|---|---|
| Basis data | Dibuka read-only lewat URI `mode=ro`. Seluruh kueri terparameter; tidak ada nilai dari pengguna yang disisipkan ke teks SQL. |
| Masukan | Daftar putih untuk seluruh penyaring, pemotongan panjang pada pencarian bebas, batas ukuran badan permintaan ditegakkan Werkzeug. |
| Keluaran | CSP dengan nonce berbeda tiap respons, tanpa `unsafe-inline` pada `script-src`. `object-src 'none'`, `frame-ancestors 'none'`. |
| Transport | HSTS dikirim hanya pada koneksi HTTPS. TLS diakhiri di sisi platform. |
| Ketersediaan | Pembatas laju token bucket per alamat IP. Batas waktu permintaan, daur ulang worker berkala. |
| Container | Multi-stage, berjalan sebagai UID 10001 non-root, tanpa compiler dan tanpa curl pada image runtime. |
| Rantai pasok | Dependensi dikunci beserta hash, dipasang dengan `--require-hashes`. Dipindai `pip-audit` dan Trivy pada tiap push dan tiap minggu. |
| Kode | Dipindai Bandit pada tiap push. Pengecualian ditandai per baris beserta alasannya, bukan dimatikan menyeluruh. |

## Batasan yang diketahui

Ditulis terbuka karena menyembunyikannya tidak membuat siapa pun lebih aman.

1. **Pembatas laju berlaku per proses, bukan per layanan.** Statusnya disimpan
   di memori worker. Selama `WEB_CONCURRENCY=1` perilakunya sesuai harapan.
   Menaikkan jumlah worker melipatgandakan batas efektif tanpa peringatan.

2. **`style-src` masih mengizinkan `unsafe-inline`.** Template memakai dua
   puluh atribut `style=`, dan atribut style tidak dapat membawa nonce.
   Menghapusnya menuntut pemindahan seluruh atribut itu ke kelas CSS. CSS yang
   disisipkan tidak dapat menjalankan kode, jadi risikonya jauh di bawah
   `script-src`.

3. **Gerbang alur penjelasan bukan kendali akses.** Fungsinya memastikan
   pembaca menemui batasan penelitian lebih dulu. Seluruh data tetap dapat
   diambil langsung lewat `/api/`, dan itu memang disengaja.

4. **`MBG_TRUSTED_PROXIES` harus benar.** Nilai yang terlalu tinggi membuat
   header `X-Forwarded-For` dapat dipalsukan sehingga pembatas laju dapat
   dilewati. Bawaannya nol, yang aman. Angkanya wajib diperiksa ulang setiap
   kali platform atau lapisan proxy berubah.

5. **Base image belum dipatok ke digest.** Ada penjelasan dan perintahnya di
   dalam `Dockerfile`. Sampai dipatok, build belum sepenuhnya dapat
   direproduksi.

## Di luar cakupan

- Serangan penolakan layanan pada tingkat jaringan. Itu tanggung jawab platform.
- Celah pada platform hosting atau pada infrastruktur GitHub.
- Absennya batas laju pada `/static/`, yang memang disengaja karena berkas
  statis dilayani platform dan tidak menyentuh basis data.
