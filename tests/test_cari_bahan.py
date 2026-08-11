"""
test_cari_bahan.py: penyaring "cari bahan" dan penanda bahan lokal di kartu.

Latar belakangnya laporan nyata: mencari "babi" pada halaman rekomendasi
tidak memunculkan menu berbabi. Penyebabnya bukan data hilang, melainkan
logika penyaring yang tidak lengkap. Pemilih bahan satu-satunya hanya bisa
MEMBUANG menu, sehingga mencentang "Daging babi kurus" justru menyingkirkan
kelima belas menu yang memuatnya. Tidak ada cara mencari menu yang memuat
sebuah bahan.

Pilihan bawaan "cukup salah satu" bukan selera melainkan hasil analisis:
tiap menu hanya memuat lima sampai enam bahan, sehingga mensyaratkan tiga
bahan tertentu muncul bersamaan menghasilkan nol hasil pada 90 persen
kombinasi acak, sedangkan syarat salah satu tidak pernah menghasilkan nol.
"""

import pytest

import config
import db

from angka_acuan import TOTAL_MENU

BABI = "Daging babi kurus"
from angka_acuan import MENU_NON_HALAL as MENU_BERBABI  # menu bermuatan babi


# --- bahan yang dicari ada di pemilih ---------------------------------------
def test_bahan_babi_ada_di_pemilih():
    nama = [b["nama_bahan"] for b in db.ingredients_all(hanya_terpakai=True)]
    assert BABI in nama


def test_seluruh_bahan_pemilih_masuk_kategori_yang_dirender():
    """Bahan berkategori di luar daftar tidak akan pernah muncul di layar."""
    for b in db.ingredients_all(hanya_terpakai=True):
        assert b["kategori"] in config.KATEGORI_MENU


def test_pemilih_menyediakan_dua_tindakan(klien):
    """Pemilih memakai pola cari lalu pilih tindakan.

    Pola sebelumnya memasang dua kotak centang tanpa nama pada tiap baris,
    sehingga pengguna harus mengingat kolom mana berarti apa. Sekarang tiap
    tindakan punya tombol bertulisan sendiri, dibuat saat bahan dicari.
    """
    html = klien.get("/rekomendasi").get_data(as_text=True)
    assert 'id="fCariBahan"' in html        # satu kotak pencarian
    assert 'id="pilihanBahan"' in html      # tempat keping pilihan
    assert "Tampilkan" in html and "Hindari" in html
    assert BABI in html                     # datanya tersedia untuk dicari


def test_daftar_bahan_dikirim_sebagai_data(klien):
    """Daftar bahan tidak lagi dirender menjadi ratusan kotak centang."""
    html = klien.get("/rekomendasi").get_data(as_text=True)
    assert "var BAHAN" in html
    assert html.count('"nama_bahan"') == len(db.ingredients_all(hanya_terpakai=True))
    # Halaman jauh lebih ringan tanpa 190 kotak centang.
    assert html.count("<input") < 30


# --- mencari bahan ----------------------------------------------------------
def test_cari_babi_mengembalikan_menu_berbabi():
    r = db.recommend(include_bahan=[BABI], batas=50)
    assert r["total_lolos"] == MENU_BERBABI


def test_cari_bahan_hasilnya_benar_benar_memuat_bahan_itu():
    r = db.recommend(include_bahan=[BABI], batas=50)
    for m in r["rekomendasi"]:
        detail = db.menu_detail(m["menu_id"])
        assert any(b["nama_bahan"] == BABI for b in detail["bahan"])


def test_cari_dan_hindari_adalah_kebalikan():
    """Menu yang lolos 'cari' harus persis yang dibuang 'hindari'."""
    total = db.ringkasan()["total_menu"]
    cari = db.recommend(include_bahan=[BABI])["total_lolos"]
    hindari = db.recommend(exclude_bahan=[BABI])["total_lolos"]
    assert cari + hindari == total


@pytest.mark.parametrize("bahan", [
    "Beras putih nasi", "Sagu lempeng", "Telur ayam rebus", "Tempe",
])
def test_cari_beragam_bahan(bahan):
    r = db.recommend(include_bahan=[bahan], batas=50)
    assert r["total_lolos"] > 0


def test_cari_bahan_tidak_dikenal_menghasilkan_nol():
    assert db.recommend(include_bahan=["Bahan Khayalan"])["total_lolos"] == 0


# --- salah satu vs harus semua ----------------------------------------------
def _sepasang_yang_bersanding():
    """Cari sepasang bahan yang benar-benar muncul bersama pada suatu menu.

    Pasangannya tidak ditulis tangan, sebab bahan yang terpilih berubah setiap
    kali pipeline dijalankan dengan data baru. Menuliskannya membuat pengujian
    gagal karena datanya bergeser, bukan karena kodenya rusak.
    """
    with db._connect() as con:
        baris = con.execute(
            "SELECT a.nama_bahan AS x, b.nama_bahan AS y "
            "FROM menu_provinsi_komposisi a "
            "JOIN menu_provinsi_komposisi b "
            "  ON a.menu_id = b.menu_id AND a.nama_bahan < b.nama_bahan "
            "GROUP BY a.nama_bahan, b.nama_bahan "
            "HAVING COUNT(*) >= 2 ORDER BY COUNT(*) DESC LIMIT 1"
        ).fetchone()
    assert baris is not None, "tidak ada sepasang bahan yang bersanding"
    return [baris["x"], baris["y"]]


def test_bawaan_cukup_salah_satu():
    dua = _sepasang_yang_bersanding()
    salah_satu = db.recommend(include_bahan=dua)["total_lolos"]
    semua = db.recommend(include_bahan=dua, include_semua=True)["total_lolos"]
    assert salah_satu > semua > 0, f"pasangan {dua}: {salah_satu} vs {semua}"


def test_harus_semua_benar_benar_memuat_keduanya():
    dua = _sepasang_yang_bersanding()
    r = db.recommend(include_bahan=dua, include_semua=True, batas=50)
    for m in r["rekomendasi"]:
        nama = {b["nama_bahan"] for b in db.menu_detail(m["menu_id"])["bahan"]}
        assert set(dua) <= nama


def test_salah_satu_cukup_satu_yang_cocok():
    dua = ["Sagu lempeng", "Ikan patin kukus"]
    r = db.recommend(include_bahan=dua, batas=50)
    for m in r["rekomendasi"]:
        nama = {b["nama_bahan"] for b in db.menu_detail(m["menu_id"])["bahan"]}
        assert nama & set(dua)


def test_filter_melaporkan_mode_yang_dipakai():
    r = db.recommend(include_bahan=[BABI], include_semua=True)
    assert r["filter"]["include_bahan"] == [BABI]
    assert r["filter"]["include_semua"] is True


# --- gabungan penyaring yang saling bertentangan ----------------------------
def test_cari_babi_dengan_halal_saja_menghasilkan_nol():
    """Keduanya saling meniadakan, dan itu harus terlihat sebagai nol jujur."""
    r = db.recommend(include_bahan=[BABI], halal_saja=True)
    assert r["total_lolos"] == 0


def test_cari_dan_hindari_bahan_yang_sama_menghasilkan_nol():
    r = db.recommend(include_bahan=[BABI], exclude_bahan=[BABI])
    assert r["total_lolos"] == 0


def test_cari_bahan_digabung_provinsi():
    r = db.recommend(include_bahan=[BABI], provinsi="Bali", batas=50)
    assert r["total_lolos"] > 0
    assert all(m["provinsi"] == "Bali" for m in r["rekomendasi"])


# --- endpoint ---------------------------------------------------------------
def test_api_cari_bahan_get(klien):
    d = klien.get(f"/api/recommend?include_bahan={BABI}&batas=50").get_json()
    assert d["total_lolos"] == MENU_BERBABI


def test_api_cari_bahan_post(klien):
    d = klien.post("/api/recommend",
                   json={"include_bahan": [BABI], "batas": 50}).get_json()
    assert d["total_lolos"] == MENU_BERBABI


def test_api_include_semua(klien):
    d = klien.post("/api/recommend", json={
        "include_bahan": ["Sagu lempeng", "Ikan patin kukus"],
        "include_semua": True,
    }).get_json()
    assert d["filter"]["include_semua"] is True


# --- penanda bahan lokal pada kartu -----------------------------------------
def test_kartu_membawa_ringkasan_bahan():
    """Kartu harus dapat menandai bahan lokal tanpa membuka halaman detail."""
    for m in db.menus(provinsi="Papua Pegunungan", jenjang="SD"):
        assert m["bahan_ringkas"]
        assert len(m["bahan_ringkas"]) == m["jumlah_bahan"]
        for b in m["bahan_ringkas"]:
            assert b["lokal"] in config.TINGKAT_LOKAL


def test_ringkasan_bahan_tidak_diambil_dari_label():
    """menu_label menghilangkan bahan lemak pada sebagian besar menu.

    Karena itu nama bahan pada kartu harus berasal dari tabel komposisi,
    bukan hasil memecah menu_label.
    """
    m = db.menus(provinsi="Aceh", jenjang="SD")[0]
    dari_label = {x.strip() for x in m["menu_label"].split("+")}
    dari_ringkas = {b["nama_bahan"] for b in m["bahan_ringkas"]}
    assert dari_ringkas >= dari_label
    detail = db.menu_detail(m["menu_id"])
    assert dari_ringkas == {b["nama_bahan"] for b in detail["bahan"]}


def test_penanda_kartu_cocok_dengan_halaman_detail():
    m = db.menus(provinsi="Papua Pegunungan", jenjang="SD")[0]
    detail = db.menu_detail(m["menu_id"])
    peta = {b["nama_bahan"]: b["lokal"] for b in detail["bahan"]}
    for b in m["bahan_ringkas"]:
        assert b["lokal"] == peta[b["nama_bahan"]]


def test_halaman_rekomendasi_menyiapkan_keterangan_penanda(klien):
    html = klien.get("/rekomendasi").get_data(as_text=True)
    assert "keping-utama" in html          # gaya penanda tersedia
    assert "Diproduksi di provinsi ini" in html


# --- galeri memuat bertahap -------------------------------------------------
def test_api_menus_membalas_dengan_total(klien):
    d = klien.get("/api/menus?batas=60").get_json()
    assert d["total"] == TOTAL_MENU
    assert d["ditampilkan"] == 60
    assert len(d["data"]) == 60


def test_api_menus_tanpa_batas_utuh(klien):
    d = klien.get("/api/menus?provinsi=Aceh").get_json()
    assert d["total"] == d["ditampilkan"] == len(d["data"])


def test_api_menus_batas_bukan_angka(klien):
    assert klien.get("/api/menus?batas=xx").status_code == 400


def test_galeri_punya_tombol_muat_lagi(klien):
    html = klien.get("/menu").get_data(as_text=True)
    assert 'id="g-lagi"' in html
