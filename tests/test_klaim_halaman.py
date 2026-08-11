"""
test_klaim_halaman.py: pengujian kesesuaian pernyataan halaman dengan data.

Latar belakangnya satu cacat nyata. Halaman Tentang pernah menyatakan sebagian
baris data merupakan hasil estimasi, padahal kolom `is_imputed` bernilai nol
pada seluruh baris. Cacat itu bertahan lama karena dua sebab: tidak ada uji
yang menyentuh jalur imputasi, dan tidak ada yang memeriksa apakah pernyataan
pada halaman masih sesuai isi basis datanya.

Berkas ini menutup kedua celah tersebut. Seluruhnya blackbox, sebab yang dinilai
adalah apa yang benar-benar dibaca pengunjung, bukan bagaimana kodenya bekerja.
"""

import re

import pytest

import angka_acuan as A
import db


HALAMAN_PENJELASAN = ["/tentang", "/data", "/metodologi", "/istilah"]


# Jalur imputasi

def test_pernyataan_imputasi_sesuai_isi_basis_data(klien):
    """Halaman Tentang tidak boleh mengaku ada estimasi bila tidak ada.

    Inilah cacat yang pernah terjadi. Pernyataannya kini bercabang mengikuti
    angka pada basis data, sehingga tidak dapat lagi bertentangan dengannya.
    """
    n = db.ringkasan()["baris_imputed"]
    h = klien.get("/tentang").get_data(as_text=True)

    if n == 0:
        assert "tidak ada satu pun baris hasil" in h
        assert "Sebagian baris data hasil estimasi" not in h
    else:
        assert str(n) in h
        assert "tidak ada satu pun baris hasil" not in h


def test_daftar_istilah_tidak_menjanjikan_penanda_yang_tak_ada(klien):
    """Istilah imputasi pernah menjanjikan penanda yang "selalu ditandai".

    Janji itu tidak dapat dipenuhi ketika tidak ada satu pun baris imputasi.
    """
    h = klien.get("/istilah").get_data(as_text=True)
    assert "selalu ditandai" not in h
    assert "imputasi" in h.lower()


def test_kolom_estimasi_tetap_tersedia_pada_data_mentah(klien):
    """Mekanismenya dipertahankan meski datanya nihil.

    Snapshot berikutnya bisa saja memuat baris imputasi, dan penandanya harus
    muncul sendiri tanpa perlu mengubah kode.
    """
    d = klien.get("/api/data-mentah").get_json()
    assert "is_imputed" in d["kolom"]


def test_penanda_baris_imputasi_ada_pada_skrip_dan_gaya():
    """Jalur penandaannya harus tetap utuh, bukan ikut terhapus."""
    js = open("static/js/data.js", encoding="utf-8").read()
    assert "is_imputed" in js
    assert "row-imputed" in js
    templat = open("templates/provinsi.html", encoding="utf-8").read()
    assert "is_imputed" in templat


# Klaim yang pernah keliru

@pytest.mark.parametrize("klaim", [
    "surplus produksi beras",
    "kesenjangan protein hewani-nabati",
    "Statistik Konsumsi Pangan",
])
def test_klaim_fiktif_tidak_muncul_lagi(klien, klaim):
    """Ketiganya menggambarkan sistem yang tidak pernah dibangun.

    Pemilihan bahan memakai Indeks Pola Pangan Wilayah dan Indeks Sumber
    Lokal. Tidak ada logika surplus beras di mana pun pada pipeline.
    """
    h = klien.get("/tentang").get_data(as_text=True)
    assert klaim not in h


def test_metode_bobot_ahp_disebut_dengan_benar(klien):
    """Bobot berasal dari rata-rata kolom, bukan rata-rata geometrik."""
    h = klien.get("/metodologi").get_data(as_text=True)
    assert "rata-rata geometrik" not in h
    assert "jumlah kolomnya" in h


def test_persentase_makan_siang_sesuai_basis_data(klien):
    """Sempat tertulis 30-35 persen untuk keempat zat gizi.

    Nilai sebenarnya 32,5 persen untuk energi, lemak, dan karbohidrat, serta
    35 persen untuk protein.
    """
    h = klien.get("/metodologi").get_data(as_text=True)
    assert "30-35%" not in h and "30-35%" not in h
    assert "32,5 persen" in h
    for a in db.akg_standards():
        persen = f"{a['pct_energi'] * 100:.1f}".replace(".", ",")
        assert f"{persen}%" in h, a["jenjang"]


# Angka pada halaman harus berasal dari basis data

def test_angka_pokok_pada_halaman_sesuai_basis_data(klien):
    """Angka yang disebut halaman penjelasan dicocokkan ke basis data."""
    r = db.ringkasan()
    tentang = klien.get("/tentang").get_data(as_text=True)
    metod = klien.get("/metodologi").get_data(as_text=True)

    assert str(r["total_bahan"]) in tentang
    assert str(r["bahan_terpakai"]) in tentang
    assert str(r["total_grid"]) in tentang
    assert str(r["total_baris_provinsi"]) in tentang
    assert str(r["total_grid"]) in metod
    assert str(r["produksi_tahun_awal"]) in metod
    assert str(r["produksi_tahun_akhir"]) in metod


def test_target_gizi_pada_metodologi_sesuai_tabel_akg(klien):
    h = klien.get("/metodologi").get_data(as_text=True)
    for a in db.akg_standards():
        nilai = f"{a['energi_siang']:.1f}".replace(".", ",")
        assert nilai in h, f"{a['jenjang']} {nilai}"


def test_profil_kluster_pada_metodologi_sesuai_basis_data(klien):
    h = klien.get("/metodologi").get_data(as_text=True)
    for p in db.cluster_profiles(jenjang="SMP"):
        skor = f"{p['mean_weighted_score']:.6f}".replace(".", ",")
        assert skor in h, p["label_risiko"]


def test_cakupan_isl_pada_tentang_sesuai_basis_data(klien):
    h = klien.get("/tentang").get_data(as_text=True)
    persen = f"{db.ringkasan()['isl_cakupan_persen']:.1f}".replace(".", ",")
    assert persen in h


# Kaidah penulisan angka

@pytest.mark.parametrize("jalur", HALAMAN_PENJELASAN)
def test_desimal_memakai_koma_bukan_titik(klien, jalur):
    """Kaidah bahasa Indonesia memakai koma sebagai pemisah desimal.

    Titik dipakai sebagai pemisah ribuan, sehingga "2.260" justru benar dan
    tidak boleh ikut tertangkap. Yang dicari adalah titik yang diikuti selain
    tepat tiga angka, sebab kelompok ribuan selalu tepat tiga. Pola itu
    menangkap "80.1" tanpa menyalahkan "2.260".

    Penulisan jam juga memakai titik, misalnya "pukul 17.44", sehingga
    dikecualikan tersendiri.

    Diperiksa pada teks yang terbaca, bukan pada atribut maupun skrip, sebab
    versi berkas dan nomor rilis memang memakai titik.
    """
    h = klien.get(jalur).get_data(as_text=True)
    teks = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", h,
                  flags=re.S)
    teks = re.sub(r"pukul\s+\d{1,2}\.\d{2}", " ", teks)
    salah = re.findall(r"(?<![\w.])\d+\.(?:\d{1,2}|\d{4,})(?![\d.])", teks)
    assert not salah, f"{jalur}: {salah[:5]}"


def test_penapis_angka_membalik_pemisah():
    """Uji langsung penapis Jinja tanpa lewat halaman."""
    from app import app as flask_app
    f = flask_app.jinja_env.filters["angka"]
    assert f(80.1) == "80,1"
    assert f(15743, 0) == "15.743"
    assert f(1024.5) == "1.024,5"
    assert f(None) != ""


# Keutuhan halaman

@pytest.mark.parametrize("jalur", HALAMAN_PENJELASAN)
def test_halaman_penjelasan_terbuka(klien, jalur):
    assert klien.get(jalur).status_code == 200


def test_metodologi_menomori_langkah_tanpa_ganda(klien):
    """Halaman ini pernah memuat dua bagian bernomor 4."""
    h = klien.get("/metodologi").get_data(as_text=True)
    nomor = [int(m) for m in re.findall(r"<h2[^>]*>\s*(\d+)\.", h)]
    assert nomor == sorted(nomor)
    assert len(nomor) == len(set(nomor)), f"nomor ganda: {nomor}"


def test_metodologi_memuat_seluruh_langkah_pipeline(klien):
    """Sebelumnya separuh langkah tidak dijelaskan sama sekali."""
    h = klien.get("/metodologi").get_data(as_text=True)
    for konsep in ["rate", "Min-Max", "Kruskal-Wallis", "celah",
                   "pangsa", "Rasio Konsistensi", "K-Means"]:
        assert konsep in h, konsep


def test_metodologi_menyatakan_golongan_asal_angka(klien):
    """Ketetapan penulis harus dinyatakan terbuka, bukan disamarkan."""
    h = klien.get("/metodologi").get_data(as_text=True)
    assert "Ketetapan penulis" in h
    assert "Turunan" in h


def test_tentang_menyebut_tanggal_pengambilan_data(klien):
    """Seluruh angka terikat satu snapshot, dan itu harus dinyatakan."""
    h = klien.get("/tentang").get_data(as_text=True)
    assert "7 Agustus 2026" in h


def test_tentang_menyebut_keterbatasan_cakupan_isl(klien):
    h = klien.get("/tentang").get_data(as_text=True)
    assert "protein nabati" in h.lower()
    assert "36,4" in h
