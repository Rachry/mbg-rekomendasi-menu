"""
test_data_produksi.py: pengujian tab Produksi Pangan pada halaman data mentah.

Berisi dua golongan pengujian yang sengaja dipisah dalam berkas yang sama
supaya fitur barunya dapat dibaca utuh:

WHITEBOX menguji `db.produksi_mentah()` dan `db.opsi_produksi()` dengan melihat
isi kodenya, menyasar cabang penyaring, pembatasan nilai, dan keadaan batas
pemuatan bertahap.

BLACKBOX menguji lewat alamat data dan halaman tanpa melihat kodenya, memakai
partisi ekuivalensi dan analisis nilai batas atas masukan yang sah, tidak sah,
dan kosong.
"""

import pytest

import angka_acuan as A
import db


# WHITEBOX: lapisan basis data

def test_wb_produksi_tanpa_penyaring_mengembalikan_seluruh_baris():
    """Cabang tanpa klausa WHERE, total harus sama dengan isi tabel."""
    h = db.produksi_mentah()
    assert h["total"] == A.TOTAL_BARIS_PRODUKSI
    assert h["ditampilkan"] == db.PRODUKSI_BATAS_BAKU
    assert h["ada_lagi"] is True


def test_wb_tiap_penyaring_mempersempit_hasil():
    """Tiap cabang penyaring diuji sendiri-sendiri, lalu digabung."""
    semua = db.produksi_mentah()["total"]
    per_prov = db.produksi_mentah(provinsi="Aceh")["total"]
    per_kel = db.produksi_mentah(kelompok="buah")["total"]
    per_kom = db.produksi_mentah(komoditas="padi")["total"]
    per_th = db.produksi_mentah(tahun=2023)["total"]
    for n in (per_prov, per_kel, per_kom, per_th):
        assert 0 < n < semua

    gabungan = db.produksi_mentah(provinsi="Aceh", komoditas="padi")["total"]
    assert gabungan <= min(per_prov, per_kom)


def test_wb_penyaring_provinsi_memakai_kunci_bukan_ejaan():
    """Kolom provinsi memuat 47 ragam ejaan untuk 38 provinsi.

    Menyaring lewat ejaan mana pun harus memberi jumlah yang sama, sebab
    penyaringan dijalankan pada provinsi_key yang sudah diseragamkan.
    """
    ejaan = ["DI Yogyakarta", "Di Yogyakarta", "D.I. Yogyakarta", "di yogyakarta"]
    jumlah = {db.produksi_mentah(provinsi=e)["total"] for e in ejaan}
    assert len(jumlah) == 1, f"ejaan berbeda memberi jumlah berbeda: {jumlah}"
    assert jumlah.pop() > 0


def test_wb_batas_dipangkas_ke_rentang_yang_sah():
    """Analisis nilai batas pada parameter batas."""
    assert db.produksi_mentah(batas=1)["batas"] == 1
    assert db.produksi_mentah(batas=0)["batas"] == 1          # di bawah batas bawah
    assert db.produksi_mentah(batas=-10)["batas"] == 1        # negatif
    assert db.produksi_mentah(batas=db.PRODUKSI_BATAS_MAX)["batas"] == db.PRODUKSI_BATAS_MAX
    assert db.produksi_mentah(batas=999999)["batas"] == db.PRODUKSI_BATAS_MAX


def test_wb_offset_negatif_dianggap_nol():
    assert db.produksi_mentah(offset=-5)["offset"] == 0


def test_wb_pemuatan_bertahap_tidak_tumpang_tindih():
    """Dua halaman berurutan tidak boleh memuat baris yang sama."""
    h1 = db.produksi_mentah(batas=50, offset=0)
    h2 = db.produksi_mentah(batas=50, offset=50)
    kunci = lambda b: (b["provinsi"], b["komoditas"], b["tahun"])
    assert not (set(map(kunci, h1["baris"])) & set(map(kunci, h2["baris"])))


def test_wb_ada_lagi_padam_pada_halaman_terakhir():
    """Keadaan batas: offset tepat sebelum dan tepat pada akhir data."""
    total = db.produksi_mentah()["total"]
    sebelum = db.produksi_mentah(batas=10, offset=total - 10)
    assert sebelum["ada_lagi"] is False
    assert sebelum["ditampilkan"] == 10

    habis = db.produksi_mentah(batas=10, offset=total)
    assert habis["ditampilkan"] == 0
    assert habis["ada_lagi"] is False


def test_wb_penyaring_tanpa_hasil_mengembalikan_kosong_bukan_galat():
    h = db.produksi_mentah(provinsi="Aceh", komoditas="sagu", tahun=1900)
    assert h["total"] == 0
    assert h["baris"] == []
    assert h["ada_lagi"] is False


def test_wb_opsi_produksi_seragam_38_provinsi():
    """Pilihan penyaring tidak boleh memuat provinsi ganda karena beda ejaan."""
    o = db.opsi_produksi()
    assert len(o["provinsi"]) == 38
    kunci = [p["kunci"] for p in o["provinsi"]]
    assert len(set(kunci)) == len(kunci)
    assert all(p["nama"] and p["n_baris"] > 0 for p in o["provinsi"])


def test_wb_opsi_produksi_seluruhnya_menghasilkan_baris():
    """Pilihan yang ditawarkan harus benar-benar ada datanya.

    Menawarkan pilihan yang menghasilkan tabel kosong membuat pengguna
    menyangka aplikasinya rusak.
    """
    o = db.opsi_produksi()
    for kel in o["kelompok"]:
        assert db.produksi_mentah(kelompok=kel)["total"] > 0, kel
    for th in o["tahun"]:
        assert db.produksi_mentah(tahun=th)["total"] > 0, th


def test_wb_kolom_yang_dikembalikan_tetap():
    h = db.produksi_mentah(batas=1)
    assert set(h["baris"][0]) == {
        "provinsi", "komoditas", "kelompok", "tahun", "produksi_ton", "satuan"
    }


def test_wb_nilai_nol_dipertahankan_bukan_dibuang():
    """Tercatat nol berbeda dari tidak tercatat, keduanya harus dibedakan.

    Sagu Jawa Barat tercatat nol ton, dan baris itu wajib tetap ada. Kalau
    dibuang, pembaca tidak dapat membedakannya dari komoditas yang memang
    tidak pernah didata di provinsi tersebut.
    """
    h = db.produksi_mentah(provinsi="Jawa Barat", komoditas="sagu")
    assert h["total"] > 0
    assert any(b["produksi_ton"] == 0 for b in h["baris"])


# WHITEBOX: angka ringkasan yang dipakai halaman

def test_wb_ringkasan_memuat_kunci_baru():
    r = db.ringkasan()
    for kunci in ("baris_imputed", "total_grid", "baris_dibuang",
                  "isl_cakupan_persen", "produksi_tahun_awal",
                  "produksi_tahun_akhir"):
        assert kunci in r, kunci


def test_wb_ringkasan_grid_konsisten():
    """total_grid harus sama dengan jumlah jenjang kali jumlah provinsi."""
    import config
    r = db.ringkasan()
    assert r["total_grid"] == len(config.JENJANG_LIST) * config.TOTAL_PROVINSI_GRID
    assert r["baris_dibuang"] == r["total_grid"] - r["total_baris_provinsi"]


def test_wb_ringkasan_cakupan_isl_masuk_akal():
    r = db.ringkasan()
    assert 0 <= r["isl_cakupan_persen"] <= 100


def test_wb_ringkasan_tahun_produksi_berurutan():
    r = db.ringkasan()
    assert r["produksi_tahun_awal"] <= r["produksi_tahun_akhir"]


def test_wb_baris_imputed_dihitung_bukan_ditulis_tangan():
    """Angka imputasi harus berasal dari basis data.

    Halaman Tentang pernah menyatakan sebagian data hasil estimasi padahal
    tidak ada satu pun. Uji ini mengunci agar angkanya selalu dihitung.
    """
    import sqlite3
    r = db.ringkasan()
    with db._connect() as con:
        nyata = con.execute(
            "SELECT COUNT(*) n FROM provinces WHERE is_imputed = 1"
        ).fetchone()["n"]
    assert r["baris_imputed"] == nyata


# BLACKBOX: alamat data

def test_bb_alamat_produksi_mentah_membalas_bentuk_yang_dijanjikan(klien):
    d = klien.get("/api/produksi-mentah").get_json()
    for kunci in ("total", "batas", "offset", "ditampilkan", "ada_lagi",
                  "baris", "penyaring", "sumber", "catatan"):
        assert kunci in d, kunci
    assert d["total"] == A.TOTAL_BARIS_PRODUKSI


def test_bb_penyaring_dipantulkan_kembali(klien):
    d = klien.get("/api/produksi-mentah?provinsi=Aceh&kelompok=buah").get_json()
    assert d["penyaring"]["provinsi"] == "Aceh"
    assert d["penyaring"]["kelompok"] == "buah"
    assert d["penyaring"]["komoditas"] is None


@pytest.mark.parametrize("kueri", [
    "provinsi=Wakanda",
    "kelompok=bukan-kelompok",
    "komoditas=bukan-komoditas",
    "tahun=1900",
    "tahun=bukan-angka",
    "batas=abc",
    "batas=-1",
    "offset=-1",
])
def test_bb_masukan_tidak_sah_menghasilkan_400(klien, kueri):
    """Partisi ekuivalensi golongan tidak sah.

    Membalas 200 berisi data kosong akan membuat kekeliruan pengetikan
    tampak seperti jawaban yang sah.
    """
    r = klien.get("/api/produksi-mentah?" + kueri)
    assert r.status_code == 400, kueri
    assert "error" in r.get_json()


@pytest.mark.parametrize("kueri", ["", "provinsi=", "kelompok=", "tahun=", "batas="])
def test_bb_parameter_kosong_dianggap_tidak_menyaring(klien, kueri):
    """Partisi ekuivalensi golongan kosong, harus sama dengan tanpa penyaring."""
    d = klien.get("/api/produksi-mentah?" + kueri).get_json()
    assert d["total"] == A.TOTAL_BARIS_PRODUKSI


def test_bb_alamat_opsi_produksi(klien):
    d = klien.get("/api/opsi-produksi").get_json()
    assert len(d["provinsi"]) == 38
    assert len(d["tahun"]) >= 1
    assert all({"kunci", "nama", "n_baris"} <= set(p) for p in d["provinsi"])


def test_bb_pilihan_dari_opsi_selalu_dapat_dipakai_menyaring(klien):
    """Nilai yang ditawarkan alamat opsi harus diterima alamat tabel."""
    o = klien.get("/api/opsi-produksi").get_json()
    for p in o["provinsi"][:5]:
        r = klien.get("/api/produksi-mentah?provinsi=" + p["kunci"])
        assert r.status_code == 200, p["kunci"]
        assert r.get_json()["total"] == p["n_baris"]


# BLACKBOX: halaman

def test_bb_halaman_data_memuat_dua_tab(klien):
    h = klien.get("/data").get_data(as_text=True)
    assert 'data-tab="kesehatan"' in h
    assert 'data-tab="produksi"' in h
    assert 'id="panel-produksi"' in h


def test_bb_halaman_data_memuat_skrip_tab_produksi(klien):
    h = klien.get("/data").get_data(as_text=True)
    assert "data_produksi.js" in h
    assert "apiProduksiMentah" in h
    assert "apiOpsiProduksi" in h
    assert klien.get("/static/js/data_produksi.js").status_code == 200


def test_bb_kepala_tab_menampilkan_jumlah_baris(klien):
    """Besarnya data terlihat sebelum tabelnya dibuka."""
    h = klien.get("/data").get_data(as_text=True)
    assert f"{A.TOTAL_PROVINCES} baris" in h
    assert "15.743 baris" in h


def test_bb_halaman_data_menyebut_sumber_kedua_data(klien):
    h = klien.get("/data").get_data(as_text=True)
    assert "API Kemendikdasmen" in h
    assert "Badan Pusat Statistik" in h
    assert "bukan angka" in h.lower() or "bukan konsumsi" in h.lower()


def test_bb_penyaring_tab_produksi_tersedia(klien):
    h = klien.get("/data").get_data(as_text=True)
    for id_ in ("p-provinsi", "p-kelompok", "p-komoditas", "p-tahun",
                "p-lagi", "p-csv", "p-reset"):
        assert f'id="{id_}"' in h, id_
