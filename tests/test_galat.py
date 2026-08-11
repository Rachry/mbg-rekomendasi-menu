"""
test_galat.py: pengujian jalur kegagalan.

Bagian ini sengaja dipisah karena jalur galat justru yang paling jarang
dijalankan tetapi paling merugikan bila rusak. Cacat 500.html yang kosong
pada versi sebelumnya lolos persis karena tidak ada pengujian yang pernah
memicunya.
"""

import sqlite3

import pytest

import api
import app as modul_app
import config
import db

from angka_acuan import TOTAL_MENU


# --- halaman yang memanggil abort(404) --------------------------------------
def test_provinsi_tidak_ada_404(klien):
    assert klien.get("/provinsi/999999").status_code == 404


def test_menu_tidak_ada_404(klien):
    assert klien.get("/menu/TIDAK-ADA-99").status_code == 404


def test_menu_id_kepanjangan_404(klien):
    assert klien.get("/menu/" + "z" * 60).status_code == 404


# --- ParamSalah --------------------------------------------------------------
def test_param_salah_menyertakan_pilihan():
    e = api.ParamSalah("jenjang", "SMEA", ["SD", "SMP"])
    assert "SMEA" in str(e)
    assert "SD" in str(e)


def test_param_salah_tanpa_pilihan():
    e = api.ParamSalah("provinsi", "Atlantis")
    assert "Atlantis" in str(e)
    assert e.nama == "provinsi"


def test_daftar_bukan_list_ditolak(klien):
    r = klien.post("/api/recommend", json={"exclude_alergen": {"a": 1}})
    assert r.status_code == 400


def test_daftar_dipangkas_pada_batas_maksimum():
    hasil = api._daftar(["x"] * 100, None, "exclude_bahan", maks=40)
    assert len(hasil) == 40


def test_bool_menerima_beragam_bentuk():
    assert api._bool("1") and api._bool("true") and api._bool("ya")
    assert api._bool(True)
    assert not api._bool("0") and not api._bool(None) and not api._bool("")


def test_pilihan_kosong_berarti_none():
    assert api._pilihan("", ["a"], "x") is None
    assert api._pilihan(None, ["a"], "x") is None


def test_tahun_bukan_angka_400(klien):
    assert klien.get("/api/produksi/Aceh?tahun=kemarin").status_code == 400


def test_profil_pangan_provinsi_salah_400(klien):
    assert klien.get("/api/profil-pangan?provinsi=Atlantis").status_code == 400


def test_profil_pangan_provinsi_valid(klien):
    d = klien.get("/api/profil-pangan?provinsi=Aceh").get_json()
    assert len(d) == 1


# --- penangan galat aplikasi -------------------------------------------------
def test_galat_server_merender_halaman(klien, monkeypatch):
    """500 pada halaman harus menghasilkan HTML berisi, bukan layar putih."""
    def meledak():
        raise RuntimeError("kegagalan buatan")

    monkeypatch.setattr(db, "ringkasan", meledak)
    modul_app.app.config["PROPAGATE_EXCEPTIONS"] = False
    r = klien.get("/tentang")
    modul_app.app.config["PROPAGATE_EXCEPTIONS"] = None
    assert r.status_code == 500
    isi = r.get_data(as_text=True)
    assert len(isi) > 200
    assert "kegagalan buatan" not in isi        # traceback tidak boleh bocor


def test_galat_server_pada_api_mengembalikan_json(klien, monkeypatch):
    def meledak(*a, **k):
        raise RuntimeError("kegagalan buatan")

    monkeypatch.setattr(db, "recommend", meledak)
    modul_app.app.config["PROPAGATE_EXCEPTIONS"] = False
    r = klien.get("/api/recommend")
    modul_app.app.config["PROPAGATE_EXCEPTIONS"] = None
    assert r.status_code == 500
    assert r.is_json
    assert "kegagalan buatan" not in r.get_data(as_text=True)


def test_galat_basis_data_ditangani(klien, monkeypatch):
    def meledak(*a, **k):
        raise sqlite3.OperationalError("basis data terkunci")

    monkeypatch.setattr(db, "menus", meledak)
    modul_app.app.config["PROPAGATE_EXCEPTIONS"] = False
    r = klien.get("/api/menus")
    modul_app.app.config["PROPAGATE_EXCEPTIONS"] = None
    assert r.status_code == 500
    assert r.is_json
    assert "terkunci" not in r.get_data(as_text=True)


def test_health_melaporkan_degraded(klien, monkeypatch):
    def meledak():
        raise sqlite3.OperationalError("tidak bisa dibaca")

    monkeypatch.setattr(db, "ringkasan", meledak)
    r = klien.get("/health")
    assert r.status_code == 503
    assert r.get_json()["status"] == "degraded"


def test_400_pada_halaman_html(klien):
    r = klien.get("/provinsi/bukan-angka")
    assert r.status_code == 404      # konverter <int:> menolak lebih dulu


# --- basis data hilang -------------------------------------------------------
def test_create_app_menolak_tanpa_basis_data(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "tidak-ada.db"))
    with pytest.raises(FileNotFoundError):
        modul_app.create_app()


# --- utilitas cache ----------------------------------------------------------
def test_bersihkan_cache_mengosongkan_semua():
    db.penanda_bahan()
    db.daftar_provinsi()
    db.total_menu()
    db._bersihkan_cache()
    assert db.penanda_bahan.cache_info().currsize == 0
    assert db.total_menu.cache_info().currsize == 0
    # Setelah dikosongkan, pemanggilan berikutnya tetap benar.
    assert db.total_menu() == TOTAL_MENU


def test_pragma_tidak_meledak_pada_koneksi_readonly():
    # Seluruh PRAGMA dibungkus try: mode read-only menolak sebagian di antaranya.
    with db._connect() as con:
        db._pragma(con)
        assert con.execute("SELECT 1").fetchone()[0] == 1


def test_menus_dengan_batas():
    assert len(db.menus(batas=7)) == 7


def test_menu_ada():
    assert db.menu_ada("SD-60000-1") is True
    assert db.menu_ada("TIDAK-ADA") is False


def test_produksi_tanpa_tahun():
    hasil = db.produksi_provinsi("Aceh")
    assert hasil and len(hasil) <= 200


def test_profil_pangan_semua_provinsi():
    assert len(db.profil_pangan_provinsi()) == 38


def test_pesan_galat_tidak_menggemakan_masukan_panjang(klien):
    """Masukan panjang tidak boleh digemakan utuh pada pesan galat.

    Tanpa pemangkasan, permintaan sepanjang seratus ribu huruf menghasilkan
    balasan sepanjang seratus ribu huruf pula, sehingga penyerang dapat
    memperbesar muatan balasan sekehendaknya hanya dengan mengirim parameter
    panjang. Nilainya tetap disebut, tetapi dipangkas.
    """
    for n in (5_000, 100_000):
        r = klien.get("/api/produksi-mentah?provinsi=" + "A" * n)
        assert r.status_code == 400
        assert len(r.get_data(as_text=True)) < 500, f"balasan membengkak pada n={n}"


def test_pesan_galat_tetap_menyebut_nilai_pendek(klien):
    """Pemangkasan tidak boleh menghilangkan kegunaan pesannya."""
    r = klien.get("/api/produksi-mentah?provinsi=Wakanda")
    assert r.status_code == 400
    d = r.get_json()
    assert "Wakanda" in d["error"]
    assert d["parameter"] == "provinsi"


def test_balasan_galat_bertipe_json_dan_nosniff(klien):
    """Nilai keliru yang digemakan aman sebab tidak pernah ditafsirkan HTML."""
    r = klien.get("/api/produksi-mentah?provinsi=%3Cscript%3Ealert(1)%3C/script%3E")
    assert r.status_code == 400
    assert r.headers["Content-Type"].startswith("application/json")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
