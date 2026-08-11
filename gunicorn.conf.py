"""Konfigurasi Gunicorn.

Dibaca otomatis bila berada di direktori kerja, sehingga perintah start cukup
`gunicorn app:app`. Nilai yang berbeda antarlingkungan dibaca dari environment.
"""

import os

# PaaS menyuntikkan nomor port lewat PORT dan menolak deployment yang mengikat
# ke port lain.
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"

# Satu worker dengan banyak thread. Gerbang alur dan pembatas laju menyimpan
# status di memori proses, jadi beberapa worker berarti beberapa salinan status
# yang tidak saling tahu. Bebannya juga didominasi I/O SQLite, bukan CPU.
# Naikkan WEB_CONCURRENCY hanya setelah status tersebut dipindah ke penyimpanan
# bersama.
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
threads = int(os.getenv("MBG_THREADS", "8"))
worker_class = "gthread"

timeout = int(os.getenv("MBG_TIMEOUT", "30"))
graceful_timeout = 15
keepalive = 65          # lebih panjang dari batas idle load balancer

# Daur ulang berkala sebagai jaring pengaman terhadap kebocoran memori.
max_requests = int(os.getenv("MBG_MAX_REQUESTS", "1000"))
max_requests_jitter = 100

# Tanda hubung berarti stdout dan stderr, yang dibaca sistem log platform.
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("MBG_LOG_LEVEL", "info").lower()

# %(h)s mencatat alamat pengunjung sebagaimana dibaca ProxyFix, jadi log akses
# memang memuat alamat IP. Header X-Forwarded-For mentahnya tidak dicatat,
# sebab isinya seluruh rantai proxy dan tidak menambah informasi apa pun untuk
# penelusuran. Ganti %(h)s dengan tanda hubung bila alamat pengunjung tidak
# boleh tercatat sama sekali.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms "%(a)s"'

# /dev/shm dipakai karena /tmp bisa tidak dapat ditulis pada container
# berfilesystem read-only.
worker_tmp_dir = "/dev/shm"  # nosec B108
preload_app = True
