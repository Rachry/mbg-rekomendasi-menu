"""
test_gerbang.py: pengujian alur penjelasan wajib.

Sebelum melihat peta dan menu, pengunjung harus melewati tiga halaman secara
berurutan. Sebelumnya hanya memeriksa satu cookie yang diset JavaScript
di akhir halaman terakhir, sehingga dua halaman pertama dapat dilompati.
"""

import re
import pytest

import app as modul_app


def test_pengunjung_baru_diarahkan_ke_langkah_pertama(klien_baru, html):
    r = klien_baru.get("/", headers=html)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/tentang")


@pytest.mark.parametrize("jalur", ["/", "/menu", "/rekomendasi", "/cluster", "/produsen"])
def test_halaman_utama_tertutup_sebelum_alur_selesai(klien_baru, html, jalur):
    assert klien_baru.get(jalur, headers=html).status_code == 302


def test_tidak_bisa_melompati_langkah(klien_baru, html):
    # Langsung ke langkah dua dan tiga harus dikembalikan ke langkah satu.
    assert klien_baru.get("/data", headers=html).headers["Location"].endswith("/tentang")
    assert klien_baru.get("/metodologi", headers=html).headers["Location"].endswith("/tentang")


def test_alur_berurutan_terbuka_satu_per_satu(klien_baru, html):
    c = klien_baru
    assert c.get("/tentang", headers=html).status_code == 200

    assert c.get("/lanjut/1", headers=html).headers["Location"].endswith("/data")
    assert c.get("/data", headers=html).status_code == 200
    # Langkah tiga masih tertutup.
    assert c.get("/metodologi", headers=html).status_code == 302

    assert c.get("/lanjut/2", headers=html).headers["Location"].endswith("/metodologi")
    assert c.get("/metodologi", headers=html).status_code == 200
    # Peta masih tertutup sampai langkah tiga ditandai selesai.
    assert c.get("/", headers=html).status_code == 302

    assert c.get("/lanjut/3", headers=html).headers["Location"].endswith("/")
    assert c.get("/", headers=html).status_code == 200


def test_penanda_tidak_mundur(klien_baru, html):
    c = klien_baru
    for langkah in (1, 2, 3):
        c.get(f"/lanjut/{langkah}", headers=html)
    # Membuka ulang langkah lama tidak boleh menutup kembali halaman utama.
    c.get("/lanjut/1", headers=html)
    assert c.get("/", headers=html).status_code == 200


def test_langkah_tidak_sah_404(klien_baru):
    assert klien_baru.get("/lanjut/0").status_code == 404
    assert klien_baru.get("/lanjut/9").status_code == 404


def test_ulangi_panduan_mengosongkan_penanda(klien, html):
    assert klien.get("/", headers=html).status_code == 200
    klien.get("/ulangi-panduan", headers=html)
    assert klien.get("/", headers=html).status_code == 302


def test_cookie_rusak_dianggap_belum_mulai(klien_baru, html):
    for rusak in ["bukan-angka", "3", "", ":::", "abc:def"]:
        klien_baru.set_cookie("mbg_alur", rusak)
        assert klien_baru.get("/", headers=html).status_code == 302, rusak


def test_cookie_dipalsukan_di_luar_rentang(klien_baru, html):
    """Nilai di luar rentang dipangkas, bukan dipercaya begitu saja."""
    tanda = modul_app.PENANDA_JALAN
    klien_baru.set_cookie("mbg_alur", f"{tanda}:999")
    assert klien_baru.get("/", headers=html).status_code == 200
    klien_baru.set_cookie("mbg_alur", f"{tanda}:-5")
    assert klien_baru.get("/", headers=html).status_code == 302


def test_cookie_sesi_lama_diulang_dari_awal(klien_baru, html):
    """Alur diulang setiap kali aplikasi dijalankan.

    Cookie dari sesi sebelumnya membawa penanda yang berbeda, sehingga
    kemajuannya tidak diakui dan pengunjung membaca ulang ketiga halaman.
    """
    klien_baru.set_cookie("mbg_alur", "penanda-lama:3")
    r = klien_baru.get("/", headers=html)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/tentang")


def test_penanda_sama_di_seluruh_worker():
    """Penanda alur harus dapat direproduksi dari lingkungan, bukan diacak.

    Ini mengunci temuan K-1. Gunicorn menjalankan beberapa proses sekaligus,
    dan tiap proses menjalankan config.py sendiri-sendiri. Penanda yang diacak
    per proses membuat cookie terbitan satu worker ditolak worker lain,
    sehingga pengunjung dilempar balik ke halaman pertama pada sebagian besar
    klik. Dijalankan ulang dengan lingkungan yang sama, penanda harus sama.
    """
    import importlib
    import os

    lingkungan = dict(os.environ)
    lingkungan["MBG_RILIS"] = "commit-abc123"

    hasil = []
    for _ in range(4):                       # empat "worker"
        os.environ.clear()
        os.environ.update(lingkungan)
        modul = importlib.reload(importlib.import_module("config"))
        hasil.append(modul.RILIS)

    os.environ.clear()
    os.environ.update(lingkungan)
    importlib.reload(importlib.import_module("config"))

    assert len(set(hasil)) == 1, f"penanda berbeda antarworker: {hasil}"


def test_penanda_berubah_saat_rilis_berganti():
    """Deploy baru harus mengulang alur penjelasan dari awal."""
    import importlib
    import os

    asli = dict(os.environ)
    penanda = []
    try:
        for rilis in ("commit-lama", "commit-baru"):
            os.environ["MBG_RILIS"] = rilis
            penanda.append(importlib.reload(importlib.import_module("config")).RILIS)
    finally:
        os.environ.clear()
        os.environ.update(asli)
        importlib.reload(importlib.import_module("config"))

    assert penanda[0] != penanda[1]


def test_kunci_wajib_diset_di_produksi():
    """Aplikasi menolak start di produksi tanpa SECRET_KEY.

    Lebih baik gagal saat start dengan pesan yang jelas daripada berjalan
    dengan kunci karangan yang berbeda di tiap worker.
    """
    import importlib
    import os

    asli = dict(os.environ)
    try:
        for kunci in ("SECRET_KEY", "MBG_SECRET_KEY", "MBG_RILIS"):
            os.environ.pop(kunci, None)
        os.environ["FLASK_ENV"] = "production"
        with pytest.raises(RuntimeError, match="MBG_SECRET_KEY"):
            importlib.reload(importlib.import_module("config"))
    finally:
        os.environ.clear()
        os.environ.update(asli)
        importlib.reload(importlib.import_module("config"))


def test_cookie_alur_tanpa_masa_berlaku(klien_baru, html):
    """Cookie berlaku sebatas sesi peramban, bukan setahun."""
    r = klien_baru.get("/lanjut/1", headers=html)
    kuki = r.headers.get("Set-Cookie", "")
    assert "Expires=" not in kuki
    assert "Max-Age=" not in kuki


def test_penanda_jalan_diacak_tiap_proses():
    assert modul_app.PENANDA_JALAN
    assert len(modul_app.PENANDA_JALAN) >= 8


# --- penanda langkah setelah alur selesai -----------------------------------
def test_banner_langkah_hilang_setelah_alur_selesai(klien):
    """Setelah ketiganya dilalui, ketiga halaman menjadi halaman biasa.

    Menyisakan penanda "Langkah 1 dari 3" justru membingungkan, sebab
    pengunjung tidak sedang menjalani alur apa pun.
    """
    for jalur in ["/tentang", "/data", "/metodologi"]:
        h = klien.get(jalur).get_data(as_text=True)
        assert "onboard-banner" not in h, jalur
        # Yang diperiksa penanda alurnya, bukan kata "Langkah" begitu saja.
        # Halaman metodologi memakai kata itu pada prosa biasa, misalnya
        # "Langkah ini menilai bahannya", dan itu memang seharusnya ada.
        assert not re.search(r"Langkah\s+\d+\s+dari\s+\d+", h), jalur
        assert "ob-step" not in h, jalur


def test_banner_langkah_muncul_selama_alur(klien_baru, html):
    h = klien_baru.get("/tentang", headers=html).get_data(as_text=True)
    assert "onboard-banner" in h
    assert "Langkah 1 dari 3" in h


def test_tombol_lanjut_hilang_setelah_alur_selesai(klien):
    for jalur in ["/tentang", "/data", "/metodologi"]:
        h = klien.get(jalur).get_data(as_text=True)
        assert "onboard-nav" not in h, jalur


def test_halaman_selalu_terbuka_tidak_ikut_gerbang(klien_baru, html):
    """Tidak satu pun jalur bebas boleh berakhir di halaman alur.

    Yang diperiksa bukan status 200, melainkan bahwa jawabannya bukan
    pengalihan ke halaman alur. /favicon.ico menjawab 301 ke berkas statis, dan
    itu benar. Sebelumnya menuntut 200 untuk semuanya, yang membuat
    penambahan jalur bebas yang sah ikut menggagalkan pengujian.
    """
    for jalur in modul_app.JALUR_SELALU_TERBUKA:
        r = klien_baru.get(jalur, headers=html)
        tujuan = r.headers.get("Location", "")
        assert not any(tujuan.endswith(t["jalur"]) for t in modul_app.ALUR), \
            f"{jalur} dicegat gerbang dan dialihkan ke {tujuan}"
        assert r.status_code in (200, 301), f"{jalur} -> {r.status_code}"


def test_api_tidak_ikut_gerbang(klien_baru):
    assert klien_baru.get("/api/ringkasan").status_code == 200


def test_permintaan_bukan_html_tidak_dialihkan(klien_baru):
    # Pengambilan data lewat fetch tidak boleh ikut dialihkan ke /tentang.
    assert klien_baru.get("/").status_code == 200


def test_cookie_alur_httponly(klien_baru, html):
    r = klien_baru.get("/lanjut/1", headers=html)
    kuki = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in kuki
    assert "SameSite=Lax" in kuki
