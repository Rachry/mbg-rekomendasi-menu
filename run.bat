@echo off
chcp 65001 >nul
setlocal
title Web Sistem Rekomendasi Menu MBG

cd /d "%~dp0"

echo ================================================================
echo   Web Sistem Rekomendasi Menu MBG
echo ================================================================
echo.

:: ---------------------------------------------------------------------
:: Pemeriksaan awal
:: ---------------------------------------------------------------------
if not exist "venv\Scripts\activate.bat" (
    echo   [GAGAL] Environment belum disiapkan.
    echo.
    echo   Jalankan setup.bat terlebih dahulu, cukup sekali saja.
    echo.
    pause
    exit /b 1
)

if not exist "data\mbg_recommendations_provinsi.db" (
    echo   [GAGAL] Basis data tidak ditemukan di data\
    echo   Jalankan setup.bat untuk pesan lengkapnya.
    echo.
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"

:: ---------------------------------------------------------------------
:: Mode dipilih lewat argumen. Tanpa argumen memakai server produksi
:: (waitress) karena lebih tenang dan stabil untuk demonstrasi sidang.
::   run.bat          -> server produksi, tanpa pesan debug
::   run.bat dev      -> mode pengembangan, muat ulang otomatis saat kode berubah
::   run.bat uji      -> menjalankan pengujian, tidak menyalakan server
:: ---------------------------------------------------------------------
set MODE=%~1
if /i "%MODE%"=="uji" goto :uji
if /i "%MODE%"=="test" goto :uji
if /i "%MODE%"=="dev" goto :dev
goto :produksi

:: ---------------------------------------------------------------------
:uji
echo   Menjalankan pengujian...
echo.
python -m pytest tests -q
echo.
pause
exit /b 0

:: ---------------------------------------------------------------------
:dev
echo   Mode: PENGEMBANGAN
echo   Kode yang diubah akan dimuat ulang otomatis.
echo   Jangan pakai mode ini untuk demonstrasi.
echo.
echo   Alamat : http://127.0.0.1:5000
echo   Berhenti: tekan Ctrl+C
echo.
set FLASK_ENV=development
start "" http://127.0.0.1:5000
python app.py
goto :selesai

:: ---------------------------------------------------------------------
:produksi
echo   Mode: PRODUKSI (waitress)
echo.
echo   Alamat  : http://127.0.0.1:5000
echo   Berhenti: tekan Ctrl+C pada jendela ini
echo.
echo   Halaman pertama yang terbuka adalah Tentang. Ikuti tombol lanjut
echo   di bagian bawah untuk melewati tiga halaman penjelasan sebelum
echo   peta terbuka.
echo.
echo   Untuk mode pengembangan : run.bat dev
echo   Untuk menjalankan uji   : run.bat uji
echo.

:: Mode produksi mewajibkan kunci rahasia dari lingkungan. Di server, kunci
:: ini diisi lewat pengaturan platform dan tetap sama lintas restart. Untuk
:: menjalankan di laptop, kunci sekali pakai dibuat di sini supaya perintahnya
:: tetap satu klik tanpa melemahkan syarat di server.
for /f %%k in ('python -c "import secrets;print(secrets.token_hex(32))"') do set MBG_SECRET_KEY=%%k
set MBG_RILIS=lokal

:: Beri jeda agar server sempat menyala sebelum peramban dibuka,
:: supaya pengguna tidak melihat halaman gagal terhubung.
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"

python -m waitress --host=127.0.0.1 --port=5000 app:app
if errorlevel 1 (
    echo.
    echo   [PERINGATAN] waitress gagal dijalankan, beralih ke server bawaan Flask.
    echo.
    python app.py
)

:selesai
echo.
echo   Server berhenti.
pause
