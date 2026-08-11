"""
config.py
Konfigurasi terpusat untuk web rekomendasi menu MBG.

Satu berkas, satu tujuan: semua konstanta yang dipakai lintas modul
dikumpulkan di sini. Mengubah satu nilai di sini cukup untuk mengubah
perilaku seluruh aplikasi.

Skema data: basis data per-provinsi hasil pipeline 5 Agustus 2026
(`mbg_recommendations_provinsi.db`), berisi 945 menu untuk 36 provinsi.
Istilah `cluster_label` pada versi sebelumnya kini bernama
`tingkat_kewaspadaan`, dan ukuran ketersediaan bahan lokal memakai
Indeks Sumber Lokal (ISL) yang bernilai kontinu 0 sampai 1.
"""

import hashlib
import os
import secrets

# Lingkungan
ENV = os.getenv("FLASK_ENV", "production").lower()
DEBUG = ENV == "development"
TESTING = ENV == "testing"

# Jalur berkas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv(
    "MBG_DB_PATH",
    os.path.join(BASE_DIR, "data", "mbg_recommendations_provinsi.db"),
)
GEOJSON_PATH = os.path.join(BASE_DIR, "static", "data", "provinsi.geojson")

# Keamanan
# Kunci ini harus sama di seluruh worker. Gunicorn menjalankan beberapa proses
# sekaligus, dan tiap proses menjalankan berkas ini sendiri-sendiri. Kunci yang
# diacak per proses berarti tiap worker memakai kunci berbeda, sehingga apa pun
# yang ditandatangani satu worker akan ditolak worker lain.
#
# Di produksi kunci wajib datang dari lingkungan. Bila tidak diset, aplikasi
# lebih baik menolak start daripada diam-diam mengarang kunci dan gagal secara
# tidak kasatmata setelah berjalan.
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("MBG_SECRET_KEY") or ""
if not SECRET_KEY:
    if ENV == "production":
        raise RuntimeError(
            "MBG_SECRET_KEY wajib diset saat FLASK_ENV=production. "
            "Hasilkan dengan: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    # Di luar produksi kunci acak sudah cukup dan tidak menghalangi pengembangan.
    SECRET_KEY = secrets.token_hex(32)

# Penanda rilis. Dipakai gerbang alur penjelasan sebagai penanda "satu kali
# jalan": cookie yang membawa penanda berbeda dianggap sisa deploy lama dan
# kemajuannya dikembalikan ke nol.
#
# Nilainya harus sama di seluruh worker dalam satu deploy, dan harus berubah
# pada deploy berikutnya. SHA commit memenuhi keduanya, dan hampir semua
# platform menyediakannya sebagai variabel lingkungan.
#
# Bila kosong, nilainya diturunkan dari SECRET_KEY. Selama SECRET_KEY diset
# dari lingkungan, seluruh worker tetap menghasilkan penanda yang sama.
RILIS = (
    os.getenv("MBG_RILIS")
    or os.getenv("RENDER_GIT_COMMIT")        # Render
    or os.getenv("RAILWAY_GIT_COMMIT_SHA")   # Railway
    or os.getenv("SOURCE_COMMIT")            # Hugging Face Spaces
    or os.getenv("FLY_MACHINE_VERSION")      # Fly.io
    or hashlib.sha256(SECRET_KEY.encode()).hexdigest()
)[:16]

# Batas ukuran badan permintaan POST (byte). Ditegakkan Werkzeug, bukan hanya
# lewat header Content-Length, sehingga permintaan chunked ikut terbatasi.
MAX_CONTENT_LENGTH = int(os.getenv("MBG_MAX_PAYLOAD", "8192"))

# Rate limit per IP per menit.
RATE_LIMIT_PER_MINUTE = int(os.getenv("MBG_RATE_LIMIT", "240"))
# Entri bucket yang tidak aktif selama sekian detik dibuang, supaya kamus
# rate limit tidak tumbuh tanpa batas.
RATE_LIMIT_TTL_SECONDS = int(os.getenv("MBG_RATE_LIMIT_TTL", "600"))
# Jumlah proxy tepercaya di depan aplikasi (Nginx = 1). Nol berarti aplikasi
# diakses langsung dan header X-Forwarded-For tidak boleh dipercaya.
TRUSTED_PROXY_COUNT = int(os.getenv("MBG_TRUSTED_PROXIES", "0"))

# Basis data
DB_TIMEOUT_MS = int(os.getenv("MBG_DB_TIMEOUT", "5000"))
DB_CACHE_SIZE_KB = int(os.getenv("MBG_DB_CACHE", "-8000"))
DB_JOURNAL_MODE = os.getenv("MBG_DB_JOURNAL", "WAL")

# Jenjang dan tingkat kewaspadaan
JENJANG_LIST = ["SD", "SMP", "SMA", "SMK"]

# Jumlah provinsi pada grid penuh data MBG. Dipakai menghitung berapa kombinasi
# provinsi dan jenjang yang dibuang saat penyaringan, tanpa menulis angkanya
# dengan tangan di templat.
TOTAL_PROVINSI_GRID = 38

# Urutan sengaja dari paling waspada ke paling aman. Dipakai juga oleh
# tingkat_tertinggi() untuk memilih tingkat mana yang mewakili satu provinsi
# ketika keempat jenjangnya berbeda.
TINGKAT_LIST = ["Tinggi", "Sedang", "Rendah"]
URUTAN_WASPADA = TINGKAT_LIST

LABEL_AWAM = {
    "Tinggi": "Perlu sangat hati-hati",
    "Sedang": "Perlu hati-hati",
    "Rendah": "Relatif aman",
}
LABEL_KOSONG = "Data belum tersedia"

WARNA_TINGKAT = {
    "Tinggi": "#d64545",
    "Sedang": "#e08e2b",
    "Rendah": "#3f9d5b",
    None: "#c9ccd1",
}


# Versi tanpa kunci None, aman diserialkan ke JSON untuk dipakai sisi depan.
WARNA_TINGKAT_JSON = {t: WARNA_TINGKAT[t] for t in TINGKAT_LIST}


def label_awam(tingkat):
    """Ubah istilah teknis tingkat kewaspadaan menjadi bahasa sehari-hari."""
    if not tingkat:
        return LABEL_KOSONG
    return LABEL_AWAM.get(tingkat, tingkat)


def warna_tingkat(tingkat):
    return WARNA_TINGKAT.get(tingkat, WARNA_TINGKAT[None])


def tingkat_tertinggi(daftar_tingkat):
    """Pilih tingkat paling waspada dari beberapa jenjang di satu provinsi."""
    bersih = [t for t in daftar_tingkat if t]
    if not bersih:
        return None
    for tingkat in URUTAN_WASPADA:
        if tingkat in bersih:
            return tingkat
    return None


# Penanda bahan
KOLOM_ALERGEN = {
    "alergen_telur": "telur",
    "alergen_ikan": "ikan",
    "alergen_susu": "susu",
    "alergen_kerang": "kerang",
    "alergen_kacang_tanah": "kacang tanah",
    "alergen_kacang_pohon": "kacang pohon",
    "alergen_gandum": "gandum",
    "alergen_kedelai": "kedelai",
}
KOLOM_INTOLERANSI = {
    "intoleransi_laktosa": "laktosa",
    "intoleransi_gluten": "gluten",
}
ALERGEN_LIST = sorted(KOLOM_ALERGEN.values())
INTOLERANSI_LIST = sorted(KOLOM_INTOLERANSI.values())

# Ambang skor fobia. Bahan berskor di atas nilai ini ditandai sebagai bahan
# yang umum ditolak anak (neofobia pangan), bukan sebagai bahaya kesehatan.
AMBANG_FOBIA = 0.30

# Preferensi sumber karbohidrat dan protein
# Nilai memetakan langsung ke kolom sumber_karbo dan sumber_protein pada
# tabel menu_provinsi, jadi penyaringan dikerjakan basis data, bukan tebakan
# pencocokan nama bahan seperti pada versi sebelumnya.
SUMBER_KARBO = {
    "serealia": "Nasi dan olahan serealia",
    "umbi": "Umbi (singkong, ubi, kentang)",
    "sagu": "Sagu dan papeda",
}
SUMBER_PROTEIN = {
    "ternak": "Daging ternak dan unggas",
    "telur": "Telur",
    "ikan_laut": "Ikan laut",
    "ikan_tawar": "Ikan air tawar",
    "seafood_lain": "Hasil laut lain",
}
SUMBER_KARBO_LIST = list(SUMBER_KARBO.keys())
SUMBER_PROTEIN_LIST = list(SUMBER_PROTEIN.keys())

# Kategori bahan yang benar-benar menjadi komponen menu
# Tabel bahan memuat sembilan kategori, tetapi penyusun menu hanya mengundi
# dari enam kategori ini. Bumbu, camilan, dan susu ada di basis data sebagai
# kelengkapan penanda alergen, bukan sebagai kandidat komponen menu.
KATEGORI_MENU = [
    "karbohidrat", "protein_hewani", "protein_nabati",
    "sayuran", "buah", "lemak",
]

# Pengurutan hasil
# Web ini lapisan penyajian: tidak ada model yang dijalankan saat permintaan
# masuk. Karena itu pengurutan memakai nilai yang sudah ada di basis data,
# bukan skor gabungan baru yang dikarang di sisi web.
URUT_OPSI = {
    "gizi": "Skor gizi bahan (tertinggi dulu)",
    "isl": "Ketersediaan bahan lokal / ISL (tertinggi dulu)",
    "akg_energi": "Rasio energi terhadap AKG (paling mendekati 1)",
    "protein": "Kandungan protein (tertinggi dulu)",
}
URUT_DEFAULT = "gizi"

# Jumlah menu yang dikembalikan endpoint rekomendasi.
BATAS_REKOMENDASI = int(os.getenv("MBG_BATAS_REKOMENDASI", "12"))
BATAS_REKOMENDASI_MAX = 50

# Status halal
LABEL_HALAL = {
    "halal": "Halal",
    "non_halal": "Mengandung bahan non-halal",
}

# Penanda bahan yang diproduksi setempat
# Indeks Sumber Lokal bernilai kontinu 0 sampai 1, tetapi pembaca butuh
# penanda yang langsung terbaca. Ambang di bawah membagi bahan berdata
# menjadi tiga kelompok yang besarnya seimbang, masing-masing sekitar
# sepertiga: 48 persen bernilai 0,7 ke atas, 28 persen di rentang tengah,
# dan 23 persen di bawah 0,3.
#
# Ambang ini murni untuk penyajian dan tidak dipakai pipeline maupun
# perhitungan mana pun. Angka aslinya selalu ikut ditampilkan di sebelah
# penandanya supaya pembaca dapat menilai sendiri.
AMBANG_LOKAL_UTAMA = 0.70
AMBANG_LOKAL_SEBAGIAN = 0.30

TINGKAT_LOKAL = {
    "utama": {
        "label": "Diproduksi di provinsi ini",
        "arti": "Sebagian besar kebutuhan bahan ini dapat dipenuhi produksi provinsi sendiri.",
        "warna": "#3f9d5b",
    },
    "sebagian": {
        "label": "Sebagian dari provinsi ini",
        "arti": "Sebagian kebutuhan dipenuhi produksi provinsi sendiri, sisanya dari luar.",
        "warna": "#e08e2b",
    },
    "sedikit": {
        "label": "Sedikit dari provinsi ini",
        "arti": "Hanya sebagian kecil kebutuhan yang dapat dipenuhi produksi setempat.",
        "warna": "#a2704a",
    },
    "tidak": {
        "label": "Tidak diproduksi di sini",
        "arti": "Komoditas sumbernya tercatat tidak diproduksi di provinsi ini.",
        "warna": "#8b8f94",
    },
    "tanpa_data": {
        "label": "Tanpa data produksi",
        "arti": "Komoditas sumbernya tidak ada pada data produksi, jadi tidak diketahui, bukan berarti nol.",
        "warna": "#c9ccd1",
    },
}


def tingkat_lokal(isl):
    """Ubah nilai Indeks Sumber Lokal menjadi kunci penanda yang terbaca."""
    if isl is None:
        return "tanpa_data"
    if isl >= AMBANG_LOKAL_UTAMA:
        return "utama"
    if isl >= AMBANG_LOKAL_SEBAGIAN:
        return "sebagian"
    if isl > 0:
        return "sedikit"
    return "tidak"


# Keterbatasan data yang harus selalu terlihat
# Empat provinsi hasil pemekaran Papua belum memiliki survei Neraca Bahan
# Makanan sendiri, sehingga pipeline mewarisi nilai provinsi induknya. Nilai
# Indeks Pola Pangan Wilayah keempatnya karena itu identik dengan induknya,
# bukan hasil pengukuran di wilayah tersebut.
#
# Daftar ini dipakai menandai keluaran API dan tampilan, supaya keterbatasan
# tersebut tidak hanya tertulis di naskah tetapi juga terlihat pembaca.
IPW_WARISAN = {
    "Papua Selatan": "Papua",
    "Papua Tengah": "Papua",
    "Papua Pegunungan": "Papua",
    "Papua Barat Daya": "Papua Barat",
}

CATATAN_IPW_WARISAN = (
    "Provinsi ini belum memiliki survei Neraca Bahan Makanan sendiri karena "
    "baru terbentuk melalui pemekaran. Nilai pola pangannya mewarisi provinsi "
    "induk, sehingga menggambarkan wilayah induk, bukan hasil pengukuran di "
    "provinsi ini."
)


def ipw_warisan_dari(nama):
    """Nama provinsi induk bila nilai IPW-nya warisan, None bila terukur sendiri."""
    return IPW_WARISAN.get(nama_provinsi(nama))


# Daftar istilah dan singkatan
# Satu-satunya sumber kepanjangan singkatan. Halaman mana pun yang menyebut
# singkatan mengambil kepanjangannya dari sini, sehingga tidak mungkin ada
# dua halaman yang menuliskannya berbeda.
ISTILAH = [
    {
        "singkatan": "MBG",
        "panjang": "Makan Bergizi Gratis",
        "kelompok": "Program",
        "arti": (
            "Program pemerintah yang menyediakan makan bergizi bagi peserta "
            "didik. Penelitian ini memakai data program sebagai objek riset "
            "sistem rekomendasi, bukan sebagai bahan penilaian program."
        ),
    },
    {
        "singkatan": "AKG",
        "panjang": "Angka Kecukupan Gizi",
        "kelompok": "Gizi",
        "arti": (
            "Standar kecukupan zat gizi harian menurut kelompok umur, mengacu "
            "Peraturan Menteri Kesehatan Nomor 28 Tahun 2019. Dipakai sebagai "
            "target yang harus dipenuhi tiap menu."
        ),
    },
    {
        "singkatan": "TKPI",
        "panjang": "Tabel Komposisi Pangan Indonesia",
        "kelompok": "Gizi",
        "arti": (
            "Tabel rujukan kandungan gizi bahan pangan Indonesia terbitan 2017. "
            "Menjadi sumber angka energi, protein, lemak, dan karbohidrat tiap bahan."
        ),
    },
    {
        "singkatan": "AHP",
        "panjang": "Analytic Hierarchy Process",
        "kelompok": "Metode",
        "arti": (
            "Metode pembobotan kriteria lewat perbandingan berpasangan, "
            "diperkenalkan Saaty pada 1980. Dipakai menentukan seberapa besar "
            "bobot alergi, intoleransi, dan fobia dalam skor risiko."
        ),
    },
    {
        "singkatan": "K-Means",
        "panjang": "K-Means Clustering",
        "kelompok": "Metode",
        "arti": (
            "Metode pengelompokan yang membagi data ke sejumlah kelompok "
            "berdasarkan kemiripan. Dipakai mengelompokkan provinsi menurut "
            "profil kesehatan peserta didik."
        ),
    },
    {
        "singkatan": "ISL",
        "panjang": "Indeks Sumber Lokal",
        "kelompok": "Wilayah",
        "arti": (
            "Ukuran 0 sampai 1 yang menyatakan seberapa besar kebutuhan sebuah "
            "bahan dapat dipenuhi produksi provinsi itu sendiri. Dihitung dari "
            "data produksi pangan, bukan dari data konsumsi."
        ),
    },
    {
        "singkatan": "IPW",
        "panjang": "Indeks Pola Pangan Wilayah",
        "kelompok": "Wilayah",
        "arti": (
            "Perbandingan pangsa energi tiap kelompok pangan di satu provinsi "
            "terhadap rata-rata nasional. Nilai 1 berarti pola pangannya sama "
            "dengan rata-rata nasional, di atas 1 berarti lebih bertumpu pada "
            "kelompok tersebut. Ini indeks pola, bukan jumlah."
        ),
    },
    {
        "singkatan": "NBM",
        "panjang": "Neraca Bahan Makanan",
        "kelompok": "Wilayah",
        "arti": (
            "Publikasi Badan Pangan Nasional yang mencatat ketersediaan pangan "
            "dalam kilokalori per kapita per hari. Yang diukur adalah pangan "
            "yang tersedia untuk dikonsumsi, bukan yang benar-benar dimakan."
        ),
    },
    {
        "singkatan": "SPPG",
        "panjang": "Satuan Pelayanan Pemenuhan Gizi",
        "kelompok": "Program",
        "arti": (
            "Unit yang menyiapkan dan menyalurkan makanan pada program Makan "
            "Bergizi Gratis. Petugasnya adalah pengguna utama yang dituju "
            "situs ini."
        ),
    },
    {
        "singkatan": "Silhouette Score",
        "panjang": "Skor Silhouette",
        "kelompok": "Metode",
        "arti": (
            "Ukuran seberapa rapat anggota satu kelompok dan seberapa "
            "terpisah dari kelompok lain. Nilainya minus satu sampai satu, "
            "makin mendekati satu makin baik pengelompokannya."
        ),
    },
    {
        "singkatan": "Davies-Bouldin Index",
        "panjang": "Indeks Davies-Bouldin",
        "kelompok": "Metode",
        "arti": (
            "Ukuran kualitas pengelompokan yang membandingkan sebaran di "
            "dalam kelompok terhadap jarak antar kelompok. Berbeda dari "
            "Silhouette, nilai yang makin kecil justru makin baik."
        ),
    },
    {
        "singkatan": "Uji Kruskal-Wallis",
        "panjang": "Uji Kruskal-Wallis",
        "kelompok": "Metode",
        "arti": (
            "Uji statistik untuk memeriksa apakah beberapa kelompok berbeda "
            "nyata, tanpa mensyaratkan data menyebar normal. Dipakai menguji "
            "perbedaan profil kesehatan antar jenjang."
        ),
    },
    {
        "singkatan": "Waterfall",
        "panjang": "Model Waterfall",
        "kelompok": "Metode",
        "arti": (
            "Model pengembangan perangkat lunak yang menjalankan tahapan "
            "secara berurutan, dari penetapan kebutuhan sampai penempatan, "
            "dengan tiap tahap diselesaikan sebelum tahap berikutnya."
        ),
    },
    {
        "singkatan": "BPS",
        "panjang": "Badan Pusat Statistik",
        "kelompok": "Sumber data",
        "arti": "Lembaga resmi penyedia statistik nasional, sumber data produksi pangan.",
    },
    {
        "singkatan": "API",
        "panjang": "Application Programming Interface",
        "kelompok": "Teknis",
        "arti": (
            "Antarmuka yang memungkinkan satu program mengambil data dari "
            "program lain. Data peserta didik diambil lewat antarmuka milik "
            "Kementerian Pendidikan Dasar dan Menengah."
        ),
    },
    {
        "singkatan": "WHO",
        "panjang": "World Health Organization",
        "kelompok": "Sumber data",
        "arti": "Organisasi Kesehatan Dunia, rujukan daftar alergen pangan utama.",
    },
    {
        "singkatan": "FAO",
        "panjang": "Food and Agriculture Organization",
        "kelompok": "Sumber data",
        "arti": "Organisasi Pangan dan Pertanian PBB, rujukan bersama WHO untuk daftar alergen.",
    },

    # Ditambahkan 10 Agustus 2026
    # Istilah berikut muncul pada halaman Metodologi yang menjelaskan tiap
    # langkah perhitungan. Sebelumnya pembaca menjumpai istilah ini tanpa ada
    # tempat untuk mencari artinya.

    # Kelompok Data
    {
        "singkatan": "Rate",
        "panjang": "Rate kondisi kesehatan",
        "kelompok": "Data",
        "arti": (
            "Jumlah kasus dibagi jumlah penerima manfaat pada satu provinsi dan "
            "jenjang. Dipakai agar provinsi berpenduduk besar tidak otomatis "
            "tampak paling berisiko hanya karena jumlah kasusnya banyak. "
            "Contohnya 230 kasus alergi dari 2.260 penerima menghasilkan rate "
            "0,101770."
        ),
    },
    {
        "singkatan": "Skor terbobot",
        "panjang": "Skor risiko terbobot",
        "kelompok": "Data",
        "arti": (
            "Gabungan ketiga rate memakai bobot AHP menjadi satu angka. Dipakai "
            "mengurutkan kelompok daerah sebelum diberi label Rendah, Sedang, "
            "dan Tinggi, bukan untuk menilai provinsi satu per satu."
        ),
    },
    {
        "singkatan": "Snapshot",
        "panjang": "Snapshot data",
        "kelompok": "Data",
        "arti": (
            "Salinan data pada satu saat tertentu. Seluruh angka situs ini "
            "berasal dari satu pengambilan, sehingga pengambilan pada tanggal "
            "berbeda akan memberi angka berbeda meski metodenya sama."
        ),
    },

    # Kelompok Metode
    {
        "singkatan": "Min-Max",
        "panjang": "Normalisasi Min-Max",
        "kelompok": "Metode",
        "arti": (
            "Pengubahan nilai ke rentang nol sampai satu dengan rumus nilai "
            "dikurangi terkecil, dibagi selisih terbesar dan terkecil. "
            "Dijalankan terpisah tiap jenjang, sehingga nilai satu berarti "
            "tertinggi di antara sesama jenjangnya, bukan berarti seluruh "
            "peserta didik mengalami kondisi tersebut."
        ),
    },
    {
        "singkatan": "Mann-Whitney",
        "panjang": "Uji Mann-Whitney",
        "kelompok": "Metode",
        "arti": (
            "Uji yang membandingkan dua kelompok tanpa mensyaratkan sebaran "
            "normal. Dipakai sebagai lanjutan Kruskal-Wallis untuk mengetahui "
            "pasangan jenjang mana yang benar-benar berbeda."
        ),
    },
    {
        "singkatan": "Bonferroni",
        "panjang": "Koreksi Bonferroni",
        "kelompok": "Metode",
        "arti": (
            "Penyesuaian nilai p ketika banyak uji dijalankan sekaligus. Nilai "
            "p dikalikan jumlah uji supaya perbedaan yang muncul karena "
            "kebetulan tidak terbaca sebagai temuan."
        ),
    },
    {
        "singkatan": "Spearman",
        "panjang": "Korelasi Spearman",
        "kelompok": "Metode",
        "arti": (
            "Ukuran keeratan hubungan dua besaran berdasarkan urutan "
            "peringkatnya, bukan nilai aslinya. Bernilai -1 sampai 1. Dipakai "
            "menguji apakah bahan yang banyak diproduksi suatu provinsi memang "
            "lebih sering muncul pada menunya."
        ),
    },
    {
        "singkatan": "Jaccard",
        "panjang": "Indeks Jaccard",
        "kelompok": "Metode",
        "arti": (
            "Perbandingan jumlah anggota yang sama terhadap jumlah anggota "
            "gabungan dua himpunan. Dipakai mengukur seberapa mirip daftar "
            "bahan menu dua provinsi; makin kecil nilainya makin beragam "
            "menunya."
        ),
    },
    {
        "singkatan": "CRISP-DM",
        "panjang": "Cross-Industry Standard Process for Data Mining",
        "kelompok": "Metode",
        "arti": (
            "Kerangka kerja baku pengolahan data yang berjalan enam tahap, "
            "mulai dari memahami sasaran sampai penerapan. Dipakai menyusun "
            "urutan pengerjaan pipeline penelitian ini."
        ),
    },

    # Kelompok Gizi
    {
        "singkatan": "Alergen",
        "panjang": "Alergen pangan",
        "kelompok": "Gizi",
        "arti": (
            "Zat pada bahan pangan yang memicu reaksi kekebalan tubuh, mulai "
            "dari gatal sampai anafilaksis yang mengancam jiwa. Rujukan WHO dan "
            "FAO memuat 14 alergen, dan delapan kelompok yang paling lazim "
            "dijumpai menentukan skor keparahan bahan."
        ),
    },
    {
        "singkatan": "Intoleransi",
        "panjang": "Intoleransi pangan",
        "kelompok": "Gizi",
        "arti": (
            "Ketidakmampuan mencerna zat tertentu, misalnya laktosa pada susu "
            "atau gluten pada gandum. Tidak melibatkan sistem kekebalan dan "
            "umumnya tidak mengancam jiwa, tetapi mengganggu kenyamanan dan "
            "konsentrasi belajar."
        ),
    },
    {
        "singkatan": "Fobia makanan",
        "panjang": "Neofobia pangan",
        "kelompok": "Gizi",
        "arti": (
            "Kecenderungan menolak makanan tertentu karena rasa, bau, tekstur, "
            "atau warnanya, bukan karena alasan medis. Memengaruhi keragaman "
            "asupan gizi meski tidak menimbulkan reaksi tubuh."
        ),
    },
    {
        "singkatan": "Rasio AKG",
        "panjang": "Rasio kecukupan gizi",
        "kelompok": "Gizi",
        "arti": (
            "Perbandingan kandungan gizi satu menu terhadap targetnya. Nilai 1 "
            "berarti tepat memenuhi target. Menu diterima bila keempat "
            "rasionya berada antara 0,80 dan 1,20."
        ),
    },

    # Kelompok Wilayah
    {
        "singkatan": "Pangsa",
        "panjang": "Pangsa produksi",
        "kelompok": "Wilayah",
        "arti": (
            "Bagian sebuah komoditas di antara komoditas sekelompoknya pada "
            "provinsi yang sama. Dipakai menggantikan jumlah mutlak agar "
            "provinsi besar tidak selalu unggul dan kekhasan wilayah kecil "
            "tetap terlihat."
        ),
    },
    {
        "singkatan": "Kelompok pembanding",
        "panjang": "Kelompok pembanding komoditas",
        "kelompok": "Wilayah",
        "arti": (
            "Sekumpulan komoditas yang dapat saling menggantikan perannya pada "
            "menu, misalnya padi, sagu, jagung, dan umbi sebagai sumber "
            "karbohidrat. Pangsa hanya dihitung di dalam kelompok, sebab "
            "membandingkan beras dengan daging tidak bermakna."
        ),
    },
    {
        "singkatan": "Tahun acuan",
        "panjang": "Tahun acuan kelompok pembanding",
        "kelompok": "Wilayah",
        "arti": (
            "Tahun terakhir yang datanya tersedia untuk seluruh anggota satu "
            "kelompok pembanding. Diperlukan agar pangsa tidak dihitung dari "
            "tahun yang berbeda-beda, misalnya daging ayam 2024 dibandingkan "
            "daging sapi 2023."
        ),
    },
]

# Pencarian cepat singkatan ke kepanjangan, dipakai filter template.
ISTILAH_PETA = {i["singkatan"]: i["panjang"] for i in ISTILAH}


def panjangkan(singkatan):
    """Kembalikan 'Kepanjangan (SINGKATAN)' untuk penyebutan pertama."""
    panjang = ISTILAH_PETA.get(singkatan)
    return f"{panjang} ({singkatan})" if panjang else singkatan


# Logging
LOG_LEVEL = os.getenv("MBG_LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv(
    "MBG_LOG_FORMAT",
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Server
HOST = os.getenv("MBG_HOST", "127.0.0.1")
PORT = int(os.getenv("MBG_PORT", "5000"))


# Normalisasi nama provinsi
# Satu nama provinsi muncul dalam tiga bentuk di basis data:
#   provinces.provinsi        -> "Prov. D.K.I. Jakarta"
#   menu_provinsi.prov        -> "D.K.I. Jakarta"
#   ingredient_locality.key   -> "dki jakarta"
# Dua fungsi di bawah menjadi satu-satunya tempat penerjemahan itu terjadi,
# supaya tidak ada lagi tambalan regex yang tersebar di template dan JavaScript.

def nama_provinsi(nama):
    """Buang awalan 'Prov. ' untuk ditampilkan ke pengguna."""
    if not nama:
        return ""
    return nama.replace("Prov. ", "").strip()


def kunci_provinsi(nama):
    """Ubah nama provinsi apa pun bentuknya menjadi kunci ingredient_locality."""
    if not nama:
        return ""
    bersih = nama_provinsi(nama).lower().replace(".", "")
    return " ".join(bersih.split())
