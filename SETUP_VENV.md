# Menyiapkan dan menjalankan web

Folder `venv/` tidak ikut disertakan dalam paket karena dapat dibuat ulang
kapan saja dan ukurannya besar. Ada dua cara menyiapkannya.

## Cara cepat (Windows)

Klik dua kali dua berkas ini secara berurutan:

1. **`setup.bat`**, cukup sekali. Memeriksa Python, membuat `venv`, memasang
   pustaka, memeriksa basis data, lalu menjalankan 216 pengujian untuk
   memastikan semuanya benar sebelum dipakai.
2. **`run.bat`**, setiap kali ingin membuka aplikasi.

`run.bat` menerima satu argumen opsional:

| Perintah | Hasil |
|---|---|
| `run.bat` | Server produksi (waitress), tanpa pesan debug. Dipakai untuk demonstrasi. |
| `run.bat dev` | Mode pengembangan, kode dimuat ulang otomatis saat diubah. |
| `run.bat uji` | Menjalankan pengujian saja, server tidak dinyalakan. |

Peramban terbuka sendiri setelah jeda tiga detik agar server sempat menyala.

## Cara manual (Windows, Linux, macOS)

```bash
cd web_mbg

python -m venv venv
venv\Scripts\activate            # Windows
source venv/bin/activate         # Linux atau macOS

pip install -r requirements.txt
python -m pytest tests -q        # opsional, memastikan semuanya benar

python app.py                    # mode pengembangan
```

Untuk mode produksi:

```bash
python -m waitress --host=127.0.0.1 --port=5000 app:app    # Windows
gunicorn app:app                                          # Linux
```

## Syarat

- **Python 3.9 atau lebih baru.** `setup.bat` memeriksa versinya dan berhenti
  dengan pesan jelas bila terlalu lama.
- **Basis data** `data/mbg_recommendations_provinsi.db` harus ada. Berkas ini
  keluaran pipeline di Google Colab. Bila hilang, salin dari
  `02_data/processed/database/mbg_recommendations_provinsi.db`.
- **Koneksi internet** hanya saat `setup.bat` dijalankan. Setelah itu aplikasi
  berjalan sepenuhnya luring, sebab Leaflet dan Chart.js sudah disimpan lokal
  di `static/vendor/`. Yang masih daring hanya berkas font dan petak peta;
  keduanya tidak menghalangi aplikasi berjalan.

## Catatan tentang gunicorn

`requirements.txt` memasang gunicorn hanya di sistem selain Windows, memakai
penanda `sys_platform != "win32"`. Gunicorn bergantung pada modul `fcntl` yang
tidak ada di Windows, jadi paketnya akan terpasang tetapi gagal saat
dijalankan. Di Windows pakai waitress, yang sudah ditangani `run.bat`.

## Saat pertama membuka

Aplikasi mengarahkan pengunjung baru melewati tiga halaman penjelasan secara
berurutan: **Tentang**, **Data Mentah**, lalu **Metodologi**. Peta dan menu baru
terbuka setelah ketiganya dilalui. Ini disengaja, bukan galat.

Untuk membaca ulang panduan tersebut, klik tautan "baca ulang panduan" di kaki
halaman.
