"""
test_agregat.py: mengunci prinsip "pipeline menghitung, aplikasi menampilkan".

Seluruh angka turunan dihitung sel P10 pipeline lalu disimpan sebagai tabel
`agg_*`. Aplikasi hanya membacanya. Jalur cadangan yang menghitung ulang tetap
ada, tetapi hanya menyala bila tabel agregat belum ada atau sudah basi.

Pengujian di bawah membuktikan dua hal yang tidak boleh dianggap benar begitu
saja. Pertama, kedua jalur menghasilkan hal yang sama persis untuk seluruh
kombinasi masukan, sehingga memindahkan perhitungan ke pipeline tidak pernah
diam-diam mengubah angka. Kedua, cap versi benar-benar mendeteksi tabel basi.
"""

import json

import pytest

import db

from angka_acuan import TOTAL_MENU


# Toleransi perbandingan angka pecahan, dinyatakan sebagai satu satuan pada
# tempat desimal terakhir yang benar-benar ditampilkan aplikasi.
#
# Alasannya begini. Jalur agregat membaca hasil penjumlahan yang dilakukan
# pipeline dengan pandas, sedangkan jalur cadangan menjumlahkan lewat SUM()
# milik SQLite. Sejak SQLite 3.45 fungsi SUM() memakai penjumlahan
# Kahan-Babuska yang lebih teliti, sehingga kedua algoritma dapat berbeda pada
# digit terakhir. Bila nilai sebenarnya kebetulan jatuh tepat di titik
# pembulatan, misalnya 6.772.151,05 ton, kedua jalur membulatkannya ke sisi yang
# berlawanan dan menghasilkan 6.772.151,1 berbanding 6.772.151,0.
#
# Selisih sebesar 0,1 ton pada angka jutaan ton tidak berarti apa pun, dan tidak
# mungkin dihilangkan sebab kedua algoritma memang berbeda. Karena itu yang
# diuji adalah kesamaan sampai ketelitian yang ditampilkan, bukan kesamaan pola
# bit. Toleransinya tetap ketat: cacat perhitungan yang sesungguhnya akan
# menghasilkan selisih jauh lebih besar daripada satu satuan terakhir.
TOLERANSI = {
    "ton": 0.011,           # ditampilkan dua desimal
    "total_ton": 0.11,      # ditampilkan satu desimal
    "isl": 0.0011,          # ditampilkan tiga desimal
    "mean_isl": 0.0011,
}
TOLERANSI_BAKU = 1e-9


def _angka_sama(x, y, kunci=None):
    batas = TOLERANSI.get(kunci, TOLERANSI_BAKU)
    return abs(float(x) - float(y)) <= batas


def _sama(a, b, kunci=None):
    """Bandingkan dua keluaran: struktur dan urutan persis, angka bertoleransi.

    Segala yang bukan angka pecahan, termasuk nama, bilangan bulat, susunan
    kunci, dan urutan baris, tetap dibandingkan persis. Hanya angka pecahan yang
    diberi toleransi, dan besarannya mengikuti ketelitian yang ditampilkan.
    """
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is None and b is None
        return _angka_sama(a, b, kunci)
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(_sama(a[k], b[k], k) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_sama(x, y, kunci) for x, y in zip(a, b))
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _dua_jalur(fungsi, **kw):
    """Jalankan satu fungsi lewat tabel agregat, lalu lewat hitung ulang."""
    asli = db._agregat_siap
    try:
        db._agregat_siap = True
        lewat_agregat = fungsi(**kw)
        db._agregat_siap = False
        lewat_hitung = fungsi(**kw)
    finally:
        db._agregat_siap = asli
    return lewat_agregat, lewat_hitung


# ketersediaan tabel agregat
def test_tabel_agregat_ada_dan_segar():
    """Basis data yang dikirim ke aplikasi harus sudah membawa tabel agregat."""
    db._agregat_siap = None          # paksa periksa ulang
    assert db.agregat_siap() is True, (
        "Tabel agregat belum ada atau basi. Jalankan sel P10 pada "
        "Pipeline_Menu_Provinsi.ipynb sebelum menyalin basis data ke aplikasi."
    )


def test_seluruh_tabel_agregat_terisi():
    harus_ada = [
        "agg_produksi_peta", "agg_produksi_ringkasan", "agg_produksi_kelompok",
        "agg_produksi_komoditas", "agg_isl_ranking", "agg_provinsi_menu",
        "agg_provinsi_isl", "agg_ringkasan", "meta_agregat",
    ]
    with db._connect() as con:
        for t in harus_ada:
            n = con.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
            assert n > 0, f"{t} kosong"


def test_cap_versi_cocok_dengan_data():
    with db._connect() as con:
        tersimpan = con.execute(
            "SELECT nilai FROM meta_agregat WHERE kunci='versi_data'").fetchone()["nilai"]
        assert tersimpan == db._sidik_sumber(con)


def test_cap_versi_berubah_bila_data_berubah(tmp_path):
    """Sidik harus peka terhadap perubahan data, bukan sekadar hiasan."""
    import shutil, sqlite3, config
    salinan = tmp_path / "uji.db"
    shutil.copy2(config.DB_PATH, salinan)
    con = sqlite3.connect(str(salinan))
    con.row_factory = sqlite3.Row
    sebelum = db._sidik_sumber(con)
    con.execute("UPDATE produksi_pangan SET produksi_ton = produksi_ton + 1 "
                "WHERE rowid = (SELECT MIN(rowid) FROM produksi_pangan)")
    con.commit()
    sesudah = db._sidik_sumber(con)
    con.close()
    assert sebelum != sesudah


# kesetaraan kedua jalur
def test_produksi_peta_setara():
    kelompok, tahun = db.kelompok_produksi()
    for k in (None, *kelompok):
        for t in (None, *tahun):
            a, b = _dua_jalur(db.produksi_peta, kelompok=k, tahun=t)
            assert _sama(a, b), f"produksi_peta beda pada kelompok={k} tahun={t}"


def test_ringkasan_produksi_setara():
    _, tahun = db.kelompok_produksi()
    for p in [x["nama"] for x in db.daftar_provinsi()]:
        for t in (None, *tahun):
            a, b = _dua_jalur(db.ringkasan_produksi, provinsi=p, tahun=t)
            assert _sama(a, b), f"ringkasan_produksi beda pada {p} tahun={t}"


def test_komoditas_teratas_setara():
    _, tahun = db.kelompok_produksi()
    for p in [x["nama"] for x in db.daftar_provinsi()]:
        for t in (None, *tahun):
            a, b = _dua_jalur(db.komoditas_teratas, provinsi=p, tahun=t, batas=8)
            assert _sama(a, b), f"komoditas_teratas beda pada {p} tahun={t}"


def test_isl_ranking_menu_setara():
    for p in [x["nama"] for x in db.daftar_provinsi()]:
        for j in (None, "SD", "SMP", "SMA", "SMK"):
            a, b = _dua_jalur(db.isl_ranking_menu, provinsi=p, jenjang=j)
            assert _sama(a, b), f"isl_ranking_menu beda pada {p} jenjang={j}"


def test_province_detail_setara():
    for p in [x["nama"] for x in db.daftar_provinsi()]:
        a, b = _dua_jalur(db.province_detail, kode_prov=db.kode_dari_nama(p))
        assert _sama(a, b), f"province_detail beda pada {p}"


def test_total_menu_setara():
    a, b = _dua_jalur(db.total_menu)
    assert a == b == TOTAL_MENU


# urutan harus pasti
def test_urutan_pasti_walau_nilai_seri():
    """Nilai yang sama besar harus tetap keluar dengan urutan yang sama.

    Tanpa kunci pengurut kedua, SQLite bebas menentukan urutan di antara baris
    bernilai sama, sehingga tampilan dapat berubah antar pemuatan dan tangkapan
    layar pada naskah menjadi tidak dapat diulang.
    """
    for _ in range(5):
        assert (db.komoditas_teratas("D.K.I. Jakarta", tahun=2019, batas=8)
                == db.komoditas_teratas("D.K.I. Jakarta", tahun=2019, batas=8))
        assert (db.isl_ranking_menu("Aceh", "SD")
                == db.isl_ranking_menu("Aceh", "SD"))


# aplikasi tidak boleh menghitung pada jalur normal
def test_jalur_normal_membaca_tabel_jadi():
    """Pada keadaan normal, angka peta datang dari tabel agregat.

    Diuji dengan mengganti isi tabel agregat pada salinan basis data lalu
    memastikan angka yang keluar ikut berubah. Bila aplikasi diam-diam masih
    menghitung sendiri, angkanya tidak akan bergeser.
    """
    import shutil, sqlite3, config
    asal = config.DB_PATH
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        salinan = os.path.join(d, "uji.db")
        shutil.copy2(asal, salinan)
        con = sqlite3.connect(salinan)
        con.execute("UPDATE agg_produksi_peta SET total_ton = 12345.0 "
                    "WHERE kelompok='' AND tahun=0")
        con.commit(); con.close()
        try:
            config.DB_PATH = salinan
            db._bersihkan_cache()
            db._agregat_siap = True
            hasil = db.produksi_peta()
            assert all(p["total_ton"] == 12345.0 for p in hasil)
        finally:
            config.DB_PATH = asal
            db._agregat_siap = None
            db._bersihkan_cache()


# regresi: perbedaan versi SQLite antar mesin
def test_pembulatan_seluruhnya_di_python_bukan_di_sql():
    """ROUND() SQLite dan round() Python memakai aturan berbeda pada batas .5.

    SQLite membulatkan setengah menjauhi nol, sedangkan Python membulatkan ke
    genap terdekat. Bila satu jalur memakai ROUND() SQL dan jalur lain memakai
    round() Python, keduanya berbeda pada angka yang tepat jatuh di batas.
    Contohnya 4368,165 menjadi 4368,17 menurut SQLite tetapi 4368,16 menurut
    Python. Karena itu pembulatan angka produksi tidak boleh lagi dilakukan di
    dalam kueri.
    """
    sumber = open("db.py", encoding="utf-8").read()
    assert "ROUND(SUM(" not in sumber, (
        "Pembulatan kembali dilakukan di SQL. Pindahkan ke Python lewat _bulat() "
        "supaya aturannya satu dan hasilnya tidak bergantung versi SQLite."
    )


def test_aturan_pembulatan_sqlite_dan_python_memang_berbeda():
    """Menunjukkan sebab cacatnya, bukan sekadar menyatakan."""
    import sqlite3
    con = sqlite3.connect(":memory:")
    beda = [v for v in (4368.165, 2.675, 0.125)
            if con.execute("SELECT ROUND(?,2)", (v,)).fetchone()[0] != round(v, 2)]
    assert beda, "Bila keduanya sudah sama, uji di atas boleh ditinjau ulang."


def test_urutan_hasil_tidak_bergantung_jalur():
    """Urutan harus ditentukan nilai bulat, bukan nilai penuh.

    Dua provinsi bertonase nyaris sama dapat bertukar tempat antara jalur
    agregat dan jalur cadangan bila pengurutannya memakai nilai penuh.
    """
    a, b = _dua_jalur(db.produksi_peta)
    assert [x["kode_prov"] for x in a] == [x["kode_prov"] for x in b]

    a, b = _dua_jalur(db.komoditas_teratas, provinsi="Bali", batas=8)
    assert [x["komoditas"] for x in a] == [x["komoditas"] for x in b]

    a, b = _dua_jalur(db.isl_ranking_menu, provinsi="Bali")
    assert [x["menu_id"] for x in a] == [x["menu_id"] for x in b]


def test_toleransi_tetap_menolak_cacat_sungguhan():
    """Toleransi hanya boleh menyerap artefak pembulatan, bukan cacat hitung."""
    assert _sama({"ton": 4368.16}, {"ton": 4368.17})        # artefak, diterima
    assert _sama({"isl": 0.457}, {"isl": 0.458})            # artefak, diterima
    assert not _sama({"ton": 4368.16}, {"ton": 4368.26})    # sepuluh kali lebih besar
    assert not _sama({"isl": 0.457}, {"isl": 0.467})
    assert not _sama({"n_komoditas": 19}, {"n_komoditas": 20})
    assert not _sama({"provinsi": "Aceh"}, {"provinsi": "Bali"})
    assert not _sama([{"ton": 1.0}, {"ton": 2.0}], [{"ton": 2.0}, {"ton": 1.0}])
