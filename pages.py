"""
pages.py
Blueprint halaman: route yang merender template HTML.

Route halaman sengaja tipis. Data dinamis diambil sisi depan lewat endpoint
API (lihat api.py), sehingga halaman cukup mengoper sedikit konteks awal ke
template. Pemisahan ini membuat halaman cepat dimuat dan logikanya mudah
ditelusuri.
"""

from flask import Blueprint, abort, render_template, request

import config
import db

pages = Blueprint("pages", __name__)


# Remah navigasi
# Tiap halaman menyebutkan jalur hierarkinya sendiri, bukan mengandalkan
# tautan kembali yang dipatok ke satu tujuan. Sebelumnya memasang
# "Kembali ke galeri menu" pada halaman menu, sehingga pengunjung yang tiba
# lewat Kelompok Daerah lalu halaman provinsi justru terlempar ke galeri.
#
# Remah menjawab "saya ada di mana", dan tombol kembali di base.html
# menjawab "saya datang dari mana". Keduanya diperlukan karena satu halaman
# dapat dicapai lewat beberapa jalur.

def _remah(*bagian):
    """Bangun daftar remah. Butir terakhir adalah halaman saat ini."""
    return [{"label": lab, "url": url} for lab, url in bagian]


@pages.route("/")
def index():
    """Halaman peta: choropleth, pencarian, dan filter."""
    return render_template(
        "index.html",
        jenjang_list=config.JENJANG_LIST,
        tingkat_list=config.TINGKAT_LIST,
        remah=_remah(("Peta", None)),
    )


@pages.route("/provinsi/<int:kode>")
def provinsi(kode):
    """Halaman detail provinsi, menampilkan keempat jenjang sekaligus."""
    data = db.province_detail(kode)
    if data is None:
        abort(404)
    return render_template(
        "provinsi.html",
        provinsi=data,
        remah=_remah(("Peta", "/"), (data["provinsi"], None)),
    )


@pages.route("/menu")
def menu_galeri():
    """Galeri seluruh menu dengan filter provinsi, jenjang, dan tingkat."""
    return render_template(
        "menu_galeri.html",
        jenjang_list=config.JENJANG_LIST,
        tingkat_list=config.TINGKAT_LIST,
        provinsi_list=[p["nama"] for p in db.daftar_provinsi()],
        remah=_remah(("Peta", "/"), ("Galeri menu", None)),
    )


@pages.route("/menu/<menu_id>")
def menu_detail(menu_id):
    """Halaman detail satu menu. menu_id berbentuk teks, misalnya SD-60000-1."""
    if len(menu_id) > 40:
        abort(404)
    data = db.menu_detail(menu_id)
    if data is None:
        abort(404)
    # Induk hierarki sebuah menu adalah provinsinya, sebab menu disusun
    # per provinsi. Galeri hanyalah salah satu cara menemukannya.
    kode = db.kode_dari_nama(data["provinsi"])
    return render_template(
        "menu_detail.html",
        menu=data,
        ambang_utama=config.AMBANG_LOKAL_UTAMA,
        ambang_sebagian=config.AMBANG_LOKAL_SEBAGIAN,
        remah=_remah(
            ("Peta", "/"),
            (data["provinsi"], f"/provinsi/{kode}" if kode else None),
            (f"Menu {data['jenjang']}", None),
        ),
    )


@pages.route("/cluster")
def cluster():
    """Halaman penjelasan profil kelompok daerah."""
    return render_template(
        "cluster.html",
        jenjang_list=config.JENJANG_LIST,
        remah=_remah(("Peta", "/"), ("Kelompok daerah", None)),
    )


@pages.route("/metodologi")
def metodologi():
    """Halaman penjelasan AHP, K-Means, ISL, dan standar AKG."""
    # Profil kelompok SMP dipakai sebagai contoh terhitung pada langkah 7.
    # Diambil dari basis data, bukan ditulis pada templat, supaya contohnya
    # ikut berubah bila pipeline dijalankan ulang dengan data baru.
    profil = [p for p in db.cluster_profiles(jenjang="SMP")]
    return render_template(
        "metodologi.html",
        akg=db.akg_standards(),
        ringkasan=db.ringkasan(),
        profil_smp=profil,
        remah=_remah(("Peta", "/"), ("Metodologi", None)),
    )


@pages.route("/tentang")
def tentang():
    """Halaman sumber data dan batasan penelitian."""
    return render_template(
        "tentang.html",
        ringkasan=db.ringkasan(),
        remah=_remah(("Peta", "/"), ("Tentang", None)),
    )


@pages.route("/istilah")
def istilah():
    """Daftar singkatan dan istilah teknis, dapat dirujuk kapan saja."""
    kelompok = {}
    for i in config.ISTILAH:
        kelompok.setdefault(i["kelompok"], []).append(i)
    return render_template(
        "istilah.html",
        kelompok=kelompok,
        remah=_remah(("Peta", "/"), ("Daftar istilah", None)),
    )


@pages.route("/data")
def data_mentah():
    """Halaman tabel data mentah, dua tab: profil kesehatan dan produksi pangan.

    Angka jumlah baris dikirim dari sisi server supaya kepala tab sudah
    menampilkan besarnya data sebelum tabelnya sendiri diminta. Isi tab
    produksi baru diambil ketika tabnya benar-benar dibuka.
    """
    return render_template(
        "data.html",
        jenjang_list=config.JENJANG_LIST,
        ringkasan=db.ringkasan(),
        total_produksi=db.produksi_mentah(batas=1)["total"],
        remah=_remah(("Peta", "/"), ("Data mentah", None)),
    )


@pages.route("/produsen")
def produsen():
    """Rincian bahan baku yang diproduksi tiap provinsi.

    Halaman ini menjadi tujuan klik pada lapisan produksi di peta, sehingga
    pengguna melihat komoditas yang diproduksi, bukan daftar menu. Provinsi
    dapat ditentukan lewat query `?provinsi=`; bila kosong, provinsi pertama
    yang dipakai.
    """
    daftar = [p["nama"] for p in db.daftar_provinsi()]
    diminta = request.args.get("provinsi")
    terpilih = daftar[0]
    if diminta:
        kode = db.kode_dari_nama(diminta)
        if kode is None:
            abort(404)
        terpilih = db.nama_dari_kode(kode)

    _, tahun_tersedia = db.kelompok_produksi()
    kode = db.kode_dari_nama(terpilih)
    return render_template(
        "produsen.html",
        provinsi_list=daftar,
        provinsi_terpilih=terpilih,
        tahun_list=list(tahun_tersedia),
        remah=_remah(
            ("Peta", "/"),
            (terpilih, f"/provinsi/{kode}" if kode else None),
            ("Produksi bahan", None),
        ),
    )


@pages.route("/rekomendasi")
def rekomendasi():
    """Halaman rekomendasi interaktif dengan penyaring lengkap."""
    return render_template(
        "rekomendasi.html",
        jenjang_list=config.JENJANG_LIST,
        tingkat_list=config.TINGKAT_LIST,
        provinsi_list=[p["nama"] for p in db.daftar_provinsi()],
        alergen_list=config.ALERGEN_LIST,
        intoleransi_list=config.INTOLERANSI_LIST,
        sumber_karbo=config.SUMBER_KARBO,
        sumber_protein=config.SUMBER_PROTEIN,
        urut_opsi=config.URUT_OPSI,
        # Daftar bahan dikirim sebagai data, bukan dirender menjadi ratusan
        # kotak centang. Pemilih mencarinya di sisi depan, sehingga halaman
        # jauh lebih ringan dan maksud tiap tindakan dapat ditulis eksplisit.
        bahan_ringkas_json=[
            {
                "nama_bahan": b["nama_bahan"],
                "kategori": b["kategori"],
                "alergen": b["alergen"],
                "intoleransi": b["intoleransi"],
                "fobia": b["fobia"],
                "halal": b["halal"],
            }
            for b in db.ingredients_all(hanya_terpakai=True)
        ],
        ringkasan=db.ringkasan(),
        warna_tingkat=config.WARNA_TINGKAT_JSON,
        ambang_fobia=config.AMBANG_FOBIA,
        tingkat_lokal={k: v["label"] for k, v in config.TINGKAT_LOKAL.items()},
        remah=_remah(("Peta", "/"), ("Rekomendasi", None)),
    )
