"""
app.py
Titik masuk aplikasi Flask.

Cara menjalankan:
  Dev:  FLASK_ENV=development python app.py
  Prod: waitress-serve --host=0.0.0.0 --port=5000 app:app   (Windows)
        gunicorn app:app                                    (Linux)

Yang ditangani berkas ini:
  - Security headers pada setiap respons
  - Rate limiting per IP dengan token bucket
  - Pengenalan IP asli di belakang proxy (ProxyFix)
  - Logging permintaan
  - Health check
  - Penanganan galat tanpa membocorkan traceback
"""

import logging
import os
import secrets
import sqlite3
import time

from flask import (
    Flask, abort, g, jsonify, make_response, redirect, render_template, request,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from api import api
from pages import pages

# Logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format=config.LOG_FORMAT,
)
logger = logging.getLogger("mbg")


# Rate limiter: token bucket per IP.
# Saldo tidak boleh negatif, penolakan tidak menambah utang, dan pengisian
# memakai pecahan waktu penuh. Entri lama dibuang berkala agar kamus tidak
# tumbuh tanpa batas.
_ember: dict[str, tuple[float, float]] = {}   # ip -> (waktu_isi_terakhir, saldo)
_pembersihan_terakhir = 0.0


def _bersihkan_ember(sekarang):
    global _pembersihan_terakhir
    if sekarang - _pembersihan_terakhir < 60:
        return
    _pembersihan_terakhir = sekarang
    batas = sekarang - config.RATE_LIMIT_TTL_SECONDS
    for ip in [k for k, (t, _) in _ember.items() if t < batas]:
        _ember.pop(ip, None)


def _lolos_rate_limit(ip: str) -> bool:
    """False bila kuota IP ini habis."""
    kapasitas = float(config.RATE_LIMIT_PER_MINUTE)
    laju = kapasitas / 60.0                       # token per detik
    sekarang = time.monotonic()
    _bersihkan_ember(sekarang)

    terakhir, saldo = _ember.get(ip, (sekarang, kapasitas))
    # Pengisian memakai pecahan penuh, bukan dibulatkan ke bawah.
    saldo = min(kapasitas, saldo + (sekarang - terakhir) * laju)

    if saldo < 1.0:
        # Saldo tidak dikurangi lagi: penolakan tidak menambah utang.
        _ember[ip] = (sekarang, saldo)
        return False

    _ember[ip] = (sekarang, saldo - 1.0)
    return True


# Security headers
# Leaflet dan Chart.js dilayani dari /static, jadi CSP tidak perlu mengizinkan
# unpkg maupun jsdelivr. Yang tersisa dari luar hanya Google Fonts.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Permitted-Cross-Domain-Policies": "none",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _susun_csp(nonce: str) -> str:
    """Susun Content-Security-Policy dengan nonce yang berbeda tiap respons.

    Tiap tag <script> membawa nonce yang sama dengan yang ada di header, dan
    'strict-dynamic' menyertakan skrip yang dimuat oleh skrip tepercaya.

    style-src masih mengizinkan 'unsafe-inline' karena template memakai atribut
    style= yang tidak dapat membawa nonce. CSS yang disisipkan tidak dapat
    menjalankan kode, jadi risikonya di bawah script-src.
    """
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://*.tile.openstreetmap.org "
        "https://*.tile.osm.org https://*.basemaps.cartocdn.com; "
        "connect-src 'self'; "
        # object-src menutup <object>, <embed>, dan <applet>. Aplikasi ini tidak
        # memakainya sama sekali, dan ketiganya adalah jalur lama untuk
        # menjalankan kode yang sering terlewat.
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

# Gerbang penjelasan wajib.
# Pengunjung melewati tiga halaman berurutan sebelum peta dan menu terbuka:
# batasan penelitian, data mentah, lalu metodologi. Urutannya ditegakkan di
# sisi server; tiap langkah punya route sendiri yang menaikkan penanda
# kemajuan.
#
# Ini gerbang keterbacaan, bukan kendali akses. Data tetap dapat diambil lewat
# /api/.
COOKIE_ALUR = "mbg_alur"

# Penanda rilis. Cookie yang membawa penanda berbeda dianggap sisa deploy lama
# dan kemajuannya dikembalikan ke nol, sehingga alur diulang tiap penerbitan.
#
# Nilainya harus sama di seluruh worker. Penanda yang diacak per proses membuat
# cookie terbitan satu worker ditolak worker lain. config.RILIS diturunkan dari
# SHA commit yang disediakan platform, atau dari SECRET_KEY sebagai cadangan.
PENANDA_JALAN = config.RILIS

ALUR = [
    {"langkah": 1, "jalur": "/tentang", "judul": "Tentang", "berikut": "/data"},
    {"langkah": 2, "jalur": "/data", "judul": "Data Mentah", "berikut": "/metodologi"},
    {"langkah": 3, "jalur": "/metodologi", "judul": "Metodologi", "berikut": "/"},
]

# Syarat minimum penanda kemajuan untuk membuka tiap halaman alur.
SYARAT_ALUR = {"/tentang": 0, "/data": 1, "/metodologi": 2}

# Selalu terbuka. Empat jalur, masing-masing dengan alasannya:
#   /health       probe platform harus dapat menjangkaunya tanpa mengikuti alur
#   /istilah      halaman rujukan, dibuka dari halaman alur itu sendiri
#   /robots.txt   perayap tidak membawa cookie dan tidak mengikuti alur. Bila
#                 ikut dialihkan, yang terbaca perayap adalah halaman Tentang,
#                 bukan aturan pengindeksan, sehingga aturannya tidak pernah
#                 sampai. Terverifikasi terjadi sebelum jalur ini dikecualikan.
#   /favicon.ico  diminta peramban di luar navigasi biasa
JALUR_SELALU_TERBUKA = ("/health", "/istilah", "/robots.txt", "/favicon.ico")


def _kemajuan_alur(request):
    """Baca kemajuan dari cookie. Nilai rusak atau sesi lama dianggap nol.

    Isi cookie berbentuk "penanda:langkah". Penanda yang tidak cocok dengan
    proses yang sedang berjalan berarti cookie itu sisa dari sesi sebelumnya,
    sehingga alur penjelasan diulang dari awal.
    """
    nilai = request.cookies.get(COOKIE_ALUR, "")
    if ":" not in nilai:
        return 0
    penanda, _, langkah = nilai.partition(":")
    if penanda != PENANDA_JALAN:
        return 0
    try:
        return max(0, min(len(ALUR), int(langkah)))
    except (TypeError, ValueError):
        return 0


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # Angka desimal ditulis dengan koma, mengikuti kaidah bahasa Indonesia.
    # Dijadikan penapis Jinja supaya tiap templat tidak menuliskannya sendiri
    # dan tidak ada halaman yang memakai titik sementara halaman lain memakai
    # koma.
    @app.template_filter("angka")
    def _angka(nilai, desimal=1):
        if nilai is None:
            return config.LABEL_KOSONG
        try:
            teks = f"{float(nilai):,.{desimal}f}"
        except (TypeError, ValueError):
            return str(nilai)
        # Format Python memakai koma untuk ribuan dan titik untuk desimal,
        # jadi keduanya ditukar lewat penanda sementara.
        return teks.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    # Ditegakkan Werkzeug, sehingga permintaan chunked tanpa Content-Length
    # ikut terbatasi. Pemeriksaan manual di api.py dulu bisa dilewati.
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    if not os.path.exists(config.DB_PATH):
        raise FileNotFoundError(
            f"Basis data tidak ditemukan di {config.DB_PATH}. "
            "Pastikan mbg_recommendations_provinsi.db ada di folder data/."
        )

    # Di belakang Nginx, request.remote_addr selalu 127.0.0.1 sehingga rate
    # limit berlaku untuk seluruh situs digabung, bukan per pengunjung.
    # ProxyFix membaca X-Forwarded-For, tetapi hanya bila memang ada proxy
    # tepercaya di depan (MBG_TRUSTED_PROXIES).
    if config.TRUSTED_PROXY_COUNT > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=config.TRUSTED_PROXY_COUNT,
            x_proto=config.TRUSTED_PROXY_COUNT,
            x_host=config.TRUSTED_PROXY_COUNT,
        )

    # Awal permintaan.
    # Pencatat waktu didaftarkan lebih dulu agar g._mulai tetap terisi meskipun
    # permintaan berikutnya ditolak rate limiter.
    @app.before_request
    def _catat_waktu_mulai():
        g._mulai = time.monotonic()
        # Satu nonce per permintaan, dipakai bersama oleh header dan seluruh
        # tag <script> pada halaman itu.
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.before_request
    def _periksa_rate_limit():
        if request.path.startswith("/static/") or request.path == "/health":
            return None
        ip = request.remote_addr or "127.0.0.1"
        if not _lolos_rate_limit(ip):
            logger.warning("Rate limit terlampaui: %s %s", ip, request.path)
            if request.path.startswith("/api/"):
                return jsonify({"error": "Terlalu banyak permintaan. Coba lagi sebentar."}), 429
            return render_template(
                "500.html",
                kode=429,
                judul="Terlalu banyak permintaan",
                pesan="Permintaan dari jaringan ini sedang dibatasi. Coba lagi beberapa detik lagi.",
            ), 429
        return None

    @app.before_request
    def _gerbang_penjelasan():
        """Pastikan tiga halaman penjelasan dilalui berurutan."""
        if request.path.startswith(("/static/", "/api/", "/lanjut/")):
            return None
        if request.path in JALUR_SELALU_TERBUKA:
            return None
        # Permintaan yang bukan meminta HTML tidak dialihkan.
        if not request.accept_mimetypes.accept_html:
            return None

        kemajuan = _kemajuan_alur(request)

        # Halaman alur: hanya boleh dibuka bila langkah sebelumnya sudah dilalui.
        if request.path in SYARAT_ALUR:
            if kemajuan >= SYARAT_ALUR[request.path]:
                return None
            # Lompat terlalu jauh: kembalikan ke langkah yang seharusnya.
            return redirect(ALUR[kemajuan]["jalur"])

        # Halaman lain: hanya terbuka setelah ketiga langkah selesai.
        if kemajuan < 3:
            return redirect(ALUR[kemajuan]["jalur"])
        return None

    @app.route("/lanjut/<int:langkah>")
    def lanjut(langkah):
        """Tandai satu langkah alur selesai lalu antar ke halaman berikutnya.

        Penanda diset di sisi server, bukan lewat JavaScript pada atribut
        onclick seperti versi sebelumnya, supaya urutannya dapat diuji dan
        tidak bergantung pada skrip yang mungkin gagal dimuat.
        """
        if langkah < 1 or langkah > len(ALUR):
            abort(404)
        tahap = ALUR[langkah - 1]
        # Penanda tidak pernah mundur bila pengunjung membuka ulang halaman lama.
        baru = max(langkah, _kemajuan_alur(request))
        respons = make_response(redirect(tahap["berikut"]))
        # Tanpa max_age, cookie berlaku sebatas sesi peramban.
        respons.set_cookie(
            COOKIE_ALUR, f"{PENANDA_JALAN}:{baru}",
            path="/", httponly=True, samesite="Lax",
            secure=request.is_secure,
        )
        return respons

    @app.route("/ulangi-panduan")
    def ulangi_panduan():
        """Hapus penanda alur supaya panduan dapat dibaca ulang dari awal."""
        respons = make_response(redirect("/tentang"))
        respons.delete_cookie(COOKIE_ALUR, path="/")
        return respons

    # Akhir permintaan
    @app.after_request
    def _security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        response.headers.setdefault(
            "Content-Security-Policy", _susun_csp(g.get("csp_nonce", ""))
        )

        # HSTS hanya dikirim pada koneksi terenkripsi. Dikirim di localhost,
        # header ini memaksa HTTPS untuk seluruh localhost sampai penyimpanan
        # HSTS peramban dibersihkan manual.
        #
        # preload tidak dicantumkan: mengeluarkan domain dari daftar preload
        # butuh berbulan-bulan.
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        if request.path.startswith("/static/"):
            # Aset statis boleh disimpan browser satu jam. Berkas yang sering
            # berubah sudah memakai penanda versi (?v=) di templatenya.
            response.headers["Cache-Control"] = "public, max-age=3600"
        else:
            # Halaman dan API selalu diambil ulang: isinya bergantung pada
            # filter yang dipilih pengguna.
            response.headers["Cache-Control"] = "no-store"

        response.headers.pop("Server", None)
        return response

    @app.after_request
    def _log_response(response):
        if request.path.startswith("/static/"):
            return response
        mulai = g.get("_mulai")
        durasi = f"{(time.monotonic() - mulai) * 1000:.0f}ms" if mulai else "?"
        logger.info(
            "%s %s → %d (%s)",
            request.method, request.path, response.status_code, durasi,
        )
        return response

    # Konteks template
    @app.context_processor
    def _konteks_alur():
        """Sediakan keadaan alur ke seluruh template, termasuk base.html."""
        jalur = request.path
        tahap = next((t for t in ALUR if t["jalur"] == jalur), None)
        return {
            "alur": ALUR,
            "alur_total": len(ALUR),
            "alur_tahap": tahap,
            "alur_kemajuan": _kemajuan_alur(request),
            "alur_selesai": _kemajuan_alur(request) >= len(ALUR),
            # Dipakai tiap tag <script> sebagai nonce="{{ csp_nonce }}".
            # Tanpa atribut itu, skripnya tidak akan dijalankan peramban.
            "csp_nonce": g.get("csp_nonce", ""),
        }

    # Blueprint
    app.register_blueprint(pages)
    app.register_blueprint(api)

    # Health check
    @app.route("/health")
    def health():
        """Liveness probe: pastikan basis data bisa dijangkau."""
        try:
            import db as _db
            ringkas = _db.ringkasan()
            return jsonify({
                "status": "ok",
                "rilis": config.RILIS,
                "menu": ringkas["total_menu"],
                "provinsi": ringkas["total_provinsi"],
            })
        except Exception as e:
            # Detail galat masuk ke log, bukan ke badan respons. Versi
            # sebelumnya mengembalikan str(e) apa adanya, dan pesan galat
            # SQLite memuat jalur lengkap berkas basis data di server. Endpoint
            # ini terbuka untuk publik karena probe platform harus dapat
            # menjangkaunya tanpa autentikasi, jadi apa pun yang dikembalikan
            # di sini terbaca siapa saja.
            logger.exception("Health check gagal")
            return jsonify({"status": "degraded"}), 503

    # Berkas kecil di akar
    @app.route("/robots.txt")
    def robots():
        """Minta mesin pencari tidak mengindeks web ini.

        Ini web pendamping penelitian, bukan sumber rujukan publik. Angka di
        dalamnya terikat pada satu commit dan dapat berubah, sehingga kutipan
        yang diambil mesin pencari berpotensi menyesatkan. Aturan ini adalah
        permintaan, bukan penghalang: perayap yang tidak patuh tetap dapat
        membacanya.
        """
        return app.response_class(
            "User-agent: *\nDisallow: /\n", mimetype="text/plain"
        )

    @app.route("/favicon.ico")
    def favicon():
        """Balas permintaan favicon supaya log tidak dipenuhi galat 404.

        Setiap kunjungan peramban meminta berkas ini. Tanpa route-nya, tiap
        kunjungan menghasilkan satu baris 404 yang mengaburkan galat sungguhan
        saat log dibaca untuk menelusuri masalah.
        """
        return redirect(url_for("static", filename="favicon.svg"), code=301)

    # Penanganan galat
    def _galat(kode, judul, pesan, e=None):
        if request.path.startswith("/api/"):
            return jsonify({"error": pesan}), kode
        return render_template("500.html", kode=kode, judul=judul, pesan=pesan), kode

    @app.errorhandler(400)
    def _400(e):
        return _galat(400, "Permintaan tidak dipahami",
                      "Permintaan tidak dapat diproses. Periksa kembali isian filter.")

    @app.errorhandler(404)
    def _404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Tidak ditemukan"}), 404
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def _413(e):
        return _galat(413, "Permintaan terlalu besar",
                      "Isian yang dikirim melebihi batas ukuran.")

    @app.errorhandler(500)
    def _500(e):
        logger.exception("500: %s %s", request.method, request.path)
        return _galat(500, "Terjadi kesalahan",
                      "Terjadi kesalahan internal. Silakan muat ulang halaman.")

    @app.errorhandler(sqlite3.Error)
    def _galat_db(e):
        logger.exception("Galat basis data: %s %s", request.method, request.path)
        return _galat(500, "Basis data tidak dapat dibaca",
                      "Basis data sedang tidak dapat dibaca.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=config.DEBUG, host=config.HOST, port=config.PORT)
