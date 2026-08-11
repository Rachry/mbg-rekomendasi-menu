"""
test_navigasi.py: remah navigasi dan penanda bahan lokal.

Dua masalah nyata yang dikunci di sini.

Pertama, tautan kembali dulu dipatok ke satu tujuan. Halaman menu selalu
menawarkan "Kembali ke galeri menu", sehingga pengunjung yang tiba lewat
Kelompok Daerah lalu halaman provinsi justru terlempar ke galeri. Halaman
produksi bahkan tidak punya jalan kembali sama sekali.

Kedua, nilai Indeks Sumber Lokal ditampilkan sebagai persentase mentah tanpa
penanda, sehingga pembaca harus menafsirkan sendiri angka seperti 0,102.
"""

import re

import pytest

import config

POLA_REMAH = re.compile(r'<nav class="remah".*?</ol>', re.S)


def _jalur(html):
    """Ambil label remah dari halaman, tanpa teks tombol kembali."""
    m = POLA_REMAH.search(html)
    if not m:
        return []
    teks = re.findall(r">([^<>]+)</(?:a|span)>", m.group(0))
    return [t.strip() for t in teks if t.strip() and t.strip() != "Kembali"]


# --- remah navigasi ---------------------------------------------------------
@pytest.mark.parametrize("jalur,harapan", [
    ("/tentang", ["Peta", "Tentang"]),
    ("/istilah", ["Peta", "Daftar istilah"]),
    ("/data", ["Peta", "Data mentah"]),
    ("/metodologi", ["Peta", "Metodologi"]),
    ("/menu", ["Peta", "Galeri menu"]),
    ("/cluster", ["Peta", "Kelompok daerah"]),
    ("/rekomendasi", ["Peta", "Rekomendasi"]),
])
def test_remah_halaman_datar(klien, jalur, harapan):
    assert _jalur(klien.get(jalur).get_data(as_text=True)) == harapan


def test_remah_peta_tidak_ditampilkan(klien):
    """Halaman akar tidak perlu remah karena tidak punya induk."""
    assert not POLA_REMAH.search(klien.get("/").get_data(as_text=True))


def test_remah_menu_melalui_provinsinya(klien):
    """Induk sebuah menu adalah provinsinya, bukan galeri.

    Menu disusun per provinsi. Galeri hanyalah salah satu cara menemukannya,
    jadi memakainya sebagai induk membuat pengunjung dari jalur lain tersesat.
    """
    assert _jalur(klien.get("/menu/SD-380000-1").get_data(as_text=True)) == [
        "Peta", "Papua Pegunungan", "Menu SD",
    ]


def test_remah_produksi_punya_jalan_kembali(klien):
    """Halaman produksi dulu tidak punya tautan kembali sama sekali."""
    html = klien.get("/produsen?provinsi=Papua Pegunungan").get_data(as_text=True)
    assert _jalur(html) == ["Peta", "Papua Pegunungan", "Produksi bahan"]


def test_remah_menaut_ke_induk(klien):
    """Butir selain yang terakhir harus benar-benar dapat diklik."""
    html = klien.get("/menu/SD-380000-1").get_data(as_text=True)
    remah = POLA_REMAH.search(html).group(0)
    assert 'href="/"' in remah
    assert re.search(r'href="/provinsi/\d+"', remah)
    # Halaman saat ini ditandai, bukan ditautkan.
    assert 'aria-current="page"' in remah


def test_tombol_kembali_menyimpan_induk(klien):
    """Tombol menyimpan induk sebagai cadangan bila pengunjung tiba dari luar."""
    html = klien.get("/menu/SD-380000-1").get_data(as_text=True)
    assert re.search(r'data-induk="/provinsi/\d+"', html)


def test_tombol_kembali_ada_di_halaman_bertingkat(klien):
    for jalur in ["/menu/SD-380000-1", "/produsen", "/provinsi/60000", "/cluster"]:
        html = klien.get(jalur).get_data(as_text=True)
        assert 'id="remah-kembali"' in html, f"tombol kembali hilang di {jalur}"


def test_tautan_kembali_lama_sudah_dibuang(klien):
    """Tautan yang dipatok ke satu tujuan tidak boleh tersisa."""
    for jalur in ["/menu/SD-380000-1", "/provinsi/60000"]:
        html = klien.get(jalur).get_data(as_text=True)
        assert "back-link" not in html


# --- penanda bahan yang diproduksi setempat ---------------------------------
def test_tingkat_lokal_seluruh_cabang():
    assert config.tingkat_lokal(None) == "tanpa_data"
    assert config.tingkat_lokal(1.0) == "utama"
    assert config.tingkat_lokal(config.AMBANG_LOKAL_UTAMA) == "utama"
    assert config.tingkat_lokal(config.AMBANG_LOKAL_SEBAGIAN) == "sebagian"
    assert config.tingkat_lokal(0.5) == "sebagian"
    assert config.tingkat_lokal(0.1) == "sedikit"
    assert config.tingkat_lokal(0.0) == "tidak"


def test_ambang_berurutan():
    assert 0 < config.AMBANG_LOKAL_SEBAGIAN < config.AMBANG_LOKAL_UTAMA < 1


def test_setiap_tingkat_punya_label_dan_warna():
    for kunci in ["utama", "sebagian", "sedikit", "tidak", "tanpa_data"]:
        t = config.TINGKAT_LOKAL[kunci]
        assert t["label"] and t["arti"] and t["warna"].startswith("#")


def test_bahan_menu_membawa_penanda_lokal():
    import db
    d = db.menu_detail("SD-380000-1")
    for b in d["bahan"]:
        assert b["lokal"] in config.TINGKAT_LOKAL
        assert b["lokal_label"] == config.TINGKAT_LOKAL[b["lokal"]]["label"]
        # Penanda harus konsisten dengan nilai aslinya.
        assert b["lokal"] == config.tingkat_lokal(b["isl"])


def test_ringkasan_bahan_lokal_konsisten():
    import db
    d = db.menu_detail("SD-380000-1")
    hitung = sum(1 for b in d["bahan"] if b["lokal"] == "utama")
    assert d["bahan_lokal"] == hitung
    sebagian = sum(1 for b in d["bahan"] if b["lokal"] == "sebagian")
    assert d["bahan_lokal_sebagian"] == sebagian


def test_bahan_lokal_ikut_pada_daftar_menu():
    import db
    for m in db.menus(provinsi="Papua Pegunungan", jenjang="SD"):
        assert "bahan_lokal" in m
        assert m["bahan_lokal"] <= m["jumlah_bahan"]


def test_halaman_menu_menampilkan_penanda(klien):
    html = klien.get("/menu/SD-380000-1").get_data(as_text=True)
    assert 'class="tag-lokal"' in html
    assert "Diproduksi di provinsi ini" in html
    # Angka aslinya tetap ditampilkan di samping penandanya.
    assert "ISL" in html


def test_penanda_berbeda_antar_provinsi():
    """Bahan yang sama dapat berbeda penandanya di provinsi berbeda."""
    import db
    papua = db.menu_detail("SD-380000-1")
    jabar = db.menu_detail("SD-20000-1")
    assert papua["provinsi"] != jabar["provinsi"]
    tingkat = {b["lokal"] for b in papua["bahan"]} | {b["lokal"] for b in jabar["bahan"]}
    assert len(tingkat) > 1


# --- halaman daftar istilah -------------------------------------------------
def test_daftar_istilah_lengkap(klien):
    """Halaman istilah harus memuat singkatan maupun istilah non-singkatan."""
    html = klien.get("/istilah").get_data(as_text=True)
    for istilah in ["SPPG", "AHP", "AKG", "ISL", "IPW", "NBM", "TKPI",
                    "Silhouette", "Davies-Bouldin", "Kruskal-Wallis", "Waterfall",
                    "Tingkat kewaspadaan", "Alergen", "Intoleransi",
                    "Fobia makanan", "Status halal", "Rasio AKG",
                    "Koreksi pengambilan data", "Choropleth", "Imputasi"]:
        assert istilah in html, f"istilah {istilah} belum ada"


def test_singkatan_tidak_ganda():
    """Satu singkatan hanya boleh punya satu entri."""
    from collections import Counter
    hitung = Counter(i["singkatan"] for i in config.ISTILAH)
    ganda = [k for k, v in hitung.items() if v > 1]
    assert not ganda, f"entri ganda: {ganda}"


def test_tiap_istilah_lengkap_isinya():
    for i in config.ISTILAH:
        assert i["singkatan"] and i["panjang"] and i["arti"] and i["kelompok"]
