"""
test_notebook_mandiri.py: notebook harus dapat berjalan sendiri di Colab.

Sel P8 dan P10 sempat memakai `from P8_konsolidasi_produksi import ...`. Cara
itu gagal di Colab karena berkas modulnya hanya ada di komputer lokal dan tidak
ikut tersalin ke Drive, sehingga pipeline berhenti dengan ModuleNotFoundError.

Pengujian di bawah mengunci dua hal. Pertama, tidak ada sel yang mengimpor
modul yang harus diunggah terpisah. Kedua, isi sel tetap selaras dengan berkas
.py kembarannya yang dipakai untuk pengujian, supaya keduanya tidak menyimpang
diam-diam saat salah satunya disunting.
"""

import ast
import json
import pathlib
import re
import subprocess
import sys

import pytest

def _cari_akar():
    """Telusuri ke atas sampai menemukan folder yang memuat `03_notebook`.

    Sebelumnya memakai `parents[4]`, yang mengunci pengujian ini pada
    satu kedalaman folder tertentu. Begitu kode disalin ke folder kerja yang
    lebih dangkal, atau di-checkout CI sebagai akar repo, baris itu melempar
    IndexError saat pengumpulan berkas uji. Galatnya terjadi sebelum `skipif`
    sempat bekerja, sehingga satu berkas yang seharusnya dilewati justru
    menggagalkan seluruh proses pengujian.
    """
    for induk in pathlib.Path(__file__).resolve().parents:
        if (induk / "03_notebook").is_dir():
            return induk
    return None


AKAR = _cari_akar()
NB_DIR = (AKAR / "03_notebook") if AKAR else pathlib.Path("03_notebook_tidak_ada")
NOTEBOOK = NB_DIR / "Pipeline_Menu_Provinsi.ipynb"

pytestmark = pytest.mark.skipif(
    not NOTEBOOK.exists(), reason="notebook tidak tersedia pada pemeriksaan ini")


def _sel_kode():
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return [("".join(c["source"]), i)
            for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code"]


def test_tidak_mengimpor_modul_lokal():
    """Notebook tidak boleh bergantung pada berkas .py yang harus diunggah."""
    terlarang = re.compile(r"^\s*(from|import)\s+(P8_konsolidasi_produksi|P10_agregat)\b",
                           re.M)
    for s, i in _sel_kode():
        assert not terlarang.search(s), (
            f"Sel {i} mengimpor modul lokal. Sel harus mandiri, sebab berkas .py "
            f"tidak ikut tersalin ke Google Drive dan pipeline akan berhenti "
            f"dengan ModuleNotFoundError di Colab."
        )


def test_sel_selaras_dengan_berkas_py():
    """Sel notebook dan berkas .py kembarannya harus persis sama isinya."""
    skrip = NB_DIR / "sinkron_sel_notebook.py"
    if not skrip.exists():
        pytest.skip("penyalin sel tidak tersedia")
    hasil = subprocess.run([sys.executable, str(skrip), "--periksa"],
                           capture_output=True, text=True)
    assert hasil.returncode == 0, (
        f"Sel notebook tidak selaras dengan berkas .py.\n{hasil.stdout}{hasil.stderr}\n"
        f"Jalankan: python 03_notebook/sinkron_sel_notebook.py"
    )


def test_tidak_ada_tanggal_ditulis_tangan():
    """Nama berkas keluaran ML tidak boleh dipatok pada tanggal tertentu.

    Memakai tanggal tetap membuat pipeline membaca keluaran lama begitu notebook
    ML dijalankan ulang, lalu salah menuduh masukannya basi.
    """
    for s, i in _sel_kode():
        assert not re.search(r"mbg_analysis_corrected_\d{8}\.csv", s), (
            f"Sel {i} memuat nama berkas bertanggal tetap. Pilih berkas terbaru "
            f"secara otomatis berdasarkan date_pull di dalam berkas."
        )


def test_seluruh_sel_kode_sah_secara_sintaks():
    for s, i in _sel_kode():
        # baris sihir Jupyter seperti %cd bukan Python murni, jadi dilewati
        bersih = "\n".join(
            (re.match(r"(\s*)", l).group(1) + "pass") if re.match(r"\s*[%!]", l) else l
            for l in s.split("\n"))
        try:
            ast.parse(bersih)
        except SyntaxError as e:
            pytest.fail(f"Sel {i} tidak sah secara sintaks: {e}")
