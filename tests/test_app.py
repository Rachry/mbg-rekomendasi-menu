"""
test_app.py: pengujian perilaku aplikasi: header, gerbang, galat, rate limit.

Beberapa pengujian di sini menyasar cacat yang ditemukan audit kode:
halaman galat yang kosong, rate limiter yang tidak pernah pulih, dan
Cache-Control yang berlawanan dengan komentarnya sendiri.
"""

import time

import pytest

import app as modul_app
import config

from angka_acuan import TOTAL_MENU


# --- halaman -----------------------------------------------------------------
@pytest.mark.parametrize("jalur", [
    "/", "/tentang", "/data", "/metodologi", "/menu", "/cluster",
    "/produsen", "/rekomendasi",
])
def test_halaman_200(klien, jalur):
    assert klien.get(jalur).status_code == 200


def test_halaman_provinsi(klien):
    from db import kode_dari_nama
    assert klien.get(f"/provinsi/{kode_dari_nama('Aceh')}").status_code == 200


def test_halaman_menu_detail(klien):
    assert klien.get("/menu/SD-60000-1").status_code == 200


# --- galat -------------------------------------------------------------------
def test_404_halaman_html(klien):
    r = klien.get("/halaman-tidak-ada")
    assert r.status_code == 404
    assert "tidak ditemukan" in r.get_data(as_text=True).lower()


def test_404_api_json(klien):
    r = klien.get("/api/jalur-tidak-ada")
    assert r.status_code == 404
    assert r.is_json and "error" in r.get_json()


def test_halaman_galat_tidak_kosong(klien):
    """500.html dulu berukuran nol byte, sehingga setiap galat jadi layar putih."""
    from flask import render_template
    with modul_app.app.test_request_context():
        html = render_template("500.html", kode=500, judul="Uji", pesan="Pesan uji")
    assert len(html) > 200
    assert "Pesan uji" in html
    assert "Uji" in html


# --- header ------------------------------------------------------------------
def test_security_header_lengkap(klien):
    h = klien.get("/").headers
    for nama in ["Content-Security-Policy", "X-Frame-Options",
                 "X-Content-Type-Options", "Referrer-Policy",
                 "Permissions-Policy"]:
        assert nama in h


def test_csp_tidak_lagi_mengizinkan_cdn(klien):
    csp = klien.get("/").headers["Content-Security-Policy"]
    # Leaflet dan Chart.js kini dilayani dari /static.
    assert "unpkg.com" not in csp
    assert "jsdelivr" not in csp


def test_csp_tidak_mengizinkan_skrip_inline_sembarangan(klien):
    """Mengunci T-1: 'unsafe-inline' dicabut dari script-src.

    Dengan 'unsafe-inline', peramban diminta menjalankan isi tag <script> apa
    pun, termasuk yang berhasil disisipkan penyerang. Penggantinya nonce yang
    berbeda tiap respons.
    """
    csp = klien.get("/").headers["Content-Security-Policy"]
    arahan = dict(
        (bagian.split(" ", 1) + [""])[:2]
        for bagian in (b.strip() for b in csp.split(";")) if bagian
    )
    assert "'unsafe-inline'" not in arahan["script-src"], csp
    assert "'unsafe-eval'" not in arahan["script-src"], csp
    assert "'nonce-" in arahan["script-src"], csp
    assert "'strict-dynamic'" in arahan["script-src"], csp


def test_csp_menutup_object_src(klien):
    """<object>, <embed>, dan <applet> adalah jalur lama menjalankan kode."""
    assert "object-src 'none'" in klien.get("/").headers["Content-Security-Policy"]


def test_nonce_berbeda_tiap_respons(klien):
    """Nonce yang dipakai ulang tidak melindungi apa pun.

    Penyerang yang sempat melihat satu respons akan tahu nonce berikutnya dan
    dapat menyisipkan skrip yang lolos.
    """
    import re
    ambil = lambda: re.search(r"'nonce-([^']+)'",
                              klien.get("/").headers["Content-Security-Policy"]).group(1)
    nonce = {ambil() for _ in range(5)}
    assert len(nonce) == 5, f"nonce berulang: {nonce}"
    assert all(len(n) >= 16 for n in nonce)


def test_nonce_header_cocok_dengan_nonce_halaman(klien):
    """Nonce di header harus sama dengan yang menempel di tag <script>.

    Kalau keduanya berbeda, seluruh skrip halaman berhenti berjalan dan webnya
    tampak kosong tanpa pesan galat apa pun. Ini pengujian yang paling penting
    dari kelompok ini karena kegagalannya paling sunyi.
    """
    import re
    r = klien.get("/")
    nonce = re.search(r"'nonce-([^']+)'", r.headers["Content-Security-Policy"]).group(1)
    halaman = r.get_data(as_text=True)
    tag = re.findall(r"<script[^>]*>", halaman)
    assert tag, "halaman tidak memuat tag script sama sekali"
    for t in tag:
        assert f'nonce="{nonce}"' in t, t


def test_hsts_tidak_dikirim_di_http(klien):
    """Mengunci S-6.

    HSTS pada koneksi http://127.0.0.1 membuat peramban memaksa HTTPS untuk
    seluruh localhost, termasuk proyek lain di port lain, dan bertahan sampai
    penyimpanan HSTS dibersihkan manual.
    """
    assert "Strict-Transport-Security" not in klien.get("/").headers


def test_hsts_dikirim_di_https(klien):
    r = klien.get("/", base_url="https://localhost")
    assert "max-age=31536000" in r.headers.get("Strict-Transport-Security", "")
    # preload sengaja tidak dipasang: mengeluarkan domain dari daftar preload
    # peramban butuh berbulan-bulan.
    assert "preload" not in r.headers["Strict-Transport-Security"]


def test_robots_melarang_pengindeksan(klien_baru):
    """Perayap tidak membawa cookie, jadi diuji dengan klien tanpa penanda.

    Versi pertama route ini ikut dicegat gerbang alur. Perayap yang meminta
    /robots.txt menerima pengalihan ke /tentang, sehingga aturan pengindeksan
    tidak pernah sampai. Ketahuan saat menguji lewat curl, bukan lewat klien
    uji, karena klien uji sudah membawa cookie yang lengkap.
    """
    r = klien_baru.get("/robots.txt", headers={"Accept": "*/*"})
    assert r.status_code == 200, r.headers.get("Location")
    assert r.mimetype == "text/plain"
    assert "Disallow: /" in r.get_data(as_text=True)


def test_robots_tidak_dicegat_gerbang_meski_meminta_html(klien_baru):
    """Sebagian perayap mengirim Accept yang menerima HTML."""
    assert klien_baru.get("/robots.txt", headers={"Accept": "text/html"}).status_code == 200


def test_favicon_tersedia(klien_baru):
    """Tanpa route ini, tiap kunjungan menyisakan satu galat 404 di log."""
    r = klien_baru.get("/favicon.ico", headers={"Accept": "text/html"})
    assert r.status_code == 301
    assert klien_baru.get("/static/favicon.svg").status_code == 200


def test_health_tidak_membocorkan_detail_galat(klien, monkeypatch):
    """Mengunci S-4.

    /health terbuka tanpa autentikasi karena probe platform harus dapat
    menjangkaunya. Apa pun yang dikembalikan di sana terbaca siapa saja, dan
    pesan galat SQLite memuat jalur lengkap berkas basis data di server.
    """
    import db as modul_db

    def _meledak():
        raise RuntimeError("/rahasia/jalur/di/server/mbg.db terkunci")

    monkeypatch.setattr(modul_db, "ringkasan", _meledak)
    r = klien.get("/health")
    assert r.status_code == 503
    badan = r.get_data(as_text=True)
    assert "rahasia" not in badan
    assert "error" not in r.get_json()
    assert r.get_json()["status"] == "degraded"


def test_aset_statis_boleh_di_cache(klien):
    """Dulu aset statis justru dilarang di-cache, berlawanan dengan komentarnya."""
    cc = klien.get("/static/css/style.css").headers.get("Cache-Control", "")
    assert "max-age" in cc
    assert "no-store" not in cc


def test_halaman_tidak_di_cache(klien):
    assert klien.get("/").headers.get("Cache-Control") == "no-store"


# --- gerbang halaman penjelasan ---------------------------------------------
def test_pengunjung_baru_diarahkan_ke_tentang(klien_baru):
    # Header Accept ditulis eksplisit: klien uji Flask mengirim Accept kosong,
    # sedangkan gerbang hanya berlaku untuk permintaan yang meminta HTML.
    r = klien_baru.get("/", headers={"Accept": "text/html"})
    assert r.status_code == 302
    assert "/tentang" in r.headers["Location"]


def test_gerbang_tidak_mengganggu_permintaan_non_html(klien_baru):
    # Pengambilan data lewat fetch tidak boleh ikut dialihkan.
    assert klien_baru.get("/").status_code == 200


def test_langkah_pertama_dan_halaman_bebas_terbuka(klien_baru):
    """Hanya langkah pertama dan halaman rujukan yang terbuka sejak awal.

    Langkah kedua dan ketiga sengaja tertutup sampai langkah sebelumnya
    dilalui; urutannya diuji lengkap di tests/test_gerbang.py.
    """
    for jalur in ["/tentang", "/health", "/istilah"]:
        r = klien_baru.get(jalur, headers={"Accept": "text/html"})
        assert r.status_code == 200


def test_api_bebas_gerbang(klien_baru):
    assert klien_baru.get("/api/ringkasan").status_code == 200


# --- health ------------------------------------------------------------------
def test_health(klien):
    d = klien.get("/health").get_json()
    assert d["status"] == "ok"
    assert d["menu"] == TOTAL_MENU


# --- rate limiter ------------------------------------------------------------
def test_rate_limit_saldo_tidak_pernah_negatif():
    """Dulu penolakan tetap mengurangi saldo, sehingga blokir makin panjang."""
    modul_app._ember.clear()
    ip = "203.0.113.9"
    for _ in range(config.RATE_LIMIT_PER_MINUTE + 60):
        modul_app._lolos_rate_limit(ip)
    _, saldo = modul_app._ember[ip]
    assert saldo >= 0.0


def test_rate_limit_pulih_setelah_jeda():
    modul_app._ember.clear()
    ip = "203.0.113.10"
    while modul_app._lolos_rate_limit(ip):
        pass
    assert modul_app._lolos_rate_limit(ip) is False
    # Laju isi ulang = kapasitas / 60 token per detik.
    time.sleep(1.1)
    assert modul_app._lolos_rate_limit(ip) is True


def test_rate_limit_pecahan_waktu_tidak_hilang():
    """Pengisian dulu memakai int(), jadi jeda pendek beruntun tidak mengisi apa pun."""
    modul_app._ember.clear()
    ip = "203.0.113.11"
    while modul_app._lolos_rate_limit(ip):
        pass
    for _ in range(12):
        time.sleep(0.1)
        modul_app._lolos_rate_limit(ip)
    _, saldo = modul_app._ember[ip]
    assert saldo > 0.0 or modul_app._lolos_rate_limit(ip)


def test_health_dikecualikan_dari_rate_limit(klien):
    modul_app._ember.clear()
    for _ in range(config.RATE_LIMIT_PER_MINUTE + 20):
        modul_app._lolos_rate_limit("127.0.0.1")
    assert klien.get("/health").status_code == 200


def test_ember_dibersihkan():
    modul_app._ember.clear()
    modul_app._pembersihan_terakhir = 0.0
    modul_app._lolos_rate_limit("198.51.100.1")
    assert "198.51.100.1" in modul_app._ember


# --- batas ukuran badan ------------------------------------------------------
def test_payload_terlalu_besar_ditolak(klien):
    besar = {"exclude_bahan": ["x" * 200 for _ in range(200)]}
    r = klien.post("/api/recommend", json=besar)
    assert r.status_code in (400, 413)


def test_pembatas_laju_berangkat_dari_saldo_penuh(klien):
    """Tiap kasus uji harus berangkat dari keadaan yang sama.

    Saldo pembatas laju disimpan pada kamus tingkat modul yang bertahan
    sepanjang proses. Sebelum dikosongkan otomatis, uji yang boros permintaan
    menghabiskan jatah uji berikutnya, sehingga hasil pengujian bergantung
    pada urutan. Setelah urutan diacak, kegagalan muncul pada lima dari lima
    benih yang dicoba.
    """
    import app as modul_app
    assert modul_app._ember == {}, (
        "Saldo pembatas laju tidak kosong di awal kasus uji. Fixture "
        "_kosongkan_pembatas_laju pada conftest.py mungkin terhapus."
    )
    for _ in range(20):
        assert klien.get("/api/ringkasan").status_code == 200
