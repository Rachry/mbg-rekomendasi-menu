# syntax=docker/dockerfile:1.7

# Build dua tahap: perkakas kompilasi dan cache pip tidak ikut ke image runtime.
#
# Base image dipatok ke digest, bukan ke tag. Tag seperti 3.11-slim-bookworm
# dipindahkan ke image baru setiap kali Debian atau CPython dirilis ulang, jadi
# dua build dengan Dockerfile yang sama dapat menghasilkan isi yang berbeda.
# Digest menunjuk satu manifest tertentu dan tidak dapat dipindahkan, sehingga
# build yang mengiringi naskah ini dapat diulang persis oleh penguji.
#
# Digest di bawah adalah manifest index python:3.11-slim-bookworm yang didorong
# 5 Agustus 2026, diambil dari registry pada 11 Agustus 2026. Dependabot yang
# dikonfigurasi di .github/dependabot.yml akan mengusulkan penggantinya lewat
# pull request setiap kali ada rilis baru. Memeriksa ulang secara manual:
#   docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim-bookworm

# Ditulis harfiah pada kedua FROM, bukan lewat ARG, sebab Dependabot hanya
# mengenali digest yang tertulis langsung pada baris FROM.

FROM python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# --require-hashes menolak paket yang isinya tidak cocok dengan lockfile.
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --prefix=/install -r requirements.lock


FROM python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS runtime

LABEL org.opencontainers.image.title="Sistem Rekomendasi Menu MBG" \
      org.opencontainers.image.description="K-Means + AHP + Flask" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    FLASK_ENV=production

# MBG_TRUSTED_PROXIES tidak diset di sini. Jumlah hop proxy berbeda tiap
# platform, dan nilai yang terlalu tinggi membuat X-Forwarded-For dapat
# dipalsukan. Bawaan config.py adalah 0. Lihat deploy/contoh.env.

WORKDIR /app

RUN groupadd --gid 10001 mbg \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin mbg

COPY --from=builder /install /usr/local

# pip, setuptools, dan wheel bawaan base image tidak dibutuhkan saat aplikasi
# berjalan, tetapi ikut terpindai sebagai kerentanan. Membuangnya menutup CVE
# pada wheel dan pada jaraco.context yang di-vendor setuptools, sekaligus
# menghilangkan pemasang paket dari container yang melayani permintaan.
#
# Dihapus dengan rm, bukan `pip uninstall`, sebab pip yang menghapus dirinya
# sendiri dapat berhenti di tengah dan menyisakan paket lain. Impor terakhir
# memastikan build gagal bila ada yang ternyata masih dibutuhkan.
RUN rm -rf /usr/local/lib/python3.11/site-packages/pip \
           /usr/local/lib/python3.11/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.11/site-packages/setuptools \
           /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.11/site-packages/pkg_resources \
           /usr/local/lib/python3.11/site-packages/wheel \
           /usr/local/lib/python3.11/site-packages/wheel-*.dist-info \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.* \
           /usr/local/bin/wheel \
    && python -c "import flask, gunicorn; from gunicorn.app.wsgiapp import WSGIApplication"

COPY --chown=10001:10001 . .

USER 10001:10001

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request,sys;\
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','5000')+'/health',timeout=4).status==200 else sys.exit(1)"]

# Bentuk exec agar Gunicorn menerima SIGTERM langsung. Pengaturan yang
# bergantung lingkungan dibaca dari gunicorn.conf.py.
CMD ["gunicorn", "app:app"]
