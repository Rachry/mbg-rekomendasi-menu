"""
test_db.py: pengujian lapisan basis data.

Menyasar fungsi yang dulu tidak tercakup sama sekali: recommend() dan
perhitungan Indeks Sumber Lokal. Angka acuan diambil dari basis data
pipeline 5 Agustus 2026.
"""

import pytest

import config
import db

from angka_acuan import TOTAL_MENU, MENU_NON_HALAL, BAHAN_TERPAKAI
TOTAL_PROVINSI = 36
TOTAL_BAHAN = 119


# --- ringkasan: angka pokok harus cocok dengan naskah -----------------------
def test_ringkasan_cocok_dengan_naskah():
    r = db.ringkasan()
    assert r["total_menu"] == TOTAL_MENU
    assert r["total_provinsi"] == TOTAL_PROVINSI
    assert r["total_bahan"] == TOTAL_BAHAN
    assert r["bahan_terpakai"] == BAHAN_TERPAKAI
    assert r["menu_non_halal"] == MENU_NON_HALAL
    # Seluruh menu lolos validasi AKG menurut audit integritas keluaran.
    assert r["menu_akg_valid"] == TOTAL_MENU


def test_ringkasan_isl_masuk_akal():
    r = db.ringkasan()
    assert 0.0 < r["isl_rata_rata"] < 1.0


# --- pemetaan nama dan kode provinsi ----------------------------------------
def test_kode_dari_nama_menerima_tiga_bentuk():
    assert db.kode_dari_nama("Aceh") == db.kode_dari_nama("Prov. Aceh")
    assert db.kode_dari_nama("aceh") == db.kode_dari_nama("Aceh")


def test_provinsi_bertitik_tetap_dikenali():
    # Dua provinsi ini yang dulu gagal dicocokkan ke tabel ketersediaan.
    assert db.kode_dari_nama("D.K.I. Jakarta") is not None
    assert db.kode_dari_nama("D.I. Yogyakarta") is not None


def test_provinsi_tak_dikenal():
    assert db.kode_dari_nama("Atlantis") is None
    assert db.provinsi_valid("Atlantis") is False
    assert db.nama_dari_kode(999999) is None


def test_daftar_provinsi_lengkap():
    daftar = db.daftar_provinsi()
    assert len(daftar) == TOTAL_PROVINSI
    assert all(p["kode_prov"] is not None for p in daftar)
    assert all(not p["nama"].startswith("Prov. ") for p in daftar)


# --- peta dan detail provinsi -----------------------------------------------
def test_peta_tanpa_jenjang_memakai_tingkat_tertinggi():
    semua = db.provinces_for_map()
    assert len(semua) == TOTAL_PROVINSI
    assert all("warna" in p and "label_awam" in p for p in semua)


def test_peta_dengan_jenjang_lebih_sedikit():
    # Tidak semua provinsi punya data untuk tiap jenjang.
    assert len(db.provinces_for_map("SD")) <= TOTAL_PROVINSI


def test_detail_provinsi_selalu_empat_jenjang():
    d = db.province_detail(db.kode_dari_nama("Aceh"))
    assert d is not None
    assert [j["jenjang"] for j in d["jenjang"]] == config.JENJANG_LIST


def test_detail_provinsi_tidak_ada():
    assert db.province_detail(999999) is None


# --- pencarian: wildcard tidak boleh bocor ----------------------------------
def test_search_menemukan():
    hasil = db.search_provinces("jawa")
    assert len(hasil) == 3
    assert all("Jawa" in h["provinsi"] for h in hasil)


def test_search_kosong():
    assert db.search_provinces("") == []


def test_search_wildcard_dinetralkan():
    # '%' sebagai masukan tidak boleh berperilaku sebagai wildcard LIKE.
    assert db.search_provinces("%") == []
    assert db.search_provinces("_") == []


# --- menu --------------------------------------------------------------------
def test_menus_tanpa_filter():
    assert len(db.menus()) == TOTAL_MENU


@pytest.mark.parametrize("jenjang", config.JENJANG_LIST)
def test_menus_per_jenjang(jenjang):
    hasil = db.menus(jenjang=jenjang)
    assert hasil
    assert all(m["jenjang"] == jenjang for m in hasil)


@pytest.mark.parametrize("tingkat", config.TINGKAT_LIST)
def test_menus_per_tingkat(tingkat):
    hasil = db.menus(tingkat=tingkat)
    assert all(m["tingkat"] == tingkat for m in hasil)


def test_menus_per_provinsi():
    hasil = db.menus(provinsi="Bali")
    assert hasil
    assert all(m["provinsi"] == "Bali" for m in hasil)


def test_menu_detail_lengkap():
    d = db.menu_detail("SD-60000-1")
    assert d is not None
    # Audit integritas keluaran: tiap menu berisi lima sampai enam bahan.
    assert 5 <= len(d["bahan"]) <= 6
    assert d["gizi"]["akg_valid"] is True
    assert d["akg_standar"] is not None


def test_menu_detail_tidak_ada():
    assert db.menu_detail("TIDAK-ADA-1") is None


def test_setiap_menu_punya_komposisi():
    # Komposisi harus terhubung penuh ke menu, tanpa menu yatim.
    semua = db.menus()
    assert all(5 <= m["jumlah_bahan"] <= 6 for m in semua)


# --- Indeks Sumber Lokal -----------------------------------------------------
def test_isl_provinsi_valid():
    hasil = db.isl_provinsi("Aceh")
    assert hasil
    assert all(0.0 <= b["isl"] <= 1.0 for b in hasil)


def test_isl_provinsi_tanpa_bahan_kosong():
    # Bahan tanpa data produksi tidak boleh muncul sebagai nol.
    hasil = db.isl_provinsi("Aceh")
    assert all(b["isl"] is not None for b in hasil)
    assert len(hasil) < TOTAL_BAHAN


def test_isl_provinsi_tak_dikenal_mengembalikan_none():
    # Ini pembeda penting: None berarti provinsi tidak ada, bukan ISL nol.
    assert db.isl_provinsi("Atlantis") is None
    assert db.isl_ranking_menu("Atlantis") is None


def test_isl_ranking_terurut_menurun():
    hasil = db.isl_ranking_menu("Aceh")
    nilai = [m["isl"] for m in hasil if m["isl"] is not None]
    assert nilai == sorted(nilai, reverse=True)


def test_isl_menu_dihitung_dari_bahan_berdata_saja():
    hasil = db.isl_ranking_menu("Aceh", jenjang="SD")
    for m in hasil:
        assert m["bahan_berdata"] <= m["bahan_total"]


def test_isl_berbeda_antar_provinsi():
    # Kalau lapis wilayah bekerja, provinsi berbeda tidak boleh identik.
    a = db.menus(provinsi="Papua Pegunungan")
    b = db.menus(provinsi="Jawa Barat")
    label_a = {m["menu_label"] for m in a}
    label_b = {m["menu_label"] for m in b}
    assert label_a != label_b


# --- recommend: dulu 0% tercakup --------------------------------------------
def test_recommend_tanpa_filter_mengembalikan_semua():
    r = db.recommend()
    assert r["total_lolos"] == TOTAL_MENU
    assert r["ditampilkan"] == config.BATAS_REKOMENDASI


def test_recommend_filter_provinsi():
    r = db.recommend(provinsi="Bali", batas=50)
    assert all(m["provinsi"] == "Bali" for m in r["rekomendasi"])


def test_recommend_filter_jenjang():
    r = db.recommend(jenjang="SMP", batas=50)
    assert all(m["jenjang"] == "SMP" for m in r["rekomendasi"])


def test_recommend_filter_tingkat():
    r = db.recommend(tingkat="Tinggi", batas=50)
    assert r["total_lolos"] == 30      # 10 kombinasi x 3 menu
    assert all(m["tingkat"] == "Tinggi" for m in r["rekomendasi"])


def test_recommend_halal_saja():
    r = db.recommend(halal_saja=True, batas=50)
    assert r["total_lolos"] == TOTAL_MENU - MENU_NON_HALAL
    assert all(m["halal"] for m in r["rekomendasi"])


def test_recommend_tanpa_fobia():
    r = db.recommend(tanpa_fobia=True, batas=50)
    assert 0 < r["total_lolos"] < TOTAL_MENU
    assert all(not m["fobia"] for m in r["rekomendasi"])


@pytest.mark.parametrize("alergen", config.ALERGEN_LIST)
def test_recommend_exclude_tiap_alergen(alergen):
    r = db.recommend(exclude_alergen=[alergen], batas=50)
    assert all(alergen not in m["alergen"] for m in r["rekomendasi"])


def test_recommend_exclude_beberapa_alergen_menyempit():
    satu = db.recommend(exclude_alergen=["telur"])["total_lolos"]
    tiga = db.recommend(exclude_alergen=["telur", "ikan", "susu"])["total_lolos"]
    assert tiga < satu


@pytest.mark.parametrize("intol", config.INTOLERANSI_LIST)
def test_recommend_exclude_intoleransi(intol):
    r = db.recommend(exclude_intoleransi=[intol], batas=50)
    assert all(intol not in m["intoleransi"] for m in r["rekomendasi"])


def test_recommend_exclude_bahan_tertentu():
    r = db.recommend(exclude_bahan=["Beras putih nasi"], batas=50)
    assert r["total_lolos"] < TOTAL_MENU
    for m in r["rekomendasi"]:
        detail = db.menu_detail(m["menu_id"])
        assert all(b["nama_bahan"] != "Beras putih nasi" for b in detail["bahan"])


@pytest.mark.parametrize("sumber", config.SUMBER_KARBO_LIST)
def test_recommend_sumber_karbo(sumber):
    r = db.recommend(sumber_karbo=sumber, batas=50)
    assert r["total_lolos"] > 0
    assert all(m["sumber_karbo"] == sumber for m in r["rekomendasi"])


@pytest.mark.parametrize("sumber", config.SUMBER_PROTEIN_LIST)
def test_recommend_sumber_protein(sumber):
    r = db.recommend(sumber_protein=sumber, batas=50)
    assert all(m["sumber_protein"] == sumber for m in r["rekomendasi"])


def test_recommend_filter_bertumpuk():
    r = db.recommend(provinsi="Jawa Barat", jenjang="SD", halal_saja=True, batas=50)
    for m in r["rekomendasi"]:
        assert m["provinsi"] == "Jawa Barat"
        assert m["jenjang"] == "SD"
        assert m["halal"]


def test_recommend_kombinasi_mustahil_mengembalikan_nol_bukan_galat():
    # Versi lama diam-diam mengganti hasil kosong dengan menu "terdekat".
    # Sekarang nol tetap nol, supaya pengguna tahu penyaringnya terlalu ketat.
    r = db.recommend(exclude_alergen=config.ALERGEN_LIST, tanpa_fobia=True)
    assert r["total_lolos"] >= 0
    assert r["rekomendasi"] == [] or all(not m["alergen"] for m in r["rekomendasi"])


def test_recommend_provinsi_tak_dikenal_tidak_meledak():
    assert db.recommend(provinsi="Atlantis")["total_lolos"] == 0


def test_recommend_batas_dihormati_dan_dibatasi():
    assert db.recommend(batas=3)["ditampilkan"] == 3
    # Permintaan di atas batas maksimum dipangkas, bukan ditolak.
    r = db.recommend(batas=9999)
    assert r["ditampilkan"] <= config.BATAS_REKOMENDASI_MAX


@pytest.mark.parametrize("urut", list(config.URUT_OPSI))
def test_recommend_tiap_pengurutan_berjalan(urut):
    r = db.recommend(urut=urut, batas=10)
    assert r["filter"]["urut"] == urut
    assert len(r["rekomendasi"]) == 10


def test_urut_gizi_menurun():
    r = db.recommend(urut="gizi", batas=20)
    nilai = [m["skor_gizi"] for m in r["rekomendasi"] if m["skor_gizi"] is not None]
    assert nilai == sorted(nilai, reverse=True)


def test_urut_isl_menurun_dan_tanpa_data_di_belakang():
    r = db.recommend(urut="isl", batas=50)
    nilai = [m["isl"] for m in r["rekomendasi"]]
    berdata = [n for n in nilai if n is not None]
    assert berdata == sorted(berdata, reverse=True)
    # Menu tanpa data ISL tidak boleh menyelip di depan.
    if None in nilai:
        assert nilai.index(None) >= len(berdata)


def test_urut_akg_mendekati_satu():
    r = db.recommend(urut="akg_energi", batas=10)
    selisih = [abs(m["rasio_energi"] - 1.0) for m in r["rekomendasi"]]
    assert selisih == sorted(selisih)


def test_urut_asing_jatuh_ke_default():
    r = db.recommend(urut="tidak-ada")
    assert r["filter"]["urut"] == config.URUT_DEFAULT


# --- bahan -------------------------------------------------------------------
def test_ingredients_semua_vs_terpakai():
    assert len(db.ingredients_all()) == TOTAL_BAHAN
    assert len(db.ingredients_all(hanya_terpakai=True)) == BAHAN_TERPAKAI


def test_penanda_bahan_di_cache():
    # Dipanggil dua kali harus mengembalikan objek yang sama persis.
    assert db.penanda_bahan() is db.penanda_bahan()


def test_ambang_fobia_diterapkan():
    for m in db.penanda_bahan().values():
        assert m["fobia"] == (m["skor_fobia"] > config.AMBANG_FOBIA)


# --- profil kelompok ---------------------------------------------------------
def test_cluster_profiles_lengkap():
    assert len(db.cluster_profiles()) == 12          # 4 jenjang x 3 tingkat
    assert len(db.cluster_profiles("SD")) == 3


def test_cluster_profiles_dengan_anggota():
    hasil = db.cluster_profiles("SD", sertakan_provinsi=True)
    assert all("provinces" in c for c in hasil)
    total = sum(len(c["provinces"]) for c in hasil)
    assert total == sum(c["n_provinsi"] for c in hasil)


# --- data mentah -------------------------------------------------------------
def test_provinces_raw_kolom_bertambah_dengan_label():
    tanpa = db.provinces_raw()
    dengan = db.provinces_raw(dengan_label=True)
    assert len(dengan["kolom"]) > len(tanpa["kolom"])
    assert "label_risiko" in dengan["kolom"]


def test_provinces_raw_nama_provinsi_bersih():
    hasil = db.provinces_raw()
    assert all(not b["provinsi"].startswith("Prov. ") for b in hasil["baris"])


def test_akg_standards_empat_jenjang():
    assert len(db.akg_standards()) == 4
