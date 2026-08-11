"""
db.py
Lapisan akses basis data, baca saja.

Semua interaksi dengan SQLite dikumpulkan di sini supaya modul route tidak
menulis SQL langsung. Basis data dibuka dengan mode read-only (uri mode=ro)
agar web tidak mungkin mengubah hasil pipeline, sesuai batasan SRS.

Skema per-provinsi (pipeline 10 Agustus 2026):
    provinces                 130 baris, 36 provinsi x 4 jenjang
    menu_provinsi             945 menu, satu baris per menu
    menu_provinsi_komposisi   5.561 baris bahan penyusun menu
    ingredient_locality       4.522 baris Indeks Sumber Lokal per provinsi
    ingredients               119 bahan beserta penanda alergen dan halal
    cluster_profiles          12 profil kelompok (4 jenjang x 3 tingkat)
    akg_standards             4 baris standar AKG per jenjang
    province_food_profile     38 baris Indeks Pola Pangan Wilayah
    produksi_pangan           15.743 baris produksi, 38 provinsi, 2019-2025

Tabel agregat (awalan `agg_`) berisi angka turunan yang sudah dihitung sel P10
pipeline. Aplikasi membacanya apa adanya dan tidak menghitung apa pun pada
jalur normal:

    agg_produksi_peta         total produksi per provinsi, tiap kelompok x tahun
    agg_produksi_ringkasan    angka pokok produksi satu provinsi
    agg_produksi_kelompok     rincian produksi per kelompok pangan
    agg_produksi_komoditas    produksi per komoditas per provinsi
    agg_isl_ranking           rata-rata Indeks Sumber Lokal tiap menu
    agg_provinsi_menu         jumlah menu per provinsi, jenjang, tingkat
    agg_provinsi_isl          rata-rata Indeks Sumber Lokal per jenjang
    agg_ringkasan             angka pokok untuk halaman metodologi
    meta_agregat              cap versi data, penanda tabel agregat masih segar

Catatan tentang ISL. Kolom `pangsa_lokal` pada tabel komposisi sudah berisi
nilai ISL bahan tersebut di provinsi tersebut, dihitung pipeline. Nilainya
NULL untuk bahan yang tidak punya data produksi (1.106 dari 5.561 baris).
ISL tingkat menu di sini dihitung sebagai rata-rata nilai yang tidak NULL,
dan jumlah bahan yang punya data selalu ikut dilaporkan supaya pembaca tahu
seberapa kuat dasar angka itu.

Fungsi di sini mengembalikan struktur Python biasa (list of dict) sehingga
modul API tinggal mengubahnya menjadi JSON, dan modul halaman tinggal
mengoper ke template.
"""

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from functools import lru_cache

import config

# Pembulatan angka produksi. Tabel agregat menyimpan hasil penjumlahan yang
# dilakukan pipeline dengan pandas, sedangkan jalur cadangan menjumlahkan lewat
# SUM() milik SQLite. Sejak SQLite 3.45 fungsi SUM() memakai penjumlahan
# Kahan-Babuska yang lebih teliti, sehingga kedua jalur dapat berbeda pada digit
# terakhir, misalnya 368535.22 berbanding 368535.22000000003.
#
# Selisih sebesar itu tidak berarti apa pun untuk tonase pangan, tetapi membuat
# kedua jalur mengembalikan angka yang tidak persis sama, dan pada kasus tertentu
# ikut menggeser urutan hasil. Karena itu seluruh angka produksi dibulatkan pada
# satu tempat, yaitu saat dikembalikan, sehingga hasilnya tidak bergantung pada
# versi SQLite yang terpasang di mesin mana pun.
DESIMAL_TON = 2         # ketelitian angka produksi dalam ton
DESIMAL_ISL = 3         # ketelitian Indeks Sumber Lokal


def _bulat(nilai, desimal):
    """Bulatkan bila angka, kembalikan apa adanya bila kosong."""
    return None if nilai is None else round(float(nilai), desimal)

log = logging.getLogger("mbg")


def _pragma(con):
    """Terapkan pragma; lewati yang butuh akses tulis pada koneksi read-only."""
    for perintah in (
        f"PRAGMA journal_mode = {config.DB_JOURNAL_MODE}",
        f"PRAGMA busy_timeout = {config.DB_TIMEOUT_MS}",
        f"PRAGMA cache_size = {config.DB_CACHE_SIZE_KB}",
        "PRAGMA foreign_keys = ON",
    ):
        try:
            con.execute(perintah)
        except sqlite3.OperationalError:
            pass


@contextmanager
def _connect():
    """Buka koneksi SQLite baca-saja dengan auto-close."""
    uri = f"file:{config.DB_PATH}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    _pragma(con)
    try:
        yield con
    finally:
        con.close()


def _rows(cur):
    """Ubah hasil cursor menjadi list of dict agar mudah diserialkan ke JSON."""
    return [dict(r) for r in cur.fetchall()]


def _bersihkan_cache():
    """Kosongkan seluruh cache modul. Dipakai pengujian setelah ganti DB."""
    for fn in (penanda_bahan, daftar_provinsi, _peta_kode_provinsi,
               _bahan_terpakai_beku, total_menu, kelompok_produksi):
        fn.cache_clear()


# Bahan dan penandanya

@lru_cache(maxsize=1)
def penanda_bahan():
    """Kamus nama_bahan -> penanda alergen, intoleransi, fobia, halal, gizi.

    Basis data dibuka read-only dan isinya tidak berubah selama proses hidup,
    jadi hasilnya di-cache. Sebelumnya membaca ulang seluruh tabel
    bahan pada setiap permintaan dan membuka koneksi kedua tiap kali.
    """
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM ingredients")
        baris = _rows(cur)

    kamus = {}
    for b in baris:
        alergen = [nama for kol, nama in config.KOLOM_ALERGEN.items() if b.get(kol) == 1]
        intoleransi = [nama for kol, nama in config.KOLOM_INTOLERANSI.items() if b.get(kol) == 1]
        skor_fobia = b.get("skor_fobia") or 0.0
        status_halal = b.get("status_halal") or "halal"
        kamus[b["nama_bahan"]] = {
            "nama_bahan": b["nama_bahan"],
            "kategori": b.get("kategori"),
            "subkelompok": b.get("subkelompok"),
            "alergen": alergen,
            "intoleransi": intoleransi,
            "skor_fobia": round(skor_fobia, 4),
            "fobia": skor_fobia > config.AMBANG_FOBIA,
            "status_halal": status_halal,
            "halal": status_halal == "halal",
            "skor_gizi": b.get("skor_gizi"),
            "skor_risiko_bahan": b.get("skor_risiko_bahan"),
        }
    return kamus


def ingredients_all(hanya_terpakai=False):
    """Seluruh bahan beserta penandanya, diurutkan menurut nama.

    hanya_terpakai=True membatasi ke 94 bahan yang benar-benar muncul pada
    menu. Sisanya (bumbu, camilan, susu) ada di basis data sebagai pelengkap
    penanda alergen dan tidak pernah menjadi komponen menu.
    """
    markers = penanda_bahan()
    terpakai = bahan_terpakai() if hanya_terpakai else None

    hasil = [
        dict(m, skor_fobia=round(m["skor_fobia"], 3))
        for nama, m in markers.items()
        if terpakai is None or nama in terpakai
    ]
    hasil.sort(key=lambda x: x["nama_bahan"])
    return hasil


@lru_cache(maxsize=1)
def _bahan_terpakai_beku():
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT DISTINCT nama_bahan FROM menu_provinsi_komposisi")
        return frozenset(r["nama_bahan"] for r in cur.fetchall())


def bahan_terpakai():
    """Himpunan nama bahan yang benar-benar dipakai minimal satu menu."""
    return _bahan_terpakai_beku()


# Provinsi

@lru_cache(maxsize=1)
def _peta_kode_provinsi():
    """Dua arah: kode_prov -> nama bersih, dan nama bersih -> kode_prov."""
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT DISTINCT kode_prov, provinsi FROM provinces ORDER BY provinsi")
        baris = _rows(cur)
    ke_nama = {b["kode_prov"]: config.nama_provinsi(b["provinsi"]) for b in baris}
    ke_kode = {config.kunci_provinsi(b["provinsi"]): b["kode_prov"] for b in baris}
    return ke_nama, ke_kode


def kode_dari_nama(nama):
    """Cari kode provinsi dari nama dalam bentuk apa pun. None bila tak ada."""
    _, ke_kode = _peta_kode_provinsi()
    return ke_kode.get(config.kunci_provinsi(nama))


def nama_dari_kode(kode):
    ke_nama, _ = _peta_kode_provinsi()
    return ke_nama.get(kode)


@lru_cache(maxsize=1)
def daftar_provinsi():
    """Daftar provinsi yang punya menu, siap dipakai isi dropdown."""
    with _connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT DISTINCT provinsi, prov FROM menu_provinsi ORDER BY prov"
        )
        baris = _rows(cur)
    _, ke_kode = _peta_kode_provinsi()
    return tuple(
        {
            "nama": b["prov"],
            "nama_db": b["provinsi"],
            "kode_prov": ke_kode.get(config.kunci_provinsi(b["prov"])),
        }
        for b in baris
    )


def provinsi_valid(nama):
    """True bila nama provinsi dikenali, apa pun bentuk penulisannya."""
    return kode_dari_nama(nama) is not None


def provinces_for_map(jenjang=None):
    """Data pewarnaan peta. Tanpa jenjang, dipakai tingkat paling waspada."""
    with _connect() as con:
        cur = con.cursor()
        if jenjang:
            cur.execute(
                "SELECT kode_prov, provinsi, label_risiko FROM provinces WHERE jenjang = ?",
                (jenjang,),
            )
            baris = _rows(cur)
            return [
                {
                    "kode_prov": b["kode_prov"],
                    "provinsi": config.nama_provinsi(b["provinsi"]),
                    "tingkat": b["label_risiko"],
                    "label_awam": config.label_awam(b["label_risiko"]),
                    "warna": config.warna_tingkat(b["label_risiko"]),
                }
                for b in baris
            ]

        cur.execute("SELECT kode_prov, provinsi, jenjang, label_risiko FROM provinces")
        baris = _rows(cur)

    per_prov = {}
    for b in baris:
        kode = b["kode_prov"]
        if kode not in per_prov:
            per_prov[kode] = {
                "provinsi": config.nama_provinsi(b["provinsi"]),
                "tingkat_semua": [],
            }
        per_prov[kode]["tingkat_semua"].append(b["label_risiko"])

    hasil = []
    for kode, data in per_prov.items():
        tertinggi = config.tingkat_tertinggi(data["tingkat_semua"])
        hasil.append({
            "kode_prov": kode,
            "provinsi": data["provinsi"],
            "tingkat": tertinggi,
            "label_awam": config.label_awam(tertinggi),
            "warna": config.warna_tingkat(tertinggi),
        })
    return hasil


def province_detail(kode_prov):
    """Detail satu provinsi untuk keempat jenjang sekaligus."""
    with _connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT kode_prov, provinsi, jenjang, cluster, label_risiko, "
            "       rate_alergi, rate_intoleransi, rate_fobia, "
            "       jumlah_penerima_manfaat, is_imputed, weighted_score "
            "FROM provinces WHERE kode_prov = ?",
            (kode_prov,),
        )
        baris = _rows(cur)
        if not baris:
            return None

        nama_db = baris[0]["provinsi"]

        # Jumlah menu dan rata-rata ISL per jenjang, dibaca dari tabel agregat
        # hasil pipeline, dengan cadangan hitung ulang.
        if agregat_siap():
            cur.execute(
                "SELECT jenjang, tingkat_kewaspadaan, n_menu AS n "
                "FROM agg_provinsi_menu WHERE provinsi = ?", (nama_db,),
            )
            jumlah_menu = {(r["jenjang"], r["tingkat_kewaspadaan"]): r["n"]
                           for r in cur.fetchall()}
            cur.execute(
                "SELECT jenjang, isl FROM agg_provinsi_isl WHERE provinsi = ?",
                (nama_db,),
            )
            isl_per_jenjang = {r["jenjang"]: r["isl"] for r in cur.fetchall()}
        else:
            cur.execute(
                "SELECT jenjang, tingkat_kewaspadaan, COUNT(*) AS n "
                "FROM menu_provinsi WHERE provinsi = ? GROUP BY jenjang, tingkat_kewaspadaan",
                (nama_db,),
            )
            jumlah_menu = {(r["jenjang"], r["tingkat_kewaspadaan"]): r["n"]
                           for r in cur.fetchall()}
            cur.execute(
                "SELECT m.jenjang, AVG(k.pangsa_lokal) AS isl "
                "FROM menu_provinsi m JOIN menu_provinsi_komposisi k ON k.menu_id = m.menu_id "
                "WHERE m.provinsi = ? AND k.pangsa_lokal IS NOT NULL "
                "GROUP BY m.jenjang",
                (nama_db,),
            )
            isl_per_jenjang = {r["jenjang"]: r["isl"] for r in cur.fetchall()}

    per_jenjang = {b["jenjang"]: b for b in baris}
    jenjang_detail = []
    for jen in config.JENJANG_LIST:
        if jen in per_jenjang:
            b = per_jenjang[jen]
            tingkat = b["label_risiko"]
            isl = isl_per_jenjang.get(jen)
            jenjang_detail.append({
                "jenjang": jen,
                "tersedia": True,
                "tingkat": tingkat,
                "label_awam": config.label_awam(tingkat),
                "warna": config.warna_tingkat(tingkat),
                "jumlah_menu": jumlah_menu.get((jen, tingkat), 0),
                "rate_alergi": b["rate_alergi"],
                "rate_intoleransi": b["rate_intoleransi"],
                "rate_fobia": b["rate_fobia"],
                "weighted_score": b["weighted_score"],
                "isl_rata": round(isl, 3) if isl is not None else None,
                "is_imputed": bool(b["is_imputed"]),
            })
        else:
            jenjang_detail.append({
                "jenjang": jen,
                "tersedia": False,
                "tingkat": None,
                "label_awam": config.LABEL_KOSONG,
                "warna": config.warna_tingkat(None),
                "jumlah_menu": 0,
                "isl_rata": None,
            })

    return {
        "kode_prov": kode_prov,
        "provinsi": config.nama_provinsi(nama_db),
        "jenjang": jenjang_detail,
    }


def search_provinces(q):
    """Cari provinsi menurut potongan nama. Karakter wildcard dinetralkan."""
    if not q:
        return []
    # Netralkan % dan _ supaya masukan pengguna tidak menjadi wildcard LIKE.
    aman = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with _connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT DISTINCT kode_prov, provinsi FROM provinces "
            "WHERE provinsi LIKE ? ESCAPE '\\' ORDER BY provinsi LIMIT 10",
            (f"%{aman}%",),
        )
        baris = _rows(cur)
    return [
        {"kode_prov": b["kode_prov"], "provinsi": config.nama_provinsi(b["provinsi"])}
        for b in baris
    ]


# Profil kelompok daerah

def cluster_profiles(jenjang=None, sertakan_provinsi=False):
    """Profil kelompok hasil K-Means, 4 jenjang x 3 tingkat kewaspadaan."""
    with _connect() as con:
        cur = con.cursor()
        if jenjang:
            cur.execute(
                "SELECT * FROM cluster_profiles WHERE jenjang = ? "
                "ORDER BY mean_weighted_score DESC",
                (jenjang,),
            )
        else:
            cur.execute(
                "SELECT * FROM cluster_profiles ORDER BY jenjang, mean_weighted_score DESC"
            )
        hasil = _rows(cur)

        anggota = {}
        if sertakan_provinsi and jenjang:
            cur.execute(
                "SELECT kode_prov, provinsi, label_risiko FROM provinces "
                "WHERE jenjang = ? ORDER BY provinsi",
                (jenjang,),
            )
            for r in cur.fetchall():
                anggota.setdefault(r["label_risiko"], []).append({
                    "kode_prov": r["kode_prov"],
                    "provinsi": config.nama_provinsi(r["provinsi"]),
                })

    for h in hasil:
        tingkat = h.get("label_risiko")
        h["tingkat"] = tingkat
        h["label_awam"] = config.label_awam(tingkat)
        h["warna"] = config.warna_tingkat(tingkat)
        if sertakan_provinsi:
            h["provinces"] = anggota.get(tingkat, [])
    return hasil


# Menu

_KOLOM_MENU = (
    "m.menu_id, m.provinsi, m.prov, m.jenjang, m.tingkat_kewaspadaan, m.menu_label, "
    "m.sumber_karbo, m.sumber_protein, m.energi_kkal, m.protein_g, m.lemak_g, m.karbo_g, "
    "m.rasio_energi, m.rasio_protein, m.rasio_lemak, m.rasio_karbo, "
    "m.akg_valid, m.mengandung_non_halal, m.bahan_non_halal"
)


def _susun_where(provinsi=None, jenjang=None, tingkat=None,
                 sumber_karbo=None, sumber_protein=None, halal_saja=False):
    """Bangun klausa WHERE terparameter. Semua nilai lewat placeholder.

    Kueri di modul ini memakai f-string untuk menyisipkan nama kolom dan hasil
    fungsi ini. Nilai dari pengguna tidak pernah masuk ke teks kueri; semuanya
    terikat sebagai parameter. Penanda `# nosec B608` pada tiap pemanggilan
    merujuk ke catatan ini.
    """
    klausa, params = [], []
    if provinsi:
        klausa.append("m.prov = ?")
        params.append(provinsi)
    if jenjang:
        klausa.append("m.jenjang = ?")
        params.append(jenjang)
    if tingkat:
        klausa.append("m.tingkat_kewaspadaan = ?")
        params.append(tingkat)
    if sumber_karbo:
        klausa.append("m.sumber_karbo = ?")
        params.append(sumber_karbo)
    if sumber_protein:
        klausa.append("m.sumber_protein = ?")
        params.append(sumber_protein)
    if halal_saja:
        klausa.append("m.mengandung_non_halal = 0")
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    return where, params


def _lengkapi_menu(baris, komposisi_per_menu):
    """Tambahkan penanda ringkasan pada tiap baris menu."""
    markers = penanda_bahan()
    hasil = []
    for b in baris:
        bahan = komposisi_per_menu.get(b["menu_id"], [])
        alergen, intoleransi = set(), set()
        ada_fobia = False
        isl_nilai = []
        # Ringkasan bahan dibawa serta supaya kartu menu dapat menandai bahan
        # mana yang diproduksi setempat tanpa perlu membuka halaman detail.
        # Nama bahan tidak dapat diambil dari menu_label, sebab label
        # menghilangkan bahan lemak pada 836 dari 945 menu.
        ringkas = []
        for k in bahan:
            m = markers.get(k["nama_bahan"])
            if m:
                alergen.update(m["alergen"])
                intoleransi.update(m["intoleransi"])
                if m["fobia"]:
                    ada_fobia = True
            if k.get("pangsa_lokal") is not None:
                isl_nilai.append(k["pangsa_lokal"])
            # Hanya nama dan tingkatnya yang dibawa. Nilai ISL persisnya
            # sengaja tidak ikut: kartu hanya butuh penanda, sedangkan
            # halaman detail sudah menyediakan angkanya. Membawa serta
            # nilai itu menambah sekitar 200 KB pada muatan galeri.
            ringkas.append({
                "nama_bahan": k["nama_bahan"],
                "lokal": config.tingkat_lokal(k.get("pangsa_lokal")),
            })

        # Berapa bahan menu ini yang benar-benar diproduksi di provinsinya.
        n_lokal = sum(1 for n in isl_nilai if n >= config.AMBANG_LOKAL_UTAMA)
        n_sebagian = sum(1 for n in isl_nilai
                         if config.AMBANG_LOKAL_SEBAGIAN <= n < config.AMBANG_LOKAL_UTAMA)

        tingkat = b["tingkat_kewaspadaan"]
        hasil.append({
            "menu_id": b["menu_id"],
            "provinsi": b["prov"],
            "jenjang": b["jenjang"],
            "tingkat": tingkat,
            "label_awam": config.label_awam(tingkat),
            "warna": config.warna_tingkat(tingkat),
            "menu_label": b["menu_label"],
            "sumber_karbo": b["sumber_karbo"],
            "sumber_protein": b["sumber_protein"],
            "jumlah_bahan": len(bahan),
            "energi_kkal": b["energi_kkal"],
            "protein_g": b["protein_g"],
            "lemak_g": b["lemak_g"],
            "karbo_g": b["karbo_g"],
            "rasio_energi": b["rasio_energi"],
            "rasio_protein": b["rasio_protein"],
            "akg_valid": bool(b["akg_valid"]),
            "halal": not b["mengandung_non_halal"],
            "bahan_non_halal": b["bahan_non_halal"] or "",
            "alergen": sorted(alergen),
            "intoleransi": sorted(intoleransi),
            "fobia": ada_fobia,
            "isl": round(sum(isl_nilai) / len(isl_nilai), 3) if isl_nilai else None,
            "isl_bahan_berdata": len(isl_nilai),
            "bahan_lokal": n_lokal,
            "bahan_lokal_sebagian": n_sebagian,
            "bahan_ringkas": ringkas,
        })
    return hasil


def _ambil_komposisi(con, menu_ids):
    """Ambil komposisi untuk sekumpulan menu_id dalam satu query."""
    if not menu_ids:
        return {}
    hasil = {}
    ids = list(menu_ids)
    # SQLite membatasi jumlah variabel per pernyataan, jadi dipecah per 400.
    for i in range(0, len(ids), 400):
        potong = ids[i:i + 400]
        tanya = ",".join("?" * len(potong))
        cur = con.cursor()
        cur.execute(
            f"SELECT menu_id, nama_bahan, porsi_g, kategori, subkelompok, "  # nosec B608: hanya konstanta modul yang disisipkan
            f"       status_halal, skor_risiko_bahan, pangsa_lokal "
            f"FROM menu_provinsi_komposisi WHERE menu_id IN ({tanya})",
            potong,
        )
        for r in cur.fetchall():
            hasil.setdefault(r["menu_id"], []).append(dict(r))
    return hasil


def menus(provinsi=None, jenjang=None, tingkat=None, batas=None):
    """Daftar menu untuk galeri, dengan penyaring opsional."""
    where, params = _susun_where(provinsi=provinsi, jenjang=jenjang, tingkat=tingkat)
    batas_sql = ""
    if batas:
        batas_sql = " LIMIT ?"
        params = params + [int(batas)]

    with _connect() as con:
        cur = con.cursor()
        cur.execute(
            f"SELECT {_KOLOM_MENU} FROM menu_provinsi m {where} "  # nosec B608: hanya konstanta modul yang disisipkan
            f"ORDER BY m.prov, m.jenjang, m.menu_id{batas_sql}",
            params,
        )
        baris = _rows(cur)
        komposisi = _ambil_komposisi(con, [b["menu_id"] for b in baris])

    return _lengkapi_menu(baris, komposisi)


def menu_detail(menu_id):
    """Detail satu menu berikut bahan penyusun dan capaian gizinya."""
    with _connect() as con:
        cur = con.cursor()
        cur.execute(
            f"SELECT {_KOLOM_MENU} FROM menu_provinsi m WHERE m.menu_id = ?",  # nosec B608: hanya konstanta modul yang disisipkan
            (menu_id,),
        )
        baris = cur.fetchone()
        if baris is None:
            return None
        baris = dict(baris)

        cur.execute(
            "SELECT nama_bahan, porsi_g, kategori, subkelompok, status_halal, "
            "       skor_risiko_bahan, pangsa_lokal "
            "FROM menu_provinsi_komposisi WHERE menu_id = ? "
            "ORDER BY CASE kategori "
            "  WHEN 'karbohidrat' THEN 1 WHEN 'protein_hewani' THEN 2 "
            "  WHEN 'protein_nabati' THEN 3 WHEN 'sayuran' THEN 4 "
            "  WHEN 'buah' THEN 5 ELSE 6 END, nama_bahan",
            (menu_id,),
        )
        komposisi = _rows(cur)

        cur.execute(
            "SELECT * FROM akg_standards WHERE jenjang = ?", (baris["jenjang"],)
        )
        akg_row = cur.fetchone()

    markers = penanda_bahan()
    bahan = []
    for k in komposisi:
        m = markers.get(k["nama_bahan"], {})
        isl = k["pangsa_lokal"]
        tingkat = config.tingkat_lokal(isl)
        bahan.append({
            "nama_bahan": k["nama_bahan"],
            "kategori": k["kategori"],
            "subkelompok": k["subkelompok"],
            "porsi_g": k["porsi_g"],
            "status_halal": k["status_halal"],
            "halal": k["status_halal"] == "halal",
            "skor_risiko_bahan": k["skor_risiko_bahan"],
            "alergen": m.get("alergen", []),
            "intoleransi": m.get("intoleransi", []),
            "fobia": m.get("fobia", False),
            "skor_fobia": m.get("skor_fobia", 0.0),
            "isl": isl,
            # Penanda siap tampil, supaya template dan JavaScript tidak
            # masing-masing menerjemahkan ambang dan berpotensi berbeda.
            "lokal": tingkat,
            "lokal_label": config.TINGKAT_LOKAL[tingkat]["label"],
            "lokal_arti": config.TINGKAT_LOKAL[tingkat]["arti"],
            "lokal_warna": config.TINGKAT_LOKAL[tingkat]["warna"],
        })

    ringkas = _lengkapi_menu([baris], {menu_id: komposisi})[0]
    ringkas["bahan"] = bahan
    ringkas["gizi"] = {
        "energi": {"aktual": baris["energi_kkal"], "rasio": baris["rasio_energi"]},
        "protein": {"aktual": baris["protein_g"], "rasio": baris["rasio_protein"]},
        "lemak": {"aktual": baris["lemak_g"], "rasio": baris["rasio_lemak"]},
        "karbo": {"aktual": baris["karbo_g"], "rasio": baris["rasio_karbo"]},
        "akg_valid": bool(baris["akg_valid"]),
    }
    ringkas["akg_standar"] = dict(akg_row) if akg_row else None
    return ringkas


def menu_ada(menu_id):
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM menu_provinsi WHERE menu_id = ? LIMIT 1", (menu_id,))
        return cur.fetchone() is not None


# Rekomendasi dengan penyaringan

def _urutkan(hasil, urut):
    """Urutkan hasil menurut nilai yang sudah ada di basis data."""
    if urut == "isl":
        # Menu tanpa data ISL diletakkan di belakang, bukan dianggap nol,
        # supaya tidak tampak seolah bahannya tidak tersedia sama sekali.
        hasil.sort(key=lambda m: (m["isl"] is None, -(m["isl"] or 0)))
    elif urut == "akg_energi":
        hasil.sort(key=lambda m: abs((m["rasio_energi"] or 0) - 1.0))
    elif urut == "protein":
        hasil.sort(key=lambda m: -(m["protein_g"] or 0))
    else:  # "gizi"
        hasil.sort(key=lambda m: (m["skor_gizi"] is None, -(m["skor_gizi"] or 0)))
    return hasil


def recommend(provinsi=None, jenjang=None, tingkat=None,
              exclude_alergen=None, exclude_intoleransi=None,
              tanpa_fobia=False, halal_saja=False,
              sumber_karbo=None, sumber_protein=None,
              exclude_bahan=None, include_bahan=None, include_semua=False,
              urut=None, batas=None):
    """Saring dan urutkan menu menurut kebutuhan pengguna.

    Seluruh penyaringan bersifat menyingkirkan menu yang tidak memenuhi
    syarat. Tidak ada skor gabungan baru yang dihitung di sini: pengurutan
    memakai nilai yang sudah tersimpan di basis data (skor gizi bahan, ISL,
    rasio AKG, kandungan protein), sesuai peran web sebagai lapisan penyajian.

    Args:
        provinsi: nama provinsi tanpa awalan "Prov. ". None berarti semua.
        jenjang: SD, SMP, SMA, atau SMK. None berarti semua.
        tingkat: Tinggi, Sedang, atau Rendah. None berarti semua.
        exclude_alergen: daftar nama alergen yang harus dihindari.
        exclude_intoleransi: daftar nama intoleransi yang harus dihindari.
        tanpa_fobia: True untuk membuang menu yang memuat bahan skor fobia
            di atas ambang.
        halal_saja: True untuk membuang menu bertanda non-halal.
        sumber_karbo, sumber_protein: preferensi bahan baku utama.
        exclude_bahan: daftar nama bahan tertentu yang harus dihindari.
        include_bahan: daftar nama bahan yang harus ada pada menu.
        include_semua: True berarti seluruh bahan pada include_bahan harus
            ada bersamaan. Bawaannya False, yaitu cukup salah satu.

            Bawaan ini ditetapkan dari sebaran data, bukan selera. Tiap menu
            hanya memuat lima sampai enam bahan, sehingga mensyaratkan tiga
            bahan tertentu muncul bersamaan menghasilkan nol hasil pada 90
            persen kombinasi. Dengan syarat salah satu, tidak ada kombinasi
            yang menghasilkan nol.
        urut: kunci dari config.URUT_OPSI.
        batas: jumlah menu yang dikembalikan.

    Returns:
        dict berisi ringkasan penyaringan dan daftar menu.
    """
    exclude_alergen = set(exclude_alergen or [])
    exclude_intoleransi = set(exclude_intoleransi or [])
    exclude_bahan = set(exclude_bahan or [])
    include_bahan = set(include_bahan or [])
    urut = urut if urut in config.URUT_OPSI else config.URUT_DEFAULT
    batas = min(int(batas or config.BATAS_REKOMENDASI), config.BATAS_REKOMENDASI_MAX)

    where, params = _susun_where(
        provinsi=provinsi, jenjang=jenjang, tingkat=tingkat,
        sumber_karbo=sumber_karbo, sumber_protein=sumber_protein,
        halal_saja=halal_saja,
    )

    with _connect() as con:
        cur = con.cursor()
        cur.execute(
            f"SELECT {_KOLOM_MENU} FROM menu_provinsi m {where}", params  # nosec B608: hanya konstanta modul yang disisipkan
        )
        baris = _rows(cur)
        komposisi = _ambil_komposisi(con, [b["menu_id"] for b in baris])

    total_setelah_sql = len(baris)
    markers = penanda_bahan()

    lolos = []
    for b in baris:
        bahan = komposisi.get(b["menu_id"], [])
        tolak = False
        total_gizi = n_gizi = 0.0

        # Syarat memuat bahan diperiksa lebih dulu: menu yang tidak memuatnya
        # langsung gugur tanpa perlu memeriksa penanda tiap bahannya.
        if include_bahan:
            nama_bahan = {k["nama_bahan"] for k in bahan}
            cocok = (include_bahan <= nama_bahan) if include_semua \
                else bool(include_bahan & nama_bahan)
            if not cocok:
                continue

        for k in bahan:
            nama = k["nama_bahan"]
            if nama in exclude_bahan:
                tolak = True
                break
            m = markers.get(nama)
            if not m:
                continue
            if exclude_alergen.intersection(m["alergen"]):
                tolak = True
                break
            if exclude_intoleransi.intersection(m["intoleransi"]):
                tolak = True
                break
            if tanpa_fobia and m["fobia"]:
                tolak = True
                break
            if m["skor_gizi"] is not None:
                total_gizi += float(m["skor_gizi"])
                n_gizi += 1

        if tolak:
            continue

        menu = _lengkapi_menu([b], {b["menu_id"]: bahan})[0]
        menu["skor_gizi"] = round(total_gizi / n_gizi, 4) if n_gizi else None
        lolos.append(menu)

    _urutkan(lolos, urut)

    return {
        "filter": {
            "provinsi": provinsi,
            "jenjang": jenjang,
            "tingkat": tingkat,
            "exclude_alergen": sorted(exclude_alergen),
            "exclude_intoleransi": sorted(exclude_intoleransi),
            "exclude_bahan": sorted(exclude_bahan),
            "include_bahan": sorted(include_bahan),
            "include_semua": include_semua,
            "tanpa_fobia": tanpa_fobia,
            "halal_saja": halal_saja,
            "sumber_karbo": sumber_karbo,
            "sumber_protein": sumber_protein,
            "urut": urut,
        },
        "total_menu": total_menu(),
        "total_setelah_filter_wilayah": total_setelah_sql,
        "total_lolos": len(lolos),
        "ditampilkan": min(batas, len(lolos)),
        "rekomendasi": lolos[:batas],
    }


@lru_cache(maxsize=1)
def total_menu():
    """Jumlah menu, dibaca dari tabel agregat dengan cadangan hitung ulang."""
    with _connect() as con:
        cur = con.cursor()
        if agregat_siap():
            cur.execute("SELECT nilai FROM agg_ringkasan WHERE kunci='total_menu'")
            return int(cur.fetchone()["nilai"])
        cur.execute("SELECT COUNT(*) AS n FROM menu_provinsi")
        return cur.fetchone()["n"]


# Indeks sumber lokal (isl)

def isl_provinsi(provinsi):
    """Nilai ISL tiap bahan di satu provinsi, diurutkan menurun.

    Mengembalikan None bila provinsi tidak dikenal, supaya pemanggil bisa
    membedakan "provinsi tidak ada" dari "provinsi ada tetapi ISL-nya nol".
    """
    kunci = config.kunci_provinsi(provinsi)
    if not provinsi_valid(provinsi):
        return None

    with _connect() as con:
        cur = con.cursor()
        # Bahan tanpa nilai ISL sengaja tidak dikembalikan. Menampilkannya
        # sebagai nol akan terbaca seolah bahan itu tidak tersedia sama
        # sekali, padahal yang benar adalah datanya tidak diketahui.
        cur.execute(
            "SELECT nama_bahan, komoditas, ISL FROM ingredient_locality "
            "WHERE provinsi_key = ? AND ISL IS NOT NULL "
            "ORDER BY ISL DESC, nama_bahan",
            (kunci,),
        )
        baris = _rows(cur)

    return [
        {"nama_bahan": b["nama_bahan"], "komoditas": b["komoditas"], "isl": b["ISL"]}
        for b in baris
    ]


def isl_ranking_menu(provinsi, jenjang=None):
    """Peringkat menu satu provinsi menurut rata-rata ISL bahannya.

    Mengembalikan None bila provinsi tidak dikenal.
    """
    if not provinsi_valid(provinsi):
        return None

    with _connect() as con:
        cur = con.cursor()
        if agregat_siap():
            # Tabel agregat membawa kolom `prov` persis seperti menu_provinsi,
            # sehingga penyaringnya sama dengan jalur cadangan.
            klausa = ["prov = ?"]
            params = [provinsi]
            if jenjang:
                klausa.append("jenjang = ?")
                params.append(jenjang)
            cur.execute(
                f"SELECT menu_id, menu_label, jenjang, tingkat_kewaspadaan, "  # nosec B608: hanya konstanta modul yang disisipkan
                f"       isl, bahan_berdata, bahan_total "
                f"FROM agg_isl_ranking WHERE {' AND '.join(klausa)} "
                f"ORDER BY isl DESC, menu_id",
                params,
            )
        else:
            where, params = _susun_where(provinsi=provinsi, jenjang=jenjang)
            cur.execute(
                f"SELECT m.menu_id, m.menu_label, m.jenjang, m.tingkat_kewaspadaan, "  # nosec B608: hanya konstanta modul yang disisipkan
                f"       AVG(k.pangsa_lokal) AS isl, "
                f"       COUNT(k.pangsa_lokal) AS bahan_berdata, "
                f"       COUNT(*) AS bahan_total "
                f"FROM menu_provinsi m "
                f"JOIN menu_provinsi_komposisi k ON k.menu_id = m.menu_id "
                f"{where} GROUP BY m.menu_id "
                f"ORDER BY isl DESC, m.menu_id",
                params,
            )
        baris = _rows(cur)

    hasil = [
        {
            "menu_id": b["menu_id"],
            "menu_label": b["menu_label"],
            "jenjang": b["jenjang"],
            "tingkat": b["tingkat_kewaspadaan"],
            "isl": _bulat(b["isl"], DESIMAL_ISL),
            "bahan_berdata": b["bahan_berdata"],
            "bahan_total": b["bahan_total"],
        }
        for b in baris
    ]
    # Diurut ulang memakai nilai yang sudah dibulatkan. Urutan dari basis data
    # memakai rata-rata penuh, sehingga dua menu yang hanya berbeda pada digit
    # kesepuluh dapat bertukar tempat antara jalur agregat dan jalur cadangan.
    hasil.sort(key=lambda m: (-(m["isl"] if m["isl"] is not None else -1),
                              m["menu_id"]))
    return hasil


@lru_cache(maxsize=1)
def kelompok_produksi():
    """Daftar kelompok komoditas dan tahun yang tersedia pada data produksi."""
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT DISTINCT kelompok FROM produksi_pangan ORDER BY kelompok")
        kelompok = [r["kelompok"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT tahun FROM produksi_pangan ORDER BY tahun DESC")
        tahun = [r["tahun"] for r in cur.fetchall()]
    return tuple(kelompok), tuple(tahun)


# Tabel agregat: aplikasi menampilkan, pipeline menghitung
# Seluruh angka turunan dihitung sekali oleh sel P10 pipeline lalu disimpan
# sebagai tabel `agg_*`. Aplikasi hanya membacanya. Dengan begitu angka pada
# aplikasi dijamin sama persis dengan angka pada naskah, sebab keduanya berasal
# dari satu perhitungan yang sama.
#
# Jalur cadangan disediakan untuk satu keadaan saja: tabel agregat belum ada
# atau sudah basi karena pipeline belum dijalankan ulang setelah data berubah.
# Pemicunya adalah ketidakcocokan cap versi, bukan batas waktu. Batas waktu
# ditolak sebagai pemicu karena agregasi terberat hanya memakan sekitar 47 ms,
# sehingga ambang waktu apa pun yang masuk akal tidak akan pernah menyala dan
# hanya akan menjadi kode mati.
#
# Saat cadangan menyala, aplikasi tetap menyajikan angka yang benar karena
# dihitung ulang dari tabel sumber yang sama, dan kejadiannya dicatat di log
# server agar ketahuan bahwa pipeline perlu dijalankan.

SEMUA_KELOMPOK = ""     # penanda "seluruh kelompok" pada tabel agregat
SEMUA_TAHUN = 0         # penanda "seluruh tahun" pada tabel agregat

_agregat_siap = None    # None berarti belum diperiksa pada proses ini


def _sidik_sumber(con):
    """Sidik ringkas isi tabel sumber. Harus sama persis dengan P10_agregat.py."""
    bagian = []
    for sql in (
        "SELECT COUNT(*), ROUND(COALESCE(SUM(produksi_ton),0), 3) FROM produksi_pangan",
        "SELECT COUNT(*) FROM menu_provinsi",
        "SELECT COUNT(*), ROUND(COALESCE(SUM(pangsa_lokal),0), 6) FROM menu_provinsi_komposisi",
        "SELECT COUNT(*) FROM provinces",
        "SELECT COUNT(*) FROM ingredient_locality",
    ):
        bagian.append("|".join(str(x) for x in con.execute(sql).fetchone()))
    return hashlib.sha256("::".join(bagian).encode()).hexdigest()[:32]


def agregat_siap():
    """Apakah tabel agregat ada dan masih sesuai dengan data sumbernya.

    Hasilnya diingat selama proses berjalan, sebab basis data dibuka hanya baca
    dan tidak berubah selagi aplikasi hidup.
    """
    global _agregat_siap
    if _agregat_siap is not None:
        return _agregat_siap

    with _connect() as con:
        ada = con.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master "
            "WHERE type='table' AND name='meta_agregat'"
        ).fetchone()["n"]
        if not ada:
            log.warning(
                "Tabel agregat tidak ditemukan. Aplikasi menghitung sendiri. "
                "Jalankan sel P10 pada Pipeline_Menu_Provinsi.ipynb."
            )
            _agregat_siap = False
            return _agregat_siap

        tersimpan = con.execute(
            "SELECT nilai FROM meta_agregat WHERE kunci='versi_data'"
        ).fetchone()
        sekarang = _sidik_sumber(con)
        cocok = bool(tersimpan) and tersimpan["nilai"] == sekarang
        if not cocok:
            log.warning(
                "Tabel agregat basi: cap versi %s tidak cocok dengan data %s. "
                "Aplikasi menghitung sendiri. Jalankan ulang sel P10.",
                tersimpan["nilai"] if tersimpan else "(kosong)", sekarang,
            )
        _agregat_siap = cocok
    return _agregat_siap


# Catatan perihal kewajaran angka produksi.
#
# Aplikasi ini TIDAK menilai kewajaran data produksi. Seluruh angka berasal dari
# publikasi resmi Badan Pusat Statistik, dan keabsahannya adalah tanggung jawab
# lembaga penerbitnya, bukan penelitian ini. Menandai angka resmi sebagai
# meragukan berarti menempatkan penilaian penulis di atas penilaian lembaga
# statistik negara tanpa dasar, sekaligus menyembunyikan fakta nyata bahwa
# produksi antarwilayah memang timpang karena spesialisasi daerah.
#
# Cacat yang benar-benar ada, yaitu satuan biofarmaka dan satu baris yang rusak
# saat pengambilan data, sudah diperbaiki di hulu pada sel P8 pipeline dengan
# angka rujukan resmi BPS. Lihat 01_dokumen/Verifikasi_BPS_Biofarmaka.md.


def produksi_peta(kelompok=None, tahun=None):
    """Total produksi per provinsi untuk diwarnakan ke peta.

    Hanya provinsi yang ada di tabel provinces yang dikembalikan, sebab
    tabel produksi memuat 38 provinsi sementara peta memakai 36 provinsi
    yang punya data peserta didik.

    Angka dikembalikan apa adanya, tanpa penyaringan maupun penandaan.

    Dibaca dari tabel agregat hasil pipeline. Bila tabel itu belum ada atau
    sudah basi, angkanya dihitung ulang dari tabel sumber.
    """
    with _connect() as con:
        cur = con.cursor()
        if agregat_siap():
            cur.execute(
                "SELECT provinsi_key, total_ton, n_komoditas FROM agg_produksi_peta "
                "WHERE kelompok = ? AND tahun = ?",
                (kelompok or SEMUA_KELOMPOK, int(tahun) if tahun else SEMUA_TAHUN),
            )
        else:
            klausa, params = [], []
            if kelompok:
                klausa.append("kelompok = ?")
                params.append(kelompok)
            if tahun:
                klausa.append("tahun = ?")
                params.append(int(tahun))
            where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
            cur.execute(
                f"SELECT provinsi_key, SUM(produksi_ton) AS total_ton, "  # nosec B608: hanya konstanta modul yang disisipkan
                f"       COUNT(DISTINCT komoditas) AS n_komoditas "
                f"FROM produksi_pangan {where} GROUP BY provinsi_key",
                params,
            )
        baris = _rows(cur)

    _, ke_kode = _peta_kode_provinsi()
    hasil = []
    for b in baris:
        kode = ke_kode.get(b["provinsi_key"])
        if kode is None:
            continue        # provinsi di luar cakupan peta
        hasil.append({
            "kode_prov": kode,
            "provinsi": nama_dari_kode(kode),
            "total_ton": _bulat(b["total_ton"] or 0, 1),
            "n_komoditas": b["n_komoditas"],
        })
    # Pengurutan memakai nilai yang sudah dibulatkan, dengan kode provinsi
    # sebagai pemecah seri. Tanpa pemecah seri, dua provinsi bertonase sama
    # dapat bertukar urutan antar pemuatan maupun antar jalur.
    hasil.sort(key=lambda p: (-p["total_ton"], p["kode_prov"]))
    return hasil


def komoditas_teratas(provinsi, tahun=None, batas=8):
    """Komoditas dengan produksi terbesar di satu provinsi.

    Dibaca dari tabel agregat hasil pipeline, dengan cadangan hitung ulang.
    """
    if not provinsi_valid(provinsi):
        return None
    kunci = config.kunci_provinsi(provinsi)

    with _connect() as con:
        cur = con.cursor()
        if agregat_siap():
            cur.execute(
                "SELECT komoditas, kelompok, ton FROM agg_produksi_komoditas "
                "WHERE provinsi_key = ? AND tahun = ? "
                "ORDER BY ton DESC, komoditas LIMIT ?",
                (kunci, int(tahun) if tahun else SEMUA_TAHUN, int(batas)),
            )
        else:
            klausa = ["provinsi_key = ?"]
            params = [kunci]
            if tahun:
                klausa.append("tahun = ?")
                params.append(int(tahun))
            params.append(int(batas))
            cur.execute(
                f"SELECT komoditas, kelompok, SUM(produksi_ton) AS ton "  # nosec B608: hanya konstanta modul yang disisipkan
                f"FROM produksi_pangan WHERE {' AND '.join(klausa)} "
                f"GROUP BY komoditas ORDER BY ton DESC, komoditas LIMIT ?",
                params,
            )
        baris = _rows(cur)

    # Dibulatkan di kedua jalur, lalu diurut ulang memakai nilai bulat itu.
    # Urutan dari basis data memakai nilai penuh, sehingga dua komoditas yang
    # hanya berbeda pada digit terakhir dapat bertukar tempat antar jalur.
    for b in baris:
        b["ton"] = _bulat(b["ton"], DESIMAL_TON)
    baris.sort(key=lambda b: (-(b["ton"] or 0), b["komoditas"]))
    return baris


def ringkasan_produksi(provinsi, tahun=None):
    """Angka pokok produksi satu provinsi, untuk kepala halaman produsen."""
    if not provinsi_valid(provinsi):
        return None
    kunci = config.kunci_provinsi(provinsi)
    th = int(tahun) if tahun else SEMUA_TAHUN

    with _connect() as con:
        cur = con.cursor()
        if agregat_siap():
            cur.execute(
                "SELECT total_ton, n_komoditas, n_kelompok, tahun_awal, tahun_akhir "
                "FROM agg_produksi_ringkasan WHERE provinsi_key = ? AND tahun = ?",
                (kunci, th),
            )
            baris = cur.fetchone()
            b = dict(baris) if baris else {"total_ton": 0, "n_komoditas": 0,
                                           "n_kelompok": 0, "tahun_awal": None,
                                           "tahun_akhir": None}
            cur.execute(
                "SELECT kelompok, ton, n_komoditas FROM agg_produksi_kelompok "
                "WHERE provinsi_key = ? AND tahun = ? ORDER BY ton DESC",
                (kunci, th),
            )
            kelompok = _rows(cur)
        else:
            klausa = ["provinsi_key = ?"]
            params = [kunci]
            if tahun:
                klausa.append("tahun = ?")
                params.append(int(tahun))
            cur.execute(
                f"SELECT SUM(produksi_ton) AS total_ton, "  # nosec B608: hanya konstanta modul yang disisipkan
                f"       COUNT(DISTINCT komoditas) AS n_komoditas, "
                f"       COUNT(DISTINCT kelompok) AS n_kelompok, "
                f"       MIN(tahun) AS tahun_awal, MAX(tahun) AS tahun_akhir "
                f"FROM produksi_pangan WHERE {' AND '.join(klausa)}",
                params,
            )
            b = dict(cur.fetchone())
            cur.execute(
                f"SELECT kelompok, SUM(produksi_ton) AS ton, "  # nosec B608: hanya konstanta modul yang disisipkan
                f"       COUNT(DISTINCT komoditas) AS n_komoditas "
                f"FROM produksi_pangan WHERE {' AND '.join(klausa)} "
                f"GROUP BY kelompok ORDER BY ton DESC",
                params,
            )
            kelompok = _rows(cur)

    for k in kelompok:
        k["ton"] = _bulat(k["ton"], DESIMAL_TON)
    kelompok.sort(key=lambda k: (-(k["ton"] or 0), k["kelompok"]))

    return {
        "provinsi": nama_dari_kode(kode_dari_nama(provinsi)),
        "total_ton": _bulat(b["total_ton"] or 0, 1),
        "n_komoditas": b["n_komoditas"] or 0,
        "n_kelompok": b["n_kelompok"] or 0,
        "tahun_awal": b["tahun_awal"],
        "tahun_akhir": b["tahun_akhir"],
        "kelompok": kelompok,
    }


def profil_pangan_provinsi(provinsi=None):
    """Indeks Pola Pangan Wilayah per kelompok pangan.

    Tiap baris ditandai apakah nilainya terukur sendiri atau mewarisi provinsi
    induk. Empat provinsi hasil pemekaran Papua belum punya survei Neraca Bahan
    Makanan sendiri, dan tanpa penanda ini pembaca akan mengira angkanya hasil
    pengukuran di wilayah tersebut.
    """
    with _connect() as con:
        cur = con.cursor()
        if provinsi:
            cur.execute(
                "SELECT * FROM province_food_profile WHERE LOWER(REPLACE(provinsi,'.','')) = ?",
                (config.kunci_provinsi(provinsi),),
            )
        else:
            cur.execute("SELECT * FROM province_food_profile ORDER BY provinsi")
        baris = _rows(cur)

    for b in baris:
        induk = config.ipw_warisan_dari(b.get("provinsi"))
        b["warisan"] = induk is not None
        b["warisan_dari"] = induk
        if induk:
            b["catatan"] = config.CATATAN_IPW_WARISAN
    return baris


def produksi_provinsi(provinsi, tahun=None, batas=200):
    """Data produksi pangan mentah, untuk halaman penelusuran sumber angka."""
    if not provinsi_valid(provinsi):
        return None
    klausa = ["LOWER(REPLACE(provinsi,'.','')) = ?"]
    params = [config.kunci_provinsi(provinsi)]
    if tahun:
        klausa.append("tahun = ?")
        params.append(int(tahun))
    params.append(int(batas))

    with _connect() as con:
        cur = con.cursor()
        cur.execute(
            f"SELECT provinsi, komoditas, kelompok, tahun, produksi_ton, satuan "  # nosec B608: hanya konstanta modul yang disisipkan
            f"FROM produksi_pangan WHERE {' AND '.join(klausa)} "
            f"ORDER BY tahun DESC, produksi_ton DESC LIMIT ?",
            params,
        )
        return _rows(cur)


# Batas baris tiap permintaan tabel produksi mentah. Tabelnya memuat lebih dari
# lima belas ribu baris, sehingga tidak boleh dikirim sekaligus. Nilai ini
# menjaga muatan tiap permintaan tetap wajar sesuai NFR-002.
PRODUKSI_BATAS_BAKU = 100
PRODUKSI_BATAS_MAX = 500


def _kunci_produksi(nilai):
    """Seragamkan masukan provinsi menjadi provinsi_key tabel produksi.

    Menerima kunci apa adanya maupun nama provinsi dalam ejaan mana pun,
    sehingga alamat data tetap ramah dipanggil tanpa perlu tahu ejaan persis
    yang tersimpan.
    """
    return config.kunci_provinsi(nilai)


def produksi_mentah(provinsi=None, kelompok=None, komoditas=None, tahun=None,
                    batas=PRODUKSI_BATAS_BAKU, offset=0):
    """Tabel produksi pangan mentah berpenyaring, dimuat bertahap.

    Berbeda dari `produksi_provinsi()` yang selalu menyaring satu provinsi,
    fungsi ini melayani halaman data mentah yang boleh menampilkan seluruh
    provinsi sekaligus. Karena itu jumlah barisnya dibatasi dan disertai
    penghitung total supaya sisi depan tahu berapa yang belum dimuat.

    Penyaring apa pun boleh kosong, artinya tidak menyaring. Seluruh nilai
    masuk sebagai parameter terikat, bukan disisipkan ke teks kueri.
    """
    klausa, params = [], []
    if provinsi:
        # Disaring lewat provinsi_key, bukan kolom provinsi. Kolom provinsi
        # memuat 47 ragam ejaan untuk 38 provinsi, warisan dari berbagai
        # berkas sumber, misalnya "DI Yogyakarta", "Di Yogyakarta", dan
        # "D.I. Yogyakarta". provinsi_key sudah diseragamkan pipeline.
        klausa.append("provinsi_key = ?")
        params.append(_kunci_produksi(provinsi))
    if kelompok:
        klausa.append("kelompok = ?")
        params.append(kelompok)
    if komoditas:
        klausa.append("komoditas = ?")
        params.append(komoditas)
    if tahun:
        klausa.append("tahun = ?")
        params.append(int(tahun))

    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    batas = max(1, min(int(batas), PRODUKSI_BATAS_MAX))
    offset = max(0, int(offset))

    with _connect() as con:
        cur = con.cursor()
        # Nama kolom dan susunan urutan berasal dari konstanta modul; hanya
        # nilai penyaring yang berasal dari pengguna, dan seluruhnya terikat.
        cur.execute(f"SELECT COUNT(*) n FROM produksi_pangan {where}", params)  # nosec B608: hanya konstanta modul yang disisipkan
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT provinsi, komoditas, kelompok, tahun, produksi_ton, satuan "  # nosec B608: hanya konstanta modul yang disisipkan
            f"FROM produksi_pangan {where} "
            f"ORDER BY provinsi, komoditas, tahun DESC LIMIT ? OFFSET ?",
            params + [batas, offset],
        )
        baris = _rows(cur)

    return {
        "total": total,
        "batas": batas,
        "offset": offset,
        "ditampilkan": len(baris),
        "ada_lagi": offset + len(baris) < total,
        "baris": baris,
    }


def opsi_produksi():
    """Pilihan penyaring tabel produksi: provinsi, kelompok, komoditas, tahun.

    Diambil dari isi tabel, bukan ditulis tangan, sehingga pilihan yang muncul
    selalu benar-benar ada datanya dan tidak pernah menghasilkan tabel kosong.
    """
    with _connect() as con:
        cur = con.cursor()
        # Dikelompokkan menurut provinsi_key, sebab kolom provinsi memuat 47
        # ragam ejaan untuk 38 provinsi. Nama yang ditampilkan adalah ejaan
        # terpanjang pada tiap kunci, yaitu bentuk terlengkap seperti
        # "Kepulauan Bangka Belitung" ketimbang "Kepulauan Bangka".
        cur.execute(
            "SELECT provinsi_key AS kunci, "
            "       (SELECT p2.provinsi FROM produksi_pangan p2 "
            "        WHERE p2.provinsi_key = p1.provinsi_key "
            "        ORDER BY LENGTH(p2.provinsi) DESC, p2.provinsi LIMIT 1) AS nama, "
            "       COUNT(*) AS n_baris "
            "FROM produksi_pangan p1 GROUP BY provinsi_key ORDER BY nama"
        )
        provinsi = _rows(cur)
        cur.execute("SELECT DISTINCT kelompok FROM produksi_pangan ORDER BY kelompok")
        kelompok = [r["kelompok"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT komoditas FROM produksi_pangan ORDER BY komoditas")
        komoditas = [r["komoditas"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT tahun FROM produksi_pangan ORDER BY tahun DESC")
        tahun = [r["tahun"] for r in cur.fetchall()]
    return {
        "provinsi": provinsi,
        "kelompok": kelompok,
        "komoditas": komoditas,
        "tahun": tahun,
    }


# Data mentah dan standar akg

KOLOM_MENTAH = [
    "kode_prov", "jenjang", "provinsi", "tahun",
    "jumlah_satuan_pendidikan", "jumlah_satpen_negeri", "jumlah_satpen_swasta",
    "jumlah_laki", "jumlah_perempuan", "jumlah_penerima_manfaat",
    "jumlah_alergi", "jumlah_intoleransi", "jumlah_fobia",
    "jumlah_kondisi_khusus", "is_imputed",
]
KOLOM_ML = [
    "rate_alergi", "rate_intoleransi", "rate_fobia",
    "Xa", "Xi", "Xf", "cluster", "weighted_score", "label_risiko",
]


def provinces_raw(jenjang=None, dengan_label=False):
    """Tabel data mentah provinsi, dengan atau tanpa kolom hasil pemodelan."""
    kolom = KOLOM_MENTAH + (KOLOM_ML if dengan_label else [])
    klausa = "WHERE jenjang = ?" if jenjang else ""
    params = (jenjang,) if jenjang else ()

    with _connect() as con:
        cur = con.cursor()
        # Nama kolom berasal dari konstanta modul, bukan masukan pengguna.
        cur.execute(
            f"SELECT {', '.join(kolom)} FROM provinces {klausa} "  # nosec B608: hanya konstanta modul yang disisipkan
            f"ORDER BY provinsi, jenjang",
            params,
        )
        hasil = _rows(cur)

    for h in hasil:
        h["provinsi"] = config.nama_provinsi(h["provinsi"])
        if dengan_label and h.get("label_risiko"):
            h["tingkat"] = h["label_risiko"]
            h["label_awam"] = config.label_awam(h["label_risiko"])
    return {"kolom": kolom, "baris": hasil}


def akg_standards():
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM akg_standards")
        return _rows(cur)


def ringkasan():
    """Angka pokok untuk halaman metodologi dan pemeriksaan kesehatan sistem."""
    with _connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) n FROM menu_provinsi")
        n_menu = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(DISTINCT prov) n FROM menu_provinsi")
        n_prov = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM provinces")
        n_baris = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM ingredients")
        n_bahan = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(DISTINCT nama_bahan) n FROM menu_provinsi_komposisi")
        n_bahan_pakai = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM menu_provinsi WHERE akg_valid = 1")
        n_akg = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM menu_provinsi WHERE mengandung_non_halal = 1")
        n_non_halal = cur.fetchone()["n"]
        cur.execute("SELECT AVG(pangsa_lokal) a FROM menu_provinsi_komposisi "
                    "WHERE pangsa_lokal IS NOT NULL")
        isl_rata = cur.fetchone()["a"]
        # Dihitung, bukan ditulis tangan. Halaman Tentang pernah menyatakan
        # sebagian data hasil estimasi padahal tidak ada satu pun. Selama
        # angkanya dibaca dari basis data, pernyataan itu tidak mungkin
        # bertentangan dengan isinya lagi.
        cur.execute("SELECT COUNT(*) n FROM provinces WHERE is_imputed = 1")
        n_imputed = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM menu_provinsi_komposisi "
                    "WHERE pangsa_lokal IS NOT NULL")
        n_isl_ada = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM menu_provinsi_komposisi")
        n_komposisi = cur.fetchone()["n"]
        cur.execute("SELECT MIN(tahun) a, MAX(tahun) b FROM produksi_pangan")
        th = cur.fetchone()

    n_grid = len(config.JENJANG_LIST) * config.TOTAL_PROVINSI_GRID
    return {
        "total_menu": n_menu,
        "total_provinsi": n_prov,
        "total_baris_provinsi": n_baris,
        "total_bahan": n_bahan,
        "bahan_terpakai": n_bahan_pakai,
        "menu_akg_valid": n_akg,
        "menu_non_halal": n_non_halal,
        "isl_rata_rata": round(isl_rata, 3) if isl_rata else None,
        "baris_imputed": n_imputed,
        "total_grid": n_grid,
        "baris_dibuang": n_grid - n_baris,
        "isl_cakupan_persen": round(100 * n_isl_ada / n_komposisi, 1) if n_komposisi else 0,
        "produksi_tahun_awal": th["a"],
        "produksi_tahun_akhir": th["b"],
    }
