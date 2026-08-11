"""
test_api.py: pengujian endpoint JSON.

Fokus pada perilaku validasi: parameter keliru harus menghasilkan 400 atau
404, bukan 200 berisi nol. Kegagalan yang tampak sah adalah yang paling
berbahaya, dan versi sebelumnya melakukan persis itu.
"""

import pytest

import config

from angka_acuan import TOTAL_MENU


# --- endpoint dasar ----------------------------------------------------------
@pytest.mark.parametrize("jalur", [
    "/api/ringkasan", "/api/province-list", "/api/opsi-filter",
    "/api/provinces", "/api/clusters", "/api/menus", "/api/ingredients",
    "/api/akg", "/api/data-mentah", "/api/profil-pangan",
])
def test_endpoint_dasar_200(klien, jalur):
    r = klien.get(jalur)
    assert r.status_code == 200
    assert r.is_json


def test_ringkasan_isi(klien):
    d = klien.get("/api/ringkasan").get_json()
    assert d["total_menu"] == TOTAL_MENU
    assert d["total_provinsi"] == 36


def test_opsi_filter_sinkron_dengan_config(klien):
    d = klien.get("/api/opsi-filter").get_json()
    # Sisi depan dan server harus sepakat soal nilai yang sah.
    assert d["jenjang"] == config.JENJANG_LIST
    assert d["alergen"] == config.ALERGEN_LIST
    assert len(d["provinsi"]) == 36


# --- validasi parameter ------------------------------------------------------
def test_jenjang_salah_400(klien):
    r = klien.get("/api/provinces?jenjang=SMEA")
    assert r.status_code == 400
    assert r.get_json()["parameter"] == "jenjang"


def test_jenjang_kosong_berarti_semua(klien):
    assert klien.get("/api/provinces?jenjang=").status_code == 200


def test_tingkat_salah_400(klien):
    assert klien.get("/api/menus?tingkat=Ekstrem").status_code == 400


def test_provinsi_salah_400(klien):
    r = klien.get("/api/menus?provinsi=Atlantis")
    assert r.status_code == 400
    assert r.get_json()["parameter"] == "provinsi"


def test_provinsi_bentuk_lain_diterima(klien):
    for nama in ["Aceh", "aceh", "Prov. Aceh"]:
        assert klien.get("/api/menus?provinsi=" + nama).status_code == 200


def test_urut_salah_400(klien):
    assert klien.get("/api/recommend?urut=ngawur").status_code == 400


def test_alergen_salah_400(klien):
    assert klien.get("/api/recommend?exclude_alergen=bukanalergen").status_code == 400


def test_batas_bukan_angka_400(klien):
    assert klien.get("/api/recommend?batas=banyak").status_code == 400


# --- menu --------------------------------------------------------------------
def test_menu_detail_200(klien):
    d = klien.get("/api/menu/SD-60000-1").get_json()
    assert d["menu_id"] == "SD-60000-1"
    assert d["bahan"]


def test_menu_tidak_ada_404_json(klien):
    r = klien.get("/api/menu/TIDAK-ADA")
    assert r.status_code == 404
    assert r.is_json and "error" in r.get_json()


def test_menu_id_kepanjangan_404(klien):
    assert klien.get("/api/menu/" + "x" * 60).status_code == 404


def test_province_tidak_ada_404(klien):
    assert klien.get("/api/province/999999").status_code == 404


# --- ISL ---------------------------------------------------------------------
def test_isl_provinsi_200(klien):
    d = klien.get("/api/isl/Aceh").get_json()
    assert d["total_bahan"] > 0
    assert d["provinsi"] == "Aceh"


def test_isl_provinsi_salah_404_bukan_nol(klien):
    # Dulu endpoint ini membalas 200 dengan seluruh nilai nol.
    r = klien.get("/api/isl/Atlantis")
    assert r.status_code == 404


def test_isl_menu_200(klien):
    d = klien.get("/api/isl/Aceh/menu?jenjang=SD").get_json()
    assert d["total_menu"] > 0
    assert d["isl_rata_rata"] is not None


def test_isl_menu_jenjang_salah_400(klien):
    assert klien.get("/api/isl/Aceh/menu?jenjang=XX").status_code == 400


def test_produksi_200(klien):
    d = klien.get("/api/produksi/Aceh?tahun=2024").get_json()
    assert d["total"] > 0


def test_produksi_provinsi_salah_404(klien):
    assert klien.get("/api/produksi/Atlantis").status_code == 404


# --- recommend GET dan POST --------------------------------------------------
def test_recommend_get(klien):
    d = klien.get("/api/recommend?jenjang=SD&batas=5").get_json()
    assert d["ditampilkan"] == 5
    assert all(m["jenjang"] == "SD" for m in d["rekomendasi"])


def test_recommend_post(klien):
    d = klien.post("/api/recommend", json={
        "provinsi": "Bali", "halal_saja": True, "urut": "isl", "batas": 4,
    }).get_json()
    assert all(m["provinsi"] == "Bali" and m["halal"] for m in d["rekomendasi"])


def test_recommend_post_wajib_json(klien):
    r = klien.post("/api/recommend", data="bukan json",
                   content_type="text/plain")
    assert r.status_code == 415


def test_recommend_post_badan_kosong(klien):
    # Badan kosong berarti tanpa penyaring, bukan galat.
    d = klien.post("/api/recommend", json={}).get_json()
    assert d["total_lolos"] == TOTAL_MENU


def test_recommend_daftar_alergen_sebagai_teks_dan_list(klien):
    lewat_teks = klien.get("/api/recommend?exclude_alergen=telur,ikan").get_json()
    lewat_list = klien.post("/api/recommend",
                            json={"exclude_alergen": ["telur", "ikan"]}).get_json()
    assert lewat_teks["total_lolos"] == lewat_list["total_lolos"]


def test_recommend_melaporkan_filter_yang_dipakai(klien):
    d = klien.get("/api/recommend?jenjang=SD&halal_saja=1").get_json()
    assert d["filter"]["jenjang"] == "SD"
    assert d["filter"]["halal_saja"] is True
