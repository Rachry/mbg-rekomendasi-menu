/* ===========================================================================
   data_produksi.js  —  Tab Produksi Pangan pada halaman data mentah

   Tabelnya memuat lebih dari lima belas ribu baris, sehingga tidak pernah
   dikirim sekaligus. Sisi depan meminta seratus baris tiap kali dan menambah
   sisanya lewat tombol muat lebih banyak. Penyaringan dijalankan di sisi
   server, bukan di peramban, supaya muatan tiap permintaan tetap wajar.
   =========================================================================== */

(function () {
  "use strict";

  var M = window.MBG || {};
  var panel = document.getElementById("panel-produksi");
  if (!panel || !M.apiProduksiMentah) return;

  var tabBtns = document.querySelectorAll(".tab-btn");
  var panels = {
    kesehatan: document.getElementById("panel-kesehatan"),
    produksi: panel
  };

  var selProv = document.getElementById("p-provinsi");
  var selKel = document.getElementById("p-kelompok");
  var selKom = document.getElementById("p-komoditas");
  var selTh = document.getElementById("p-tahun");
  var tbody = document.getElementById("p-tbody");
  var hitung = document.getElementById("p-count");
  var btnLagi = document.getElementById("p-lagi");
  var progres = document.getElementById("p-progres");
  var btnCsv = document.getElementById("p-csv");
  var btnReset = document.getElementById("p-reset");

  var BATAS = 100;
  var terkumpul = [];      // seluruh baris yang sudah dimuat
  var total = 0;
  var adaLagi = false;
  var opsiSiap = false;
  var sedangMuat = false;

  // Bantu

  function angkaID(nilai, desimal) {
    if (nilai === null || nilai === undefined) return "—";
    var n = Number(nilai);
    if (!isFinite(n)) return String(nilai);
    var teks = n.toLocaleString("id-ID", {
      minimumFractionDigits: desimal === undefined ? 0 : desimal,
      maximumFractionDigits: desimal === undefined ? 2 : desimal
    });
    return teks;
  }

  function rapiKata(teks) {
    if (!teks) return "—";
    return String(teks).replace(/_/g, " ");
  }

  function isiPilihan(sel, daftar, ambilNilai, ambilLabel) {
    // Simpul dibangun satu per satu, bukan lewat innerHTML, sebab nilainya
    // berasal dari basis data dan tidak boleh ditafsirkan sebagai markup.
    while (sel.options.length > 1) sel.remove(1);
    daftar.forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = ambilNilai(item);
      opt.textContent = ambilLabel(item);
      sel.appendChild(opt);
    });
  }

  function penyaringAktif() {
    var q = [];
    if (selProv.value) q.push("provinsi=" + encodeURIComponent(selProv.value));
    if (selKel.value) q.push("kelompok=" + encodeURIComponent(selKel.value));
    if (selKom.value) q.push("komoditas=" + encodeURIComponent(selKom.value));
    if (selTh.value) q.push("tahun=" + encodeURIComponent(selTh.value));
    return q;
  }

  // Penggambaran

  function gambar() {
    tbody.innerHTML = "";

    if (!terkumpul.length) {
      var kosong = document.createElement("tr");
      var sel = document.createElement("td");
      sel.className = "empty-state";
      sel.colSpan = 6;
      sel.textContent = "Tidak ada baris yang cocok dengan penyaring ini. "
        + "Coba longgarkan salah satu pilihan.";
      kosong.appendChild(sel);
      tbody.appendChild(kosong);
      hitung.textContent = "0 baris";
      progres.textContent = "";
      btnLagi.hidden = true;
      return;
    }

    terkumpul.forEach(function (row) {
      var tr = document.createElement("tr");
      [
        row.provinsi,
        rapiKata(row.komoditas),
        rapiKata(row.kelompok),
        row.tahun,
        angkaID(row.produksi_ton, 1),
        row.satuan
      ].forEach(function (nilai, i) {
        var td = document.createElement("td");
        td.textContent = nilai === null || nilai === undefined ? "—" : String(nilai);
        if (i === 4) td.className = "num";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });

    hitung.textContent = angkaID(total) + " baris";
    progres.textContent = "Menampilkan " + angkaID(terkumpul.length)
      + " dari " + angkaID(total) + " baris.";
    btnLagi.hidden = !adaLagi;
  }

  // Pemuatan

  function muat(lanjutkan) {
    if (sedangMuat) return;
    sedangMuat = true;

    if (!lanjutkan) {
      terkumpul = [];
      tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Memuat…</td></tr>';
    }
    btnLagi.disabled = true;

    var q = penyaringAktif();
    q.push("batas=" + BATAS);
    q.push("offset=" + terkumpul.length);

    fetch(M.apiProduksiMentah + "?" + q.join("&"))
      .then(function (r) {
        if (!r.ok) throw new Error("status " + r.status);
        return r.json();
      })
      .then(function (data) {
        total = data.total;
        adaLagi = data.ada_lagi;
        terkumpul = terkumpul.concat(data.baris || []);
        gambar();
      })
      .catch(function () {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">'
          + "Gagal memuat data produksi. Coba muat ulang halaman.</td></tr>";
        progres.textContent = "";
        btnLagi.hidden = true;
      })
      .then(function () {
        sedangMuat = false;
        btnLagi.disabled = false;
      });
  }

  function muatOpsi() {
    if (opsiSiap) return Promise.resolve();
    return fetch(M.apiOpsiProduksi)
      .then(function (r) { return r.json(); })
      .then(function (o) {
        isiPilihan(selProv, o.provinsi,
          function (p) { return p.kunci; },
          function (p) { return p.nama; });
        isiPilihan(selKel, o.kelompok,
          function (k) { return k; }, rapiKata);
        isiPilihan(selKom, o.komoditas,
          function (k) { return k; }, rapiKata);
        isiPilihan(selTh, o.tahun,
          function (t) { return t; },
          function (t) { return String(t); });
        opsiSiap = true;
      })
      .catch(function () { /* penyaring tetap kosong, tabel tetap dapat dibaca */ });
  }

  // Peristiwa

  tabBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var nama = btn.getAttribute("data-tab");
      tabBtns.forEach(function (b) {
        var aktif = b === btn;
        b.classList.toggle("active", aktif);
        b.setAttribute("aria-selected", aktif ? "true" : "false");
      });
      Object.keys(panels).forEach(function (k) {
        if (panels[k]) panels[k].hidden = (k !== nama);
      });
      // Data produksi baru diminta saat tabnya benar-benar dibuka, supaya
      // pembaca yang hanya melihat profil kesehatan tidak ikut menanggung
      // permintaan yang tidak dipakainya.
      if (nama === "produksi" && !terkumpul.length && !sedangMuat) {
        muatOpsi().then(function () { muat(false); });
      }
    });
  });

  [selProv, selKel, selKom, selTh].forEach(function (sel) {
    sel.addEventListener("change", function () { muat(false); });
  });

  btnLagi.addEventListener("click", function () { muat(true); });

  btnReset.addEventListener("click", function () {
    [selProv, selKel, selKom, selTh].forEach(function (s) { s.value = ""; });
    muat(false);
  });

  btnCsv.addEventListener("click", function () {
    var judul = ["Provinsi", "Komoditas", "Kelompok", "Tahun", "Produksi (ton)", "Satuan"];
    var baris = [judul.join(",")];
    terkumpul.forEach(function (row) {
      baris.push([
        row.provinsi, row.komoditas, row.kelompok,
        row.tahun, row.produksi_ton, row.satuan
      ].map(function (v) {
        return '"' + String(v === null || v === undefined ? "" : v).replace(/"/g, '""') + '"';
      }).join(","));
    });
    var blob = new Blob([baris.join("\n")], { type: "text/csv;charset=utf-8;" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "mbg_produksi_pangan.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  });
})();
