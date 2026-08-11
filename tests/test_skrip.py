"""
test_skrip.py: penjaga kewarasan skrip sisi depan.

Latar belakangnya nyata: satu suntingan pernah meninggalkan `(function(){`
tanpa penutup di base.html. Galat sintaks itu mematikan seluruh blok skrip
inline pada setiap halaman, termasuk tombol ganti tema yang berada di blok
yang sama. Tidak ada pengujian yang menangkapnya karena server tetap
membalas 200 dan halamannya tetap terlihat wajar.

Catatan tentang cara memeriksanya. Menghitung keseimbangan kurung dengan
ekspresi reguler sempat dicoba dan dibuang, karena literal regex di dalam
JavaScript, misalnya /^Prov\\.\\s*/, membuat penghitungan meleset dan
menghasilkan kegagalan palsu pada berkas yang sebenarnya sah. Pemeriksaan
sintaks yang benar memerlukan parser sungguhan, jadi pengujian ini memakai
`node --check`. Bila Node.js tidak terpasang, pengujian dilewati dengan
alasan yang jelas, bukan diganti pemeriksaan lemah yang menyesatkan.
"""

import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

HALAMAN = [
    "/", "/tentang", "/istilah", "/data", "/metodologi", "/menu",
    "/cluster", "/produsen", "/rekomendasi", "/provinsi/60000",
    "/menu/SD-60000-1",
]

POLA_SKRIP = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)

ada_node = shutil.which("node") is not None
butuh_node = pytest.mark.skipif(
    not ada_node,
    reason="Node.js tidak terpasang; pemeriksaan sintaks JavaScript dilewati",
)


def _periksa_sintaks(kode, nama):
    """Jalankan `node --check`. Kembalikan pesan galat, atau None bila sah."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(kode)
        jalur = f.name
    try:
        hasil = subprocess.run(["node", "--check", jalur],
                               capture_output=True, text=True, timeout=30)
        if hasil.returncode != 0:
            return f"{nama}: {hasil.stderr.strip().splitlines()[-1]}"
        return None
    finally:
        pathlib.Path(jalur).unlink(missing_ok=True)


# --- skrip inline pada halaman yang benar-benar dirender --------------------
@butuh_node
@pytest.mark.parametrize("jalur", HALAMAN)
def test_skrip_inline_sah(klien, jalur):
    html = klien.get(jalur).get_data(as_text=True)
    galat = []
    for i, m in enumerate(POLA_SKRIP.finditer(html)):
        kode = m.group(1).strip()
        if not kode:
            continue
        pesan = _periksa_sintaks(kode, f"{jalur} blok ke-{i}")
        if pesan:
            galat.append(pesan)
    assert not galat, "Galat sintaks pada skrip inline:\n" + "\n".join(galat)


# --- berkas JavaScript terpisah ---------------------------------------------
@butuh_node
def test_berkas_js_sah():
    akar = pathlib.Path(__file__).resolve().parent.parent / "static" / "js"
    berkas = sorted(akar.glob("*.js"))
    assert berkas, "tidak ada berkas JavaScript yang ditemukan"
    galat = []
    for f in berkas:
        pesan = _periksa_sintaks(f.read_text(encoding="utf-8"), f.name)
        if pesan:
            galat.append(pesan)
    assert not galat, "Galat sintaks pada berkas JavaScript:\n" + "\n".join(galat)


# --- pemeriksaan struktural, selalu jalan tanpa Node ------------------------
def test_setiap_halaman_punya_tombol_tema(klien):
    """Tombol tema hilang berarti dark mode tidak dapat dinyalakan."""
    for jalur in HALAMAN:
        html = klien.get(jalur).get_data(as_text=True)
        assert 'id="theme-toggle"' in html, f"tombol tema hilang di {jalur}"


def test_pemasang_pendengar_tema_ada(klien):
    """Blok skrip tema harus memasang pendengar klik, bukan hanya ada tombolnya."""
    html = klien.get("/tentang").get_data(as_text=True)
    blok = [m.group(1) for m in POLA_SKRIP.finditer(html)
            if "theme-toggle" in m.group(1)]
    assert blok, "blok skrip tema tidak ditemukan"
    assert any("addEventListener" in js for js in blok)


def test_atribut_tema_awal_kosong(klien):
    """data-theme dibiarkan kosong agar preferensi sistem yang menentukan."""
    html = klien.get("/tentang").get_data(as_text=True)
    assert '<html lang="id" data-theme>' in html


def test_css_menyediakan_kedua_tema():
    """Berkas gaya harus memuat aturan tema gelap manual maupun otomatis."""
    css = (pathlib.Path(__file__).resolve().parent.parent
           / "static" / "css" / "style.css").read_text(encoding="utf-8")
    assert '[data-theme="dark"]' in css          # dipilih manual lewat tombol
    assert "prefers-color-scheme: dark" in css   # mengikuti preferensi sistem
    assert ':root:not([data-theme="light"])' in css


# --- halaman kelompok daerah ------------------------------------------------
def test_kelompok_tidak_memakai_kanvas(klien):
    """Grafik digambar dengan HTML agar ikut tema dan tajam saat diperbesar.

    Sebelumnya memakai Chart.js di atas kanvas. Teks sumbu digambar
    dengan warna bawaan pustaka sehingga tidak ikut mode gelap, dan hasilnya
    berupa raster yang pecah bila diperbesar untuk gambar naskah.
    """
    html = klien.get("/cluster").get_data(as_text=True)
    assert "<canvas" not in html
    assert "chart.umd" not in html


def test_kelompok_tidak_menanam_warna_tetap(klien):
    """Warna diambil dari data dan variabel CSS, bukan ditulis tetap di templat."""
    import re as _re
    html = klien.get("/cluster").get_data(as_text=True)
    # Kode warna heksadesimal yang ditanam langsung tidak akan ikut ganti tema.
    assert not _re.findall(r"#[0-9a-fA-F]{6}", html)
    assert "var(--" in html


def test_kelompok_punya_bagian_utama(klien):
    html = klien.get("/cluster").get_data(as_text=True)
    for penanda in ['id="kl-kartu"', 'id="kl-panel"', 'id="kl-antar"',
                    'id="kl-tabel"', 'id="kl-daftar"']:
        assert penanda in html, f"bagian {penanda} hilang"


def test_vendor_hanya_berisi_yang_dipakai():
    """Pustaka yang tidak lagi dipakai tidak boleh tertinggal di repositori."""
    import pathlib
    vendor = pathlib.Path(__file__).resolve().parent.parent / "static" / "vendor"
    assert (vendor / "leaflet" / "leaflet.js").exists()
    assert not (vendor / "chart.umd.min.js").exists()


# --- properti hidden harus benar-benar menyembunyikan -----------------------
def test_aturan_hidden_global_ada():
    """Aturan bawaan [hidden] kalah oleh kelas yang menyetel display.

    Masalah ini sudah muncul dua kali pada halaman berbeda: kotak centang
    yang seharusnya tersembunyi tetap terlihat karena kelasnya menyetel
    display flex atau grid. Aturan global mencegahnya terulang.
    """
    css = (pathlib.Path(__file__).resolve().parent.parent
           / "static" / "css" / "style.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in css


def test_kelas_penyetel_display_tidak_menggagalkan_hidden():
    """Kelas yang menyetel display dan dipakai bersama hidden harus aman."""
    import re as _re
    akar = pathlib.Path(__file__).resolve().parent.parent / "static" / "css"
    gabung = "\n".join(f.read_text(encoding="utf-8") for f in akar.glob("*.css"))
    # Aturan global harus ada sebelum kelas mana pun dapat mengalahkannya.
    assert _re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important", gabung)


def test_penyaring_menu_dibungkus_agar_dapat_disembunyikan(klien):
    """Jenjang dan tingkat tidak berlaku pada lapisan produksi."""
    html = klien.get("/").get_data(as_text=True)
    assert 'id="grup-menu"' in html
    assert 'id="grup-saring"' in html


def test_tombol_atur_ulang_tetap_terjangkau(klien):
    """Tombol atur ulang berada setelah grup yang disembunyikan.

    Dengan begitu ia tetap terlihat pada kedua lapisan peta.
    """
    html = klien.get("/").get_data(as_text=True)
    assert html.index('id="reset"') > html.index('id="grup-menu"')


def test_alasan_tanpa_penyaringan_dijelaskan(klien):
    """Keputusan tidak menyaring data resmi harus dinyatakan dasarnya.

    Pembaca perlu tahu bahwa angka besar pada provinsi tertentu adalah
    spesialisasi wilayah, bukan galat yang lolos pemeriksaan.
    """
    html = klien.get("/").get_data(as_text=True)
    assert "Mengapa tidak ada penyaringan?" in html
    assert "Badan Pusat Statistik" in html            # siapa yang bertanggung jawab
    assert "spesialisasi" not in html or "sentra" in html   # alasan angka besar
    assert "tanpa penyaringan kewajaran" in html
    # Tidak boleh ada lagi kotak centang penyembunyian.
    assert 'id="f-sembunyikan"' not in html


def test_panel_peta_tidak_memotong_isinya():
    """Panel harus dapat digulir penuh saat keterangan dibentangkan.

    Sebelumnya `.panel-body` dipatok max-height 600px dengan overflow hidden
    demi animasi pelipatan. Begitu keterangan pada lapisan produksi dibuka,
    isinya melampaui batas itu lalu terpotong dan tidak dapat digulir.
    """
    css = (pathlib.Path(__file__).resolve().parent.parent
           / "static" / "css" / "map.css").read_text(encoding="utf-8")
    assert "max-height: 600px" not in css
    # Pemotongan hanya boleh terjadi pada keadaan terlipat.
    blok = css[css.index(".panel-body {"):css.index(".panel.collapsed .panel-body")]
    assert "overflow: visible" in blok
    # Panel induknya yang menyediakan gulir.
    assert "overflow-y: auto" in css


# variabel yang tidak pernah dideklarasikan
# `node --check` hanya memeriksa sintaks. Rujukan ke variabel yang tidak pernah
# dideklarasikan lolos pemeriksaan itu, padahal di peramban ia melempar
# ReferenceError dan menghentikan seluruh sisa berkas tanpa gejala apa pun.
#
# Cacat itu pernah terjadi. Dua rujukan ke kotak centang yang sudah dihapus
# tertinggal di map.js, sehingga skrip berhenti pada baris 331 dan pemasangan
# pendengar pencarian pada baris 359 tidak pernah berjalan. Akibatnya kotak
# "Cari provinsi" diam saja, baik pada lapisan kewaspadaan maupun produksi,
# tanpa satu pun pengujian gagal.

ALAT_VARIABEL = pathlib.Path(__file__).resolve().parent / "alat" / "periksa_variabel.js"
DIR_JS = pathlib.Path(__file__).resolve().parent.parent / "static" / "js"


def _jalankan_pemeriksa(berkas):
    return subprocess.run(
        ["node", str(ALAT_VARIABEL), str(berkas)],
        capture_output=True, text=True, timeout=30,
    )


@butuh_node
@pytest.mark.parametrize("berkas", sorted(DIR_JS.glob("*.js")), ids=lambda p: p.name)
def test_tidak_ada_variabel_tak_dideklarasikan(berkas):
    hasil = _jalankan_pemeriksa(berkas)
    assert "REFERENCE_ERROR" not in hasil.stdout, (
        f"{berkas.name}: {hasil.stdout.strip()}\n"
        "Variabel dipakai tetapi tidak pernah dideklarasikan. Di peramban ini "
        "menghentikan seluruh sisa berkas, sehingga fitur di bawahnya diam "
        "tanpa pesan galat."
    )


@butuh_node
def test_pemeriksa_variabel_memang_menangkap_cacat(tmp_path):
    """Alatnya sendiri diuji, supaya tidak lolos hanya karena tidak berfungsi."""
    umpan = tmp_path / "bercacat.js"
    umpan.write_text(
        "(function () {\n"
        "  'use strict';\n"
        "  var a = 1;\n"
        "  if (variabelYangTidakAda) { a = 2; }\n"
        "})();\n",
        encoding="utf-8",
    )
    hasil = _jalankan_pemeriksa(umpan)
    assert "REFERENCE_ERROR" in hasil.stdout
    assert "variabelYangTidakAda" in hasil.stdout

    sehat = tmp_path / "sehat.js"
    sehat.write_text("(function () { var a = 1; if (a) { a = 2; } })();\n",
                     encoding="utf-8")
    assert "REFERENCE_ERROR" not in _jalankan_pemeriksa(sehat).stdout
