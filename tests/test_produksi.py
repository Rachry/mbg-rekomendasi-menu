"""
test_produksi.py: pengujian lapisan produksi pangan.

Keputusan penelitian ini adalah menampilkan data lembaga resmi apa adanya.
Aplikasi tidak menilai kewajaran angka Badan Pusat Statistik, sebab
keabsahannya adalah tanggung jawab lembaga penerbitnya. Cacat yang benar-benar
ada, yaitu satuan biofarmaka dan satu baris rusak saat pengambilan data, sudah
diperbaiki di hulu pada pipeline memakai angka rujukan resmi.

Pengujian di bawah mengunci tiga sifat: tidak ada penandaan kewajaran di sisi
web, angka hasil koreksi cocok dengan tabel resmi BPS, dan tidak ada lagi nilai
yang mustahil secara fisik.
"""

import pytest

import db


def test_kelompok_dan_tahun_tersedia():
    kelompok, tahun = db.kelompok_produksi()
    assert "serealia_umbi" in kelompok
    assert 2024 in tahun and 2019 in tahun


def test_peta_hanya_provinsi_yang_ada_di_peta():
    data = db.produksi_peta()
    assert len(data) == 36
    assert all(p["kode_prov"] is not None for p in data)


def test_peta_terurut_menurun():
    ton = [p["total_ton"] for p in db.produksi_peta()]
    assert ton == sorted(ton, reverse=True)


def test_tidak_ada_penandaan_kewajaran():
    """Web tidak boleh menilai kewajaran angka lembaga resmi."""
    assert not hasattr(db, "AMBANG_PRODUKSI_WAJAR")
    assert not hasattr(db, "produksi_baris_ditandai")
    for p in db.produksi_peta():
        assert "n_ditandai" not in p
        assert "persen_ditandai" not in p


def test_kolom_penanda_sudah_hilang_dari_basis_data():
    with db._connect() as con:
        kolom = {r["name"] for r in
                 con.execute("PRAGMA table_info(produksi_pangan)").fetchall()}
    assert "nilai_meragukan" not in kolom


def test_kunyit_jawa_timur_cocok_dengan_bps():
    """Nilai harus persis sama dengan tabel resmi BPS, dalam ton.

    Sumber: BPS, Produksi Tanaman Biofarmaka Menurut Provinsi dan Jenis
    Tanaman, terbitan 2021 sampai 2025. Berkas sumber bersatuan kilogram,
    sehingga nilai BPS dibagi seribu.
    """
    bps_kg = {2021: 82_988_205, 2022: 102_772_963, 2023: 113_283_709,
              2024: 78_000_636, 2025: 57_394_293}
    with db._connect() as con:
        for tahun, kg in bps_kg.items():
            baris = con.execute(
                "SELECT produksi_ton FROM produksi_pangan "
                "WHERE komoditas='kunyit' AND provinsi_key='jawa timur' AND tahun=?",
                (tahun,),
            ).fetchone()
            assert baris is not None, f"kunyit jawa timur {tahun} hilang"
            assert abs(baris["produksi_ton"] - kg / 1000.0) < 0.001


def test_satuan_biofarmaka_sudah_ton():
    """Total nasional biofarmaka harus cocok dengan BPS setelah dibagi seribu."""
    acuan_ton = {("kunyit", 2021): 184_825.890, ("kunyit", 2022): 196_499.570,
                 ("kunyit", 2023): 205_656.083, ("kunyit", 2024): 177_582.524,
                 ("kunyit", 2025): 147_505.182,
                 ("jeruk_nipis", 2021): 33_510.985, ("jeruk_nipis", 2024): 60_147.370,
                 ("lidah_buaya", 2021): 15_679.981, ("lidah_buaya", 2024): 3_737.320,
                 ("jahe", 2021): 307_241.517, ("jahe", 2024): 190_257.467,
                 ("kapulaga", 2024): 127_926.732, ("kencur", 2024): 44_953.335,
                 ("laos_lengkuas", 2024): 76_976.206, ("temuireng", 2024): 4_543.166,
                 ("temulawak", 2023): 24_326.927, ("serai_hijau", 2024): 51_562.867}
    with db._connect() as con:
        for (kom, tahun), acuan in acuan_ton.items():
            total = con.execute(
                "SELECT SUM(produksi_ton) AS t FROM produksi_pangan "
                "WHERE komoditas=? AND tahun=?", (kom, tahun),
            ).fetchone()["t"]
            assert abs(total - acuan) / acuan < 0.0001, f"{kom} {tahun}: {total} vs {acuan}"


def test_biofarmaka_mencakup_2025():
    """Unduhan resmi BPS menambah tahun terbit 2025 untuk kelompok biofarmaka."""
    with db._connect() as con:
        n = con.execute(
            "SELECT COUNT(*) AS n FROM produksi_pangan "
            "WHERE kelompok='biofarmaka' AND tahun=2025").fetchone()["n"]
    assert n > 0


def test_jeruk_nipis_dan_lidah_buaya_masuk_biofarmaka():
    with db._connect() as con:
        for kom in ("jeruk_nipis", "lidah_buaya"):
            kel = {r["kelompok"] for r in con.execute(
                "SELECT DISTINCT kelompok FROM produksi_pangan WHERE komoditas=?",
                (kom,)).fetchall()}
            assert kel == {"biofarmaka"}, f"{kom} salah kelompok: {kel}"


def test_jeruk_lemon_tetap_buah():
    """Jeruk lemon tidak termuat pada tabel biofarmaka BPS, jadi satuannya ton."""
    with db._connect() as con:
        kel = {r["kelompok"] for r in con.execute(
            "SELECT DISTINCT kelompok FROM produksi_pangan WHERE komoditas='jeruk_lemon'"
        ).fetchall()}
    assert kel == {"buah"}


def test_tidak_ada_nilai_mustahil():
    """Setelah koreksi, nilai terbesar harus setara padi Jawa Timur, bukan triliunan."""
    with db._connect() as con:
        maks = con.execute(
            "SELECT MAX(produksi_ton) AS m FROM produksi_pangan").fetchone()["m"]
    assert maks < 20_000_000, f"masih ada nilai mustahil: {maks:,.0f} ton"


def test_baris_total_nasional_sudah_dibuang():
    """Baris berlabel Papua Pegunungan pada enam berkas buah adalah total nasional."""
    with db._connect() as con:
        for kom in ("nenas", "alpukat", "manggis", "sawo",
                    "duku_langsat_kokosan", "jeruk_lemon"):
            n = con.execute(
                "SELECT COUNT(*) AS n FROM produksi_pangan "
                "WHERE komoditas=? AND provinsi_key='papua pegunungan'", (kom,),
            ).fetchone()["n"]
            assert n == 0, f"{kom} masih memuat baris total nasional"


def test_nenas_terbesar_adalah_lampung():
    """Lampung sentra nanas nasional menurut BPS, bukan provinsi pegunungan Papua."""
    with db._connect() as con:
        teratas = con.execute(
            "SELECT provinsi, produksi_ton FROM produksi_pangan "
            "WHERE komoditas='nenas' AND tahun=2023 ORDER BY produksi_ton DESC LIMIT 1"
        ).fetchone()
    assert teratas["provinsi"] == "Lampung"
    assert abs(teratas["produksi_ton"] - 722_847) < 1


def test_komoditas_teratas():
    hasil = db.komoditas_teratas("Jawa Timur", tahun=2024, batas=5)
    assert len(hasil) == 5
    ton = [h["ton"] for h in hasil]
    assert ton == sorted(ton, reverse=True)


def test_komoditas_teratas_provinsi_salah():
    assert db.komoditas_teratas("Atlantis") is None


# --- endpoint ---------------------------------------------------------------
def test_api_produksi_peta(klien):
    d = klien.get("/api/produksi-peta?tahun=2024").get_json()
    assert d["total_provinsi"] == 36
    assert "baris_ditandai" not in d
    assert "provinsi_ditandai" not in d
    assert "ambang_wajar_ton" not in d
    assert "Badan Pusat Statistik" in d["sumber"]


def test_api_produksi_ditandai_sudah_dihapus(klien):
    assert klien.get("/api/produksi-ditandai").status_code == 404


@pytest.mark.parametrize("kelompok", [
    "serealia_umbi", "buah", "sayuran", "peternakan", "perikanan",
])
def test_api_filter_kelompok(klien, kelompok):
    d = klien.get(f"/api/produksi-peta?kelompok={kelompok}").get_json()
    assert d["kelompok"] == kelompok
    assert d["total_provinsi"] > 0


def test_api_kelompok_salah_400(klien):
    assert klien.get("/api/produksi-peta?kelompok=ngawur").status_code == 400


def test_api_tahun_di_luar_rentang_400(klien):
    assert klien.get("/api/produksi-peta?tahun=1990").status_code == 400
    assert klien.get("/api/produksi-peta?tahun=xx").status_code == 400


def test_api_komoditas_teratas(klien):
    d = klien.get("/api/produksi/Aceh/teratas").get_json()
    assert d["provinsi"] == "Aceh"
    assert d["data"]


# --- keterbatasan pewarisan nilai -------------------------------------------
def test_profil_pangan_menandai_warisan(klien):
    data = klien.get("/api/profil-pangan").get_json()
    warisan = [p for p in data if p["warisan"]]
    assert len(warisan) == 4
    assert {p["provinsi"] for p in warisan} == {
        "Papua Selatan", "Papua Tengah", "Papua Pegunungan", "Papua Barat Daya",
    }
    for p in warisan:
        assert p["warisan_dari"] in ("Papua", "Papua Barat")
        assert p["catatan"]


def test_profil_pangan_terukur_tidak_ditandai(klien):
    data = klien.get("/api/profil-pangan?provinsi=Aceh").get_json()
    assert data[0]["warisan"] is False
    assert data[0]["warisan_dari"] is None


def test_nilai_warisan_identik_dengan_induk():
    """Pewarisan harus benar-benar menyalin, bukan mengira-ngira."""
    semua = {p["provinsi"]: p for p in db.profil_pangan_provinsi()}
    kelompok = [k for k in semua["Papua"] if k not in
                ("provinsi", "warisan", "warisan_dari", "catatan")]
    for anak, induk in [("Papua Selatan", "Papua"), ("Papua Barat Daya", "Papua Barat")]:
        for k in kelompok:
            assert semua[anak][k] == semua[induk][k]


# --- ringkasan produksi satu provinsi ---------------------------------------
def test_ringkasan_produksi_provinsi():
    r = db.ringkasan_produksi("Jawa Timur")
    assert r["provinsi"] == "Jawa Timur"
    assert r["n_komoditas"] > 0
    assert r["n_kelompok"] > 0
    assert r["tahun_awal"] <= r["tahun_akhir"]
    # Rincian per kelompok terurut menurun dan menjumlah ke total.
    ton = [k["ton"] for k in r["kelompok"]]
    assert ton == sorted(ton, reverse=True)
    assert abs(sum(ton) - r["total_ton"]) < 1.0


def test_ringkasan_produksi_per_tahun():
    semua = db.ringkasan_produksi("Jawa Timur")
    satu = db.ringkasan_produksi("Jawa Timur", tahun=2024)
    assert satu["total_ton"] < semua["total_ton"]
    assert satu["tahun_awal"] == satu["tahun_akhir"] == 2024


def test_ringkasan_produksi_tanpa_penandaan():
    assert "n_ditandai" not in db.ringkasan_produksi("Jawa Timur")


def test_ringkasan_produksi_provinsi_salah():
    assert db.ringkasan_produksi("Atlantis") is None


def test_api_ringkasan_produksi(klien):
    d = klien.get("/api/produksi/Aceh/ringkasan").get_json()
    assert d["provinsi"] == "Aceh"
    assert d["kelompok"]


def test_api_ringkasan_produksi_tahun_salah(klien):
    assert klien.get("/api/produksi/Aceh/ringkasan?tahun=xx").status_code == 400


def test_api_ringkasan_produksi_provinsi_salah(klien):
    assert klien.get("/api/produksi/Atlantis/ringkasan").status_code == 404


# --- halaman produsen sebagai tujuan klik peta ------------------------------
def test_halaman_produsen_menerima_provinsi(klien):
    r = klien.get("/produsen?provinsi=Papua Pegunungan")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # Provinsi yang diminta harus terpilih di dropdown.
    assert 'value="Papua Pegunungan" selected' in html


def test_halaman_produsen_provinsi_salah_404(klien):
    assert klien.get("/produsen?provinsi=Atlantis").status_code == 404


def test_halaman_produsen_tanpa_provinsi(klien):
    assert klien.get("/produsen").status_code == 200


def test_halaman_produsen_menampilkan_komoditas_bukan_menu(klien):
    """Klik pada lapisan produksi harus berujung ke komoditas, bukan menu."""
    html = klien.get("/produsen").get_data(as_text=True)
    assert "Komoditas diproduksi" in html
    assert "menu_id" not in html


def test_peta_mengarahkan_klik_produksi_ke_produsen(klien):
    html = klien.get("/").get_data(as_text=True)
    assert "produksiUrlBase" in html


def test_penyaring_menu_dapat_disembunyikan_di_lapisan_produksi(klien):
    """Jenjang dan tingkat tidak berlaku bagi data produksi."""
    html = klien.get("/").get_data(as_text=True)
    assert 'id="grup-menu"' in html      # dibungkus agar bisa disembunyikan
    import pathlib
    js = (pathlib.Path(__file__).resolve().parent.parent
          / "static" / "js" / "map.js").read_text(encoding="utf-8")
    assert "grupMenu.hidden = produksi" in js
