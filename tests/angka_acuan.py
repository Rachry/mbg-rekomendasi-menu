"""
angka_acuan.py: angka pokok basis data, dikumpulkan di satu tempat.

Mengapa dipusatkan
------------------
Angka seperti jumlah menu sebelumnya ditulis tersebar di tujuh berkas uji.
Setiap kali pipeline dijalankan ulang dengan data baru, tujuh tempat harus
disunting satu per satu, dan kalau ada yang terlewat pengujian gagal karena
alasan yang tidak ada hubungannya dengan cacat kode.

Sekarang angkanya hanya ada di sini. Pembaruan data cukup mengubah berkas ini,
sedangkan pengujian tetap menjalankan fungsinya: berteriak bila ada fungsi yang
tidak sepakat dengan angka acuan.

Cara memperbarui
----------------
Jalankan `python tests/angka_acuan.py` dari folder aplikasi. Skrip akan
mencetak angka yang sebenarnya ada di basis data, lalu salin ke bawah ini.
Jangan menyalin tanpa memeriksa: perubahan angka menu berarti hasil penelitian
ikut berubah, dan naskah perlu ikut disesuaikan.

Riwayat
-------
937 menu, 129 baris provinsi   -> data MBG 4 Agustus 2026
945 menu, 130 baris provinsi   -> data MBG 7 Agustus 2026, satu kombinasi
                                  provinsi-jenjang yang semula tidak dilaporkan
                                  API menjadi tersedia
5.561 komposisi, 8 non-halal   -> 10 Agustus 2026, cakupan Indeks Sumber Lokal
                                  diperluas ke buah, sayuran, dan lemak. Bahan
                                  yang terpilih berubah, sehingga jumlah baris
                                  komposisi dan menu bermuatan non-halal ikut
                                  bergeser. Jumlah menu tidak berubah karena
                                  ditentukan tingkat kewaspadaan, bukan bahan.
"""

TOTAL_MENU = 945
TOTAL_KOMPOSISI = 5_561
TOTAL_PROVINCES = 130          # baris provinsi x jenjang pada tabel provinces
TOTAL_PROVINSI_MENU = 36       # provinsi berbeda yang punya menu
TOTAL_BAHAN = 119
BAHAN_TERPAKAI = 95        # bahan yang benar-benar muncul pada menu
TOTAL_ISL = 4_522
MENU_NON_HALAL = 8

# Cakupan data produksi
TOTAL_BARIS_PRODUKSI = 15_743
TAHUN_PRODUKSI = (2019, 2025)


if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import db

    with db._connect() as con:
        def n(sql):
            return con.execute(sql).fetchone()[0]
        nyata = {
            "TOTAL_MENU": n("SELECT COUNT(*) FROM menu_provinsi"),
            "TOTAL_KOMPOSISI": n("SELECT COUNT(*) FROM menu_provinsi_komposisi"),
            "TOTAL_PROVINCES": n("SELECT COUNT(*) FROM provinces"),
            "TOTAL_PROVINSI_MENU": n("SELECT COUNT(DISTINCT provinsi) FROM menu_provinsi"),
            "TOTAL_BAHAN": n("SELECT COUNT(*) FROM ingredients"),
            "BAHAN_TERPAKAI": n("SELECT COUNT(DISTINCT nama_bahan) FROM menu_provinsi_komposisi"),
            "TOTAL_ISL": n("SELECT COUNT(*) FROM ingredient_locality"),
            "MENU_NON_HALAL": n("SELECT COUNT(*) FROM menu_provinsi WHERE mengandung_non_halal=1"),
            "TOTAL_BARIS_PRODUKSI": n("SELECT COUNT(*) FROM produksi_pangan"),
        }
    sekarang = {k: globals()[k] for k in nyata}
    lebar = max(len(k) for k in nyata)
    print(f"{'angka':<{lebar}}  {'tertulis':>10}  {'di basis data':>14}")
    beda = 0
    for k, v in nyata.items():
        tanda = "" if sekarang[k] == v else "   <- BERBEDA"
        beda += sekarang[k] != v
        print(f"{k:<{lebar}}  {sekarang[k]:>10,}  {v:>14,}{tanda}")
    print(f"\n{beda} angka perlu diperbarui" if beda else "\nSeluruh angka acuan sudah cocok.")
