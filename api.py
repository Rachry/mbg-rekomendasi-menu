"""
api.py
Blueprint API: endpoint JSON baca-saja.

Setiap endpoint tipis: ia mengambil parameter, memvalidasinya, memanggil
fungsi di db.py, lalu mengembalikan JSON. Tidak ada logika data maupun
data mentah yang ditanam di berkas ini, supaya mudah diuji dan dijelaskan
saat sidang.

Aturan validasi yang dipegang seluruh endpoint:
  - Parameter yang dikenal tetapi nilainya salah menghasilkan 400, bukan
    diam-diam diabaikan. Sebelumnya mengembalikan 200 berisi nol
    untuk provinsi yang salah ketik, dan itu jenis kegagalan yang paling
    berbahaya karena tampak sah.
  - Parameter yang tidak diisi berarti "semua", dan itu sah.
  - Seluruh galat pada jalur /api/ dikembalikan sebagai JSON.

Daftar endpoint ada di README.md dan diuji di tests/test_api.py.
"""

import logging

from flask import Blueprint, abort, jsonify, request

import config
import db

api = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger("mbg")


# Pembantu validasi

class ParamSalah(ValueError):
    """Parameter dikenal tetapi nilainya di luar daftar yang sah."""

    # Nilai yang keliru ikut disebut supaya pengguna tahu bagian mana yang
    # salah, tetapi dipangkas lebih dulu. Tanpa pemangkasan, masukan sepanjang
    # seratus ribu huruf digemakan utuh, sehingga penyerang dapat membuat
    # balasan sebesar yang ia mau hanya dengan mengirim permintaan panjang.
    BATAS_GEMA = 80

    def __init__(self, nama, nilai, pilihan=None):
        self.nama = nama
        self.nilai = nilai
        self.pilihan = pilihan
        teks = str(nilai)
        if len(teks) > self.BATAS_GEMA:
            teks = teks[:self.BATAS_GEMA] + "…"
            nilai = teks
        pesan = f"Nilai tidak sah untuk '{nama}': {nilai!r}"
        if pilihan:
            pesan += ". Pilihan: " + ", ".join(str(p) for p in pilihan)
        super().__init__(pesan)


def _pilihan(nilai, daftar, nama):
    """Kembalikan nilai bila sah, None bila kosong, ParamSalah bila keliru."""
    if nilai in (None, ""):
        return None
    if nilai not in daftar:
        raise ParamSalah(nama, nilai, daftar)
    return nilai


def _jenjang(nilai):
    return _pilihan(nilai, config.JENJANG_LIST, "jenjang")


def _tingkat(nilai):
    return _pilihan(nilai, config.TINGKAT_LIST, "tingkat")


def _provinsi(nilai):
    """Normalkan nama provinsi ke bentuk yang dipakai kolom menu_provinsi.prov."""
    if nilai in (None, ""):
        return None
    kode = db.kode_dari_nama(nilai)
    if kode is None:
        raise ParamSalah("provinsi", nilai)
    return db.nama_dari_kode(kode)


def _daftar(nilai, sah, nama, maks=20):
    """Validasi daftar string, misalnya daftar alergen yang dihindari."""
    if not nilai:
        return []
    if isinstance(nilai, str):
        nilai = [p.strip() for p in nilai.split(",") if p.strip()]
    if not isinstance(nilai, list):
        raise ParamSalah(nama, nilai)
    nilai = nilai[:maks]
    if sah is not None:
        salah = [v for v in nilai if v not in sah]
        if salah:
            raise ParamSalah(nama, salah[0], sah)
    return nilai


def _bool(nilai):
    if isinstance(nilai, bool):
        return nilai
    return str(nilai).lower() in ("1", "true", "ya", "on")


@api.errorhandler(ParamSalah)
def _tangani_param_salah(e):
    return jsonify({"error": str(e), "parameter": e.nama}), 400


# Provinsi

@api.route("/provinces")
def api_provinces():
    """Data pewarnaan peta. ?jenjang= opsional."""
    jenjang = _jenjang(request.args.get("jenjang"))
    return jsonify(db.provinces_for_map(jenjang))


@api.route("/province-list")
def api_province_list():
    """Daftar provinsi bermenu, untuk mengisi dropdown penyaring."""
    return jsonify(list(db.daftar_provinsi()))


@api.route("/province/<int:kode>")
def api_province(kode):
    data = db.province_detail(kode)
    if data is None:
        abort(404)
    return jsonify(data)


@api.route("/search")
def api_search():
    q = (request.args.get("q") or "").strip()[:50]
    return jsonify(db.search_provinces(q))


# Kelompok daerah

@api.route("/clusters")
def api_clusters():
    jenjang = _jenjang(request.args.get("jenjang"))
    return jsonify(db.cluster_profiles(jenjang, sertakan_provinsi=bool(jenjang)))


# Menu

@api.route("/menus")
def api_menus():
    """Galeri menu. Penyaring: provinsi, jenjang, tingkat.

    ?batas= membatasi jumlah menu yang dikembalikan. Galeri memakainya untuk
    memuat bertahap: 945 kartu sekaligus berat dirender peramban dan
    muatannya mendekati satu megabita.
    """
    batas = request.args.get("batas")
    if batas:
        try:
            batas = int(batas)
        except ValueError:
            raise ParamSalah("batas", batas)

    hasil = db.menus(
        provinsi=_provinsi(request.args.get("provinsi")),
        jenjang=_jenjang(request.args.get("jenjang")),
        tingkat=_tingkat(request.args.get("tingkat")),
    )
    total = len(hasil)
    if batas:
        hasil = hasil[:batas]
    return jsonify({"total": total, "ditampilkan": len(hasil), "data": hasil})


@api.route("/menu/<menu_id>")
def api_menu(menu_id):
    """Detail satu menu. menu_id berbentuk teks, misalnya SD-60000-1."""
    if len(menu_id) > 40:
        abort(404)
    data = db.menu_detail(menu_id)
    if data is None:
        abort(404)
    return jsonify(data)


@api.route("/ingredients")
def api_ingredients():
    """Daftar bahan beserta penanda alergen, intoleransi, fobia, dan halal.

    ?terpakai=1 membatasi ke bahan yang benar-benar muncul pada menu.
    """
    hanya_terpakai = _bool(request.args.get("terpakai"))
    return jsonify(db.ingredients_all(hanya_terpakai=hanya_terpakai))


@api.route("/akg")
def api_akg():
    return jsonify(db.akg_standards())


@api.route("/data-mentah")
def api_data_mentah():
    jenjang = _jenjang(request.args.get("jenjang"))
    dengan_label = _bool(request.args.get("label"))
    return jsonify(db.provinces_raw(jenjang, dengan_label))


@api.route("/ringkasan")
def api_ringkasan():
    """Angka pokok sistem: jumlah menu, provinsi, bahan, rata-rata ISL."""
    return jsonify(db.ringkasan())


# Rekomendasi

@api.route("/recommend", methods=["GET", "POST"])
def api_recommend():
    """Saring dan urutkan menu.

    GET menerima parameter lewat query string, POST lewat badan JSON.
    Keduanya menerima kunci yang sama:

        provinsi            nama provinsi, kosong berarti semua
        jenjang             SD | SMP | SMA | SMK
        tingkat             Tinggi | Sedang | Rendah
        exclude_alergen     daftar dari config.ALERGEN_LIST
        exclude_intoleransi daftar dari config.INTOLERANSI_LIST
        exclude_bahan       daftar nama bahan yang harus dihindari
        include_bahan       daftar nama bahan yang harus ada pada menu
        include_semua       1 bila seluruh include_bahan harus ada bersamaan;
                            bawaannya cukup salah satu
        tanpa_fobia         1 untuk membuang menu berbahan skor fobia tinggi
        halal_saja          1 untuk membuang menu bertanda non-halal
        sumber_karbo        serealia | umbi | sagu
        sumber_protein      ternak | telur | ikan_laut | ikan_tawar | seafood_lain
        urut                gizi | isl | akg_energi | protein
        batas               jumlah menu yang dikembalikan
    """
    if request.method == "POST":
        if not request.is_json:
            return jsonify({"error": "Content-Type harus application/json"}), 415
        data = request.get_json(silent=True) or {}
        ambil = data.get
    else:
        ambil = request.args.get

    batas = ambil("batas")
    try:
        batas = int(batas) if batas else None
    except (TypeError, ValueError):
        raise ParamSalah("batas", batas)

    hasil = db.recommend(
        provinsi=_provinsi(ambil("provinsi")),
        jenjang=_jenjang(ambil("jenjang")),
        tingkat=_tingkat(ambil("tingkat")),
        exclude_alergen=_daftar(ambil("exclude_alergen"), config.ALERGEN_LIST, "exclude_alergen"),
        exclude_intoleransi=_daftar(ambil("exclude_intoleransi"), config.INTOLERANSI_LIST, "exclude_intoleransi"),
        exclude_bahan=_daftar(ambil("exclude_bahan"), None, "exclude_bahan", maks=40),
        include_bahan=_daftar(ambil("include_bahan"), None, "include_bahan", maks=40),
        include_semua=_bool(ambil("include_semua")),
        tanpa_fobia=_bool(ambil("tanpa_fobia")),
        halal_saja=_bool(ambil("halal_saja")),
        sumber_karbo=_pilihan(ambil("sumber_karbo"), config.SUMBER_KARBO_LIST, "sumber_karbo"),
        sumber_protein=_pilihan(ambil("sumber_protein"), config.SUMBER_PROTEIN_LIST, "sumber_protein"),
        urut=_pilihan(ambil("urut"), list(config.URUT_OPSI), "urut"),
        batas=batas,
    )
    return jsonify(hasil)


@api.route("/opsi-filter")
def api_opsi_filter():
    """Seluruh pilihan penyaring, supaya sisi depan tidak menyalin daftar.

    Menaruh daftar ini di satu tempat mencegah antarmuka dan server
    berbeda pendapat soal nilai apa yang sah.
    """
    return jsonify({
        "jenjang": config.JENJANG_LIST,
        "tingkat": [
            {"nilai": t, "label": config.label_awam(t), "warna": config.warna_tingkat(t)}
            for t in config.TINGKAT_LIST
        ],
        "provinsi": [p["nama"] for p in db.daftar_provinsi()],
        "alergen": config.ALERGEN_LIST,
        "intoleransi": config.INTOLERANSI_LIST,
        "sumber_karbo": [{"nilai": k, "label": v} for k, v in config.SUMBER_KARBO.items()],
        "sumber_protein": [{"nilai": k, "label": v} for k, v in config.SUMBER_PROTEIN.items()],
        "urut": [{"nilai": k, "label": v} for k, v in config.URUT_OPSI.items()],
        "ambang_fobia": config.AMBANG_FOBIA,
        "batas_default": config.BATAS_REKOMENDASI,
    })


# Indeks sumber lokal (isl)

@api.route("/isl/<provinsi>")
def api_isl(provinsi):
    """Nilai ISL tiap bahan di satu provinsi."""
    data = db.isl_provinsi(provinsi)
    if data is None:
        abort(404)
    return jsonify({
        "provinsi": db.nama_dari_kode(db.kode_dari_nama(provinsi)),
        "total_bahan": len(data),
        "keterangan": (
            "Indeks Sumber Lokal bernilai 0 sampai 1, menunjukkan seberapa "
            "besar kebutuhan bahan tersebut dapat dipenuhi produksi provinsi "
            "sendiri. Bahan tanpa data produksi tidak muncul di daftar ini."
        ),
        "data": data,
    })


@api.route("/isl/<provinsi>/menu")
def api_isl_menu(provinsi):
    """Peringkat menu satu provinsi menurut rata-rata ISL bahannya."""
    jenjang = _jenjang(request.args.get("jenjang"))
    data = db.isl_ranking_menu(provinsi, jenjang=jenjang)
    if data is None:
        abort(404)
    berdata = [m["isl"] for m in data if m["isl"] is not None]
    return jsonify({
        "provinsi": db.nama_dari_kode(db.kode_dari_nama(provinsi)),
        "jenjang": jenjang,
        "total_menu": len(data),
        "isl_rata_rata": round(sum(berdata) / len(berdata), 3) if berdata else None,
        "data": data,
    })


@api.route("/produksi-peta")
def api_produksi_peta():
    """Total produksi per provinsi, siap dipakai mewarnai peta.

    Query: ?kelompok=serealia_umbi&tahun=2024
    """
    kelompok, tahun_tersedia = db.kelompok_produksi()
    pilihan_kelompok = _pilihan(request.args.get("kelompok"), list(kelompok), "kelompok")

    tahun = request.args.get("tahun")
    if tahun:
        try:
            tahun = int(tahun)
        except ValueError:
            raise ParamSalah("tahun", tahun)
        if tahun not in tahun_tersedia:
            raise ParamSalah("tahun", tahun, list(tahun_tersedia))

    data = db.produksi_peta(kelompok=pilihan_kelompok, tahun=tahun)
    total = sum(p["total_ton"] for p in data)

    return jsonify({
        "kelompok": pilihan_kelompok,
        "tahun": tahun,
        "kelompok_tersedia": list(kelompok),
        "tahun_tersedia": list(tahun_tersedia),
        "total_provinsi": len(data),
        "total_ton": round(total, 1),
        "maks_ton": data[0]["total_ton"] if data else 0,
        "sumber": "Badan Pusat Statistik (BPS), produksi pangan provinsi 2019-2024",
        "catatan": (
            "Angka merupakan produksi, bukan konsumsi. Provinsi dengan produksi "
            "besar belum tentu mengonsumsinya sendiri, karena sebagian dikirim "
            "ke daerah lain. Angka ditampilkan apa adanya sesuai publikasi resmi "
            "BPS, tanpa penyaringan kewajaran."
        ),
        "data": data,
    })


@api.route("/produksi/<provinsi>/ringkasan")
def api_ringkasan_produksi(provinsi):
    """Angka pokok produksi satu provinsi beserta rinciannya per kelompok."""
    tahun = request.args.get("tahun")
    if tahun:
        try:
            tahun = int(tahun)
        except ValueError:
            raise ParamSalah("tahun", tahun)
    data = db.ringkasan_produksi(provinsi, tahun=tahun)
    if data is None:
        abort(404)
    data["tahun"] = tahun
    return jsonify(data)


@api.route("/produksi/<provinsi>/teratas")
def api_komoditas_teratas(provinsi):
    """Komoditas dengan produksi terbesar di satu provinsi."""
    tahun = request.args.get("tahun")
    if tahun:
        try:
            tahun = int(tahun)
        except ValueError:
            raise ParamSalah("tahun", tahun)
    data = db.komoditas_teratas(provinsi, tahun=tahun)
    if data is None:
        abort(404)
    return jsonify({
        "provinsi": db.nama_dari_kode(db.kode_dari_nama(provinsi)),
        "tahun": tahun,
        "data": data,
    })


@api.route("/profil-pangan")
def api_profil_pangan():
    """Indeks Pola Pangan Wilayah per kelompok pangan."""
    provinsi = request.args.get("provinsi")
    if provinsi:
        _provinsi(provinsi)  # validasi, melempar 400 bila keliru
    return jsonify(db.profil_pangan_provinsi(provinsi))


@api.route("/produksi-mentah")
def api_produksi_mentah():
    """Tabel produksi pangan mentah berpenyaring, dimuat bertahap.

    Melayani tab Produksi Pangan pada halaman data mentah. Berbeda dari
    `/api/produksi/<provinsi>` yang selalu terikat satu provinsi, alamat ini
    boleh menampilkan seluruh provinsi sekaligus, karena itu jumlah barisnya
    dibatasi dan disertai penghitung total.

    Query: ?provinsi=&kelompok=&komoditas=&tahun=&batas=&offset=
    """
    opsi = db.opsi_produksi()

    provinsi = request.args.get("provinsi") or None
    if provinsi:
        kunci_sah = {p["kunci"] for p in opsi["provinsi"]}
        if config.kunci_provinsi(provinsi) not in kunci_sah:
            raise ParamSalah("provinsi", provinsi)

    kelompok = _pilihan(request.args.get("kelompok"), opsi["kelompok"], "kelompok")
    komoditas = _pilihan(request.args.get("komoditas"), opsi["komoditas"], "komoditas")

    tahun = request.args.get("tahun")
    if tahun:
        try:
            tahun = int(tahun)
        except ValueError:
            raise ParamSalah("tahun", tahun)
        if tahun not in opsi["tahun"]:
            raise ParamSalah("tahun", tahun, opsi["tahun"])

    def _angka_positif(nama, baku):
        mentah = request.args.get(nama)
        if mentah is None or mentah == "":
            return baku
        try:
            nilai = int(mentah)
        except ValueError:
            raise ParamSalah(nama, mentah)
        if nilai < 0:
            raise ParamSalah(nama, mentah)
        return nilai

    batas = _angka_positif("batas", db.PRODUKSI_BATAS_BAKU)
    offset = _angka_positif("offset", 0)

    hasil = db.produksi_mentah(
        provinsi=provinsi, kelompok=kelompok, komoditas=komoditas,
        tahun=tahun, batas=batas, offset=offset,
    )
    hasil["penyaring"] = {
        "provinsi": provinsi, "kelompok": kelompok,
        "komoditas": komoditas, "tahun": tahun,
    }
    hasil["sumber"] = (
        "Badan Pusat Statistik dan Kementerian Pertanian, dihimpun dari 100 "
        "berkas publikasi produksi pangan provinsi"
    )
    hasil["catatan"] = (
        "Angka merupakan produksi, bukan konsumsi. Data ditampilkan apa adanya "
        "tanpa penyaringan kewajaran. Baris yang tidak muncul berarti komoditas "
        "tersebut tidak tercatat pada provinsi bersangkutan, berbeda dari nilai "
        "nol yang berarti tercatat tidak berproduksi."
    )
    return jsonify(hasil)


@api.route("/opsi-produksi")
def api_opsi_produksi():
    """Pilihan penyaring tabel produksi mentah, diambil dari isi tabel."""
    return jsonify(db.opsi_produksi())


@api.route("/produksi/<provinsi>")
def api_produksi(provinsi):
    """Data produksi pangan mentah, untuk menelusuri asal angka ISL."""
    tahun = request.args.get("tahun")
    if tahun:
        try:
            tahun = int(tahun)
        except ValueError:
            raise ParamSalah("tahun", tahun)
    data = db.produksi_provinsi(provinsi, tahun=tahun)
    if data is None:
        abort(404)
    return jsonify({
        "provinsi": db.nama_dari_kode(db.kode_dari_nama(provinsi)),
        "tahun": tahun,
        "total": len(data),
        "sumber": "Badan Pusat Statistik, produksi pangan provinsi 2020-2024",
        "data": data,
    })
