@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Setup - Web Sistem Rekomendasi Menu MBG

cd /d "%~dp0"

echo ================================================================
echo   SETUP - Web Sistem Rekomendasi Menu MBG
echo ================================================================
echo.
echo   Skrip ini menyiapkan environment sekali saja. Setelah selesai,
echo   cukup jalankan run.bat setiap kali ingin membuka aplikasi.
echo.

:: ---------------------------------------------------------------- 1/5
echo [1/5] Memeriksa Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [GAGAL] Python tidak ditemukan.
    echo.
    echo   Pasang Python 3.9 atau lebih baru dari https://python.org
    echo   Saat memasang, centang "Add Python to PATH".
    echo   Tutup jendela ini lalu jalankan setup.bat lagi setelah memasang.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)
if !PYMAJOR! LSS 3 goto :versi_kurang
if !PYMAJOR! EQU 3 if !PYMINOR! LSS 9 goto :versi_kurang
echo       Python !PYVER! terdeteksi.
goto :lanjut_venv

:versi_kurang
echo.
echo   [GAGAL] Python !PYVER! terlalu lama. Dibutuhkan 3.9 atau lebih baru.
echo   Unduh versi terbaru dari https://python.org
echo.
pause
exit /b 1

:lanjut_venv
echo.

:: ---------------------------------------------------------------- 2/5
echo [2/5] Menyiapkan virtual environment...
if exist "venv\Scripts\python.exe" (
    echo       venv sudah ada, dipakai ulang.
) else (
    if exist "venv" rmdir /s /q "venv"
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo   [GAGAL] Tidak dapat membuat virtual environment.
        echo   Coba jalankan: python -m pip install --upgrade virtualenv
        echo.
        pause
        exit /b 1
    )
    echo       venv berhasil dibuat.
)
echo.

:: ---------------------------------------------------------------- 3/5
echo [3/5] Memasang pustaka yang dibutuhkan...
echo       Perlu koneksi internet. Proses ini bisa memakan 1-3 menit.
call "venv\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet --disable-pip-version-check
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo   [GAGAL] Pemasangan pustaka tidak selesai.
    echo   Periksa koneksi internet lalu jalankan setup.bat lagi.
    echo.
    pause
    exit /b 1
)
echo       Flask, waitress, pytest, dan coverage terpasang.
echo.

:: ---------------------------------------------------------------- 4/5
echo [4/5] Memeriksa basis data...
if not exist "data\mbg_recommendations_provinsi.db" (
    echo.
    echo   [GAGAL] Basis data tidak ditemukan.
    echo.
    echo   Berkas yang dicari:
    echo     data\mbg_recommendations_provinsi.db
    echo.
    echo   Berkas ini keluaran pipeline di Google Colab. Salin dari:
    echo     02_data\processed\database\mbg_recommendations_provinsi.db
    echo.
    pause
    exit /b 1
)
for %%f in ("data\mbg_recommendations_provinsi.db") do set DBSIZE=%%~zf
echo       Basis data ditemukan (!DBSIZE! byte).
echo.

:: ---------------------------------------------------------------- 5/5
echo [5/5] Menjalankan pengujian untuk memastikan semuanya benar...
python -m pytest tests -q
if errorlevel 1 (
    echo.
    echo   [PERINGATAN] Sebagian pengujian tidak lulus.
    echo   Aplikasi mungkin tetap bisa dijalankan, tetapi sebaiknya
    echo   periksa pesan di atas sebelum dipakai untuk sidang.
    echo.
    pause
    exit /b 1
)
echo.

echo ================================================================
echo   SETUP SELESAI
echo ================================================================
echo.
echo   Langkah berikutnya: jalankan run.bat
echo.
echo   Catatan: saat pertama membuka aplikasi, Anda akan diarahkan
echo   melewati tiga halaman penjelasan secara berurutan, yaitu
echo   Tentang, Data Mentah, lalu Metodologi. Ini disengaja.
echo.
pause
