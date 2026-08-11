"""
test_config.py: pengujian kotak putih untuk config.py.

Menyasar tiap cabang: pemetaan label, pemilihan tingkat tertinggi, dan
normalisasi nama provinsi yang menjadi sumber banyak bug pada versi lama.
"""

import config


# --- label_awam: seluruh cabang ---------------------------------------------
def test_label_awam_tiap_tingkat():
    assert config.label_awam("Tinggi") == "Perlu sangat hati-hati"
    assert config.label_awam("Sedang") == "Perlu hati-hati"
    assert config.label_awam("Rendah") == "Relatif aman"


def test_label_awam_kosong_dan_asing():
    assert config.label_awam(None) == config.LABEL_KOSONG
    assert config.label_awam("") == config.LABEL_KOSONG
    # Cabang fallback: label asing dikembalikan apa adanya.
    assert config.label_awam("Ekstrem") == "Ekstrem"


# --- warna_tingkat -----------------------------------------------------------
def test_warna_tingkat():
    assert config.warna_tingkat("Tinggi") == config.WARNA_TINGKAT["Tinggi"]
    assert config.warna_tingkat("Rendah") == config.WARNA_TINGKAT["Rendah"]
    assert config.warna_tingkat(None) == config.WARNA_TINGKAT[None]
    assert config.warna_tingkat("xyz") == config.WARNA_TINGKAT[None]


def test_warna_json_tanpa_kunci_none():
    # Kunci None tidak boleh ikut, karena dipakai langsung sebagai JSON.
    assert None not in config.WARNA_TINGKAT_JSON
    assert set(config.WARNA_TINGKAT_JSON) == set(config.TINGKAT_LIST)


# --- tingkat_tertinggi: prioritas dan cabang kosong --------------------------
def test_tertinggi_kosong():
    assert config.tingkat_tertinggi([]) is None
    assert config.tingkat_tertinggi([None, None]) is None


def test_tertinggi_prioritas():
    assert config.tingkat_tertinggi(["Rendah", "Sedang", "Tinggi"]) == "Tinggi"
    assert config.tingkat_tertinggi(["Rendah", "Sedang"]) == "Sedang"
    assert config.tingkat_tertinggi(["Rendah"]) == "Rendah"
    assert config.tingkat_tertinggi([None, "Sedang", None]) == "Sedang"


def test_tertinggi_label_asing_jatuh_ke_none():
    assert config.tingkat_tertinggi(["xyz", "abc"]) is None


# --- normalisasi nama provinsi ----------------------------------------------
def test_nama_provinsi_buang_awalan():
    assert config.nama_provinsi("Prov. Aceh") == "Aceh"
    assert config.nama_provinsi("Aceh") == "Aceh"
    assert config.nama_provinsi(None) == ""
    assert config.nama_provinsi("") == ""


def test_kunci_provinsi_menyamakan_tiga_bentuk():
    # Tiga bentuk penulisan yang sama harus menghasilkan satu kunci.
    assert config.kunci_provinsi("Prov. D.K.I. Jakarta") == "dki jakarta"
    assert config.kunci_provinsi("D.K.I. Jakarta") == "dki jakarta"
    assert config.kunci_provinsi("dki jakarta") == "dki jakarta"
    # Titik pada singkatan provinsi inilah yang dulu membuat dua provinsi
    # gagal dicocokkan ke tabel ketersediaan lokal.
    assert config.kunci_provinsi("Prov. D.I. Yogyakarta") == "di yogyakarta"
    assert config.kunci_provinsi(None) == ""


def test_daftar_konstanta_konsisten():
    assert set(config.LABEL_AWAM) == set(config.TINGKAT_LIST)
    assert len(config.ALERGEN_LIST) == len(config.KOLOM_ALERGEN)
    assert len(config.INTOLERANSI_LIST) == len(config.KOLOM_INTOLERANSI)
    assert config.URUT_DEFAULT in config.URUT_OPSI
