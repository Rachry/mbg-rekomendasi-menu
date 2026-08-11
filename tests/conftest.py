"""Perkakas bersama seluruh berkas pengujian."""

import os
import pathlib
import sys

import pytest

# Lingkungan pengujian ditetapkan sebelum `config` diimpor. Tanpa ini,
# FLASK_ENV kosong berarti "production", dan sejak SECRET_KEY diwajibkan di
# produksi, seluruh proses pengujian akan berhenti di baris impor pertama.
# conftest.py dimuat pytest sebelum berkas uji mana pun, jadi ini tempat yang
# tepat untuk menetapkannya.
os.environ.setdefault("FLASK_ENV", "testing")

# Penanda rilis dipatok supaya seluruh proses uji, termasuk yang dijalankan
# paralel, memakai penanda alur yang sama.
os.environ.setdefault("MBG_RILIS", "uji-lokal")

# Folder ini dimasukkan ke jalur impor supaya `angka_acuan` dapat dipakai
# seluruh berkas uji. Angka pokok basis data dikumpulkan di sana agar
# pembaruan data cukup menyunting satu tempat, bukan tujuh berkas.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import app as modul_app
from app import app as flask_app


@pytest.fixture(autouse=True)
def _kosongkan_pembatas_laju():
    """Kosongkan saldo pembatas laju sebelum tiap kasus uji.

    Pembatas laju menyimpan saldo per alamat IP pada satu kamus tingkat modul.
    Kamus itu bertahan sepanjang proses pengujian, sehingga uji yang mengirim
    banyak permintaan menghabiskan jatah uji berikutnya, dan uji berikutnya
    gagal menerima 429 padahal kodenya benar.

    Cacat ini tidak pernah terlihat selama urutan uji tetap, sebab uji yang
    boros kebetulan berjalan paling akhir. Setelah urutan diacak, kegagalan
    muncul pada lima dari lima benih yang dicoba. Mengosongkan saldo di sini
    membuat tiap kasus uji berangkat dari keadaan yang sama, sehingga hasilnya
    tidak lagi bergantung pada urutan.
    """
    modul_app._ember.clear()
    yield
    modul_app._ember.clear()


@pytest.fixture()
def klien():
    """Klien uji yang sudah melewati ketiga langkah gerbang penjelasan.

    Cookie memuat penanda proses yang sedang berjalan, sebab alur penjelasan
    sengaja diulang setiap kali aplikasi dijalankan.
    """
    flask_app.config["TESTING"] = True
    c = flask_app.test_client()
    c.set_cookie("mbg_alur", f"{modul_app.PENANDA_JALAN}:{len(modul_app.ALUR)}")
    return c


@pytest.fixture()
def klien_baru():
    """Klien tanpa penanda alur, untuk menguji gerbang penjelasan."""
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture()
def html():
    """Header yang menandakan permintaan halaman, bukan pengambilan data."""
    return {"Accept": "text/html"}
