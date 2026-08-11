/* ===========================================================================
   data.js  —  Tabel data mentah provinsi, dua mode: dengan/tanpa label ML
   =========================================================================== */

(function () {
  "use strict";
  var M = window.MBG;

  var selJenjang = document.getElementById("d-jenjang");
  var modeBtns = document.querySelectorAll(".mode-btn");
  var thead = document.getElementById("d-thead");
  var tbody = document.getElementById("d-tbody");
  var hitung = document.getElementById("d-count");
  var modeNote = document.getElementById("d-mode-note");
  var btnCsv = document.getElementById("d-csv");

  var mode = "mentah";   // "mentah" | "label"
  var dataTerkini = { kolom: [], baris: [] };

  // Label kolom yang lebih mudah dibaca daripada nama kolom basis data.
  var LABEL_KOLOM = {
    kode_prov: "Kode", jenjang: "Jenjang", provinsi: "Provinsi", tahun: "Tahun",
    jumlah_satuan_pendidikan: "Satuan pendidikan",
    jumlah_satpen_negeri: "Satpen negeri", jumlah_satpen_swasta: "Satpen swasta",
    jumlah_laki: "Siswa laki-laki", jumlah_perempuan: "Siswa perempuan",
    jumlah_penerima_manfaat: "Penerima manfaat",
    jumlah_alergi: "Kasus alergi", jumlah_intoleransi: "Kasus intoleransi",
    jumlah_fobia: "Kasus fobia", jumlah_kondisi_khusus: "Kondisi khusus",
    is_imputed: "Estimasi?",
    rate_alergi: "Rate alergi", rate_intoleransi: "Rate intoleransi",
    rate_fobia: "Rate fobia",
    Xa: "Xa (alergi ternormalisasi)", Xi: "Xi (intoleransi ternormalisasi)",
    Xf: "Xf (fobia ternormalisasi)", cluster: "Cluster (ID)",
    weighted_score: "Skor tertimbang", label_risiko: "Label risiko"
  };

  function labelKolom(k) { return LABEL_KOLOM[k] || k; }

  function formatSel(kolom, nilai) {
    if (nilai === null || nilai === undefined) return "—";
    if (kolom === "is_imputed") return nilai ? "Ya" : "Tidak";
    if (typeof nilai === "number" && !Number.isInteger(nilai)) return nilai.toFixed(4);
    return String(nilai);
  }

  function render() {
    thead.innerHTML = "";
    dataTerkini.kolom.forEach(function (k) {
      var th = document.createElement("th");
      th.textContent = labelKolom(k);
      thead.appendChild(th);
    });

    tbody.innerHTML = "";
    if (!dataTerkini.baris.length) {
      tbody.innerHTML = '<tr><td class="empty-state">Tidak ada data.</td></tr>';
      hitung.textContent = "0 baris";
      return;
    }
    dataTerkini.baris.forEach(function (row) {
      var tr = document.createElement("tr");
      if (row.is_imputed) tr.classList.add("row-imputed");
      dataTerkini.kolom.forEach(function (k) {
        var td = document.createElement("td");
        td.textContent = formatSel(k, row[k]);
        if (k === "label_risiko" && row[k]) {
          // Dibangun sebagai simpul, bukan string HTML: nilai berasal dari
          // basis data dan tidak boleh ditafsirkan sebagai markup.
          td.textContent = "";
          var pill = document.createElement("span");
          pill.className = "pill pill-" + String(row[k]).toLowerCase();
          pill.textContent = row.label_awam || row[k];
          td.appendChild(pill);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    hitung.textContent = dataTerkini.baris.length + " baris";
  }

  function muat() {
    tbody.innerHTML = '<tr><td class="empty-state">Memuat…</td></tr>';
    var q = [];
    if (selJenjang.value) q.push("jenjang=" + encodeURIComponent(selJenjang.value));
    if (mode === "label") q.push("label=1");
    var url = M.apiDataMentah + (q.length ? "?" + q.join("&") : "");

    modeNote.textContent = mode === "label"
      ? "Menampilkan kolom hasil scraping ditambah kolom turunan model: rate per penerima manfaat, skor AHP ternormalisasi (Xa/Xi/Xf), hasil K-Means (cluster), dan label risiko akhir."
      : "Menampilkan kolom persis seperti hasil pengambilan dari API Kemendikdasmen, sebelum perhitungan model apa pun.";

    fetch(url).then(function (r) { return r.json(); }).then(function (data) {
      dataTerkini = data;
      render();
    }).catch(function () {
      tbody.innerHTML = '<tr><td class="empty-state">Gagal memuat data.</td></tr>';
    });
  }

  function csv() {
    var rows = [dataTerkini.kolom.map(labelKolom).join(",")];
    dataTerkini.baris.forEach(function (row) {
      rows.push(dataTerkini.kolom.map(function (k) {
        var v = formatSel(k, row[k]);
        return '"' + String(v).replace(/"/g, '""') + '"';
      }).join(","));
    });
    var blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "mbg_data_" + mode + (selJenjang.value ? "_" + selJenjang.value : "") + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  modeBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      modeBtns.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      mode = btn.getAttribute("data-mode");
      muat();
    });
  });

  selJenjang.addEventListener("change", muat);
  btnCsv.addEventListener("click", csv);

  muat();
})();
