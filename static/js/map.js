/* ===========================================================================
   map.js  —  Logika peta interaktif
   Membaca GeoJSON statis + data warna dari /api/provinces, lalu mewarnai,
   menyorot, dan menautkan tiap provinsi. Tidak ada perhitungan model di sini.
   =========================================================================== */

(function () {
  "use strict";
  var M = window.MBG;

  // Pengelompokan provinsi ke pulau, berdasarkan kode provinsi DB (FR-013).
  var PULAU = {
    Sumatera: [60000,70000,80000,90000,100000,110000,120000,260000,290000,310000],
    Jawa: [10000,20000,30000,40000,50000,280000],
    "Bali-Nusa": [220000,230000,240000],
    Kalimantan: [130000,140000,150000,160000,340000],
    Sulawesi: [170000,180000,190000,200000,330000],
    "Maluku-Papua": [210000,270000,250000,360000,370000,380000,390000]
  };

  var WARNA_KOSONG = "#d1d5db";
  var ARSIR_URL = null;  // diisi setelah map siap

  // Arsir (hatch pattern) untuk provinsi tanpa data
  function pasangArsir() {
    if (ARSIR_URL) return ARSIR_URL;
    // Cari SVG element Leaflet di overlay pane
    var svg = document.querySelector(".leaflet-overlay-pane svg");
    if (!svg) return null;
    try {
      var ns = "http://www.w3.org/2000/svg";
      var defs = svg.querySelector("defs");
      if (!defs) { defs = document.createElementNS(ns,"defs"); svg.insertBefore(defs, svg.firstChild); }
      if (document.getElementById("hatch-kosong")) { ARSIR_URL = "url(#hatch-kosong)"; return ARSIR_URL; }
      var p = document.createElementNS(ns,"pattern");
      p.id = "hatch-kosong";
      p.setAttribute("patternUnits","userSpaceOnUse");
      p.setAttribute("width","10"); p.setAttribute("height","10");
      p.setAttribute("patternTransform","rotate(45)");
      var r = document.createElementNS(ns,"rect");
      r.setAttribute("width","10"); r.setAttribute("height","10");
      r.setAttribute("fill","#f0f0f0");
      var l = document.createElementNS(ns,"line");
      l.setAttribute("x1","0"); l.setAttribute("y1","0");
      l.setAttribute("x2","0"); l.setAttribute("y2","10");
      l.setAttribute("stroke","#9ca3af"); l.setAttribute("stroke-width","2.5");
      p.appendChild(r); p.appendChild(l); defs.appendChild(p);
      ARSIR_URL = "url(#hatch-kosong)";
      return ARSIR_URL;
    } catch(e) { return null; }
  }

  var peta, lapisan;
  var dataWarna = {};   // kode_db -> {tingkat, label_awam, warna}
  var filterPulau = "", filterTingkat = "";

  // Lapisan peta
  // Dua lapisan memakai skala warna yang berbeda jenis. Kewaspadaan bersifat
  // kategori (tiga tingkat), produksi bersifat besaran (nol sampai maksimum),
  // sehingga tidak boleh memakai palet yang sama agar tidak tertukar maknanya.
  var lapisanAktif = "kewaspadaan";
  var dataProduksi = {};   // kode_db -> {total_ton, n_komoditas}
  var produksiMaks = 0;

  var SKALA_PRODUKSI = ["#f2f7f4", "#cfe3d6", "#9fcbb2", "#6bb08c", "#3f9d5b", "#2c7a45"];

  function warnaProduksi(ton) {
    if (!ton || produksiMaks <= 0) return "#e9ecef";
    // Skala akar pangkat: produksi antar provinsi timpang jauh (Jawa Timur
    // sekitar tiga kali Jawa Tengah), sehingga skala linear membuat hampir
    // seluruh provinsi tampak sama pucat.
    var r = Math.sqrt(ton / produksiMaks);
    var i = Math.min(SKALA_PRODUKSI.length - 1, Math.floor(r * SKALA_PRODUKSI.length));
    return SKALA_PRODUKSI[i];
  }

  function formatTon(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(1) + " juta ton";
    if (n >= 1e3) return (n / 1e3).toFixed(0) + " ribu ton";
    return Math.round(n) + " ton";
  }

  // --- Inisialisasi peta ----------------------------------------------------
  // Batas dunia: satu kali keliling bumi saja. Tanpa ini, peta bisa digeser
  // dan di-zoom out tanpa henti karena tile diulang terus secara horizontal.
  var BATAS_DUNIA = L.latLngBounds(L.latLng(-89, -180), L.latLng(89, 180));

  peta = L.map("peta", {
    renderer: L.svg({ padding: 0.5 }),
    zoomControl: true,
    attributionControl: true,
    minZoom: 4, maxZoom: 9,
    maxBounds: BATAS_DUNIA,
    maxBoundsViscosity: 1.0,   // dorongan keras: tidak bisa digeser melewati batas
    worldCopyJump: false
  }).setView([-2.5, 118], 5);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap, &copy; CARTO",
    subdomains: "abcd",
    noWrap: true,            // jangan ulang tile peta ke samping tanpa batas
    bounds: BATAS_DUNIA
  }).addTo(peta);

  // Saat ukuran kontainer berubah (termasuk akibat zoom browser), beri tahu
  // Leaflet agar peta dihitung ulang dan tidak tampak terpotong atau buram.
  window.addEventListener("resize", function () {
    if (peta) peta.invalidateSize();
  });

  // --- Pengambilan data ------------------------------------------------------
  function ambilWarna(jenjang) {
    var url = M.apiProvinces + (jenjang ? "?jenjang=" + encodeURIComponent(jenjang) : "");
    return fetch(url).then(function (r) { return r.json(); }).then(function (rows) {
      dataWarna = {};
      rows.forEach(function (p) { dataWarna[p.kode_prov] = p; });
    });
  }

  // --- Gaya tiap provinsi ----------------------------------------------------
  function gayaFitur(feature) {
    var kode = feature.properties.kode_db;
    var info = kode != null ? dataWarna[kode] : null;
    var tampil = true;

    if (filterPulau && PULAU[filterPulau].indexOf(kode) === -1) tampil = false;
    if (lapisanAktif === "kewaspadaan" && filterTingkat && (!info || info.tingkat !== filterTingkat)) {
      tampil = false;
    }

    var style = {
      fillOpacity: tampil ? 0.78 : 0.08,
      color: "#ffffff",
      weight: tampil ? 1 : 0.4,
      opacity: tampil ? 1 : 0.3
    };

    if (lapisanAktif === "produksi") {
      var prod = kode != null ? dataProduksi[kode] : null;
      style.fillColor = prod ? warnaProduksi(prod.total_ton) : (ARSIR_URL || WARNA_KOSONG);
    } else if (info) {
      style.fillColor = info.warna;
    } else {
      style.fillColor = ARSIR_URL || WARNA_KOSONG;
    }
    return style;
  }

  function gambarUlang() {
    if (lapisan) lapisan.setStyle(gayaFitur);
  }

  // --- Interaksi per fitur ---------------------------------------------------
  function aturFitur(feature, layer) {
    var p = feature.properties;
    var kode = p.kode_db;
    var info = kode != null ? dataWarna[kode] : null;
    // Nama dari API sudah bersih dari awalan "Prov. " (lihat config.nama_provinsi).
    // GeoJSON dipakai hanya sebagai cadangan untuk provinsi tanpa data.
    var nama = (info && info.provinsi) || (p.nama_db || p.PROVINSI || "").replace(/^Prov\.\s*/, "");
    var labelAwam = info ? info.label_awam : "Data belum tersedia";

    layer.bindTooltip(function () {
      // Dibangun ulang tiap kali muncul supaya isinya mengikuti lapisan aktif.
      var judul = "<strong>" + nama + "</strong>";
      if (lapisanAktif === "produksi") {
        var prod = kode != null ? dataProduksi[kode] : null;
        if (!prod) return judul + "<span>Data produksi belum tersedia</span>";
        var teks = formatTon(prod.total_ton) + " dari " + prod.n_komoditas + " komoditas";
        return judul + "<span>" + teks + "</span>";
      }
      return judul + "<span>" + labelAwam + "</span>";
    }, { className: "prov-tip", sticky: true, direction: "top" });

    layer.on({
      mouseover: function (e) {
        e.target.setStyle({ weight: 2.6, color: "#1d2b25" });
        e.target.bringToFront();
      },
      mouseout: function () { gambarUlang(); },
      click: function () {
        if (kode == null) return;
        // Tujuan klik mengikuti lapisan yang sedang tampil. Pada lapisan
        // produksi, membuka halaman menu akan menyesatkan karena yang
        // sedang dilihat pengguna adalah angka produksi, bukan menu.
        if (lapisanAktif === "produksi") {
          var nm = (info && info.provinsi) || nama;
          window.location.href = M.produksiUrlBase + "?provinsi=" + encodeURIComponent(nm);
        } else {
          window.location.href = M.provinceUrlBase + kode;
        }
      }
    });
  }

  // --- Muat GeoJSON + data, lalu render -------------------------------------
  Promise.all([
    fetch(M.geojsonUrl).then(function (r) { return r.json(); }),
    ambilWarna("")
  ]).then(function (hasil) {
    var geo = hasil[0];
    lapisan = L.geoJSON(geo, { style: gayaFitur, onEachFeature: aturFitur }).addTo(peta);
    pasangArsir();  // pasang pattern setelah renderer siap
    gambarUlang();   // re-apply style agar arsir terpakai
    try { peta.fitBounds(lapisan.getBounds(), { padding: [10, 10] }); } catch (e) {}
  });

  // --- Filter jenjang: ambil ulang warna lalu render (FR-014) ---------------
  document.getElementById("f-jenjang").addEventListener("change", function (e) {
    ambilWarna(e.target.value).then(gambarUlang);
  });

  // --- Penyaring pulau (FR-013) -------------------------------------------------
  document.getElementById("f-pulau").addEventListener("change", function (e) {
    filterPulau = e.target.value;
    gambarUlang();
    if (filterPulau && lapisan) {
      var grup = L.featureGroup();
      lapisan.eachLayer(function (l) {
        if (PULAU[filterPulau].indexOf(l.feature.properties.kode_db) !== -1) grup.addLayer(l);
      });
      try { peta.fitBounds(grup.getBounds(), { padding: [20, 20] }); } catch (e2) {}
    } else if (lapisan) {
      peta.fitBounds(lapisan.getBounds(), { padding: [10, 10] });
    }
  });

  // --- Pengalih lapisan: kewaspadaan atau produksi pangan -------------------
  var selLapisan = document.getElementById("f-lapisan");
  var selKelompok = document.getElementById("f-kelompok");
  var selTahun = document.getElementById("f-tahun");
  var grupSaring = document.getElementById("grup-saring");
  var kotakPeringatan = document.getElementById("legenda-peringatan");
  var grupKelompok = document.getElementById("grup-produksi");
  var grupTahun = document.getElementById("grup-tahun");
  var grupMenu = document.getElementById("grup-menu");
  var ketLapisan = document.getElementById("ket-lapisan");
  var legendaKewaspadaan = document.getElementById("legenda-kewaspadaan");
  var legendaProduksi = document.getElementById("legenda-produksi");
  var opsiProduksiDimuat = false;

  function gambarSkalaLegenda() {
    var kotak = document.getElementById("legenda-skala");
    if (!kotak) return;
    kotak.textContent = "";
    SKALA_PRODUKSI.forEach(function (w) {
      var s = document.createElement("span");
      s.className = "legend-step";
      s.style.background = w;
      kotak.appendChild(s);
    });
    var maks = document.getElementById("legenda-maks");
    if (maks) maks.textContent = produksiMaks ? formatTon(produksiMaks) : "-";
  }

  function ambilProduksi() {
    var q = [];
    if (selKelompok && selKelompok.value) q.push("kelompok=" + encodeURIComponent(selKelompok.value));
    if (selTahun && selTahun.value) q.push("tahun=" + encodeURIComponent(selTahun.value));
    return fetch("/api/produksi-peta" + (q.length ? "?" + q.join("&") : ""))
      .then(function (r) {
        if (!r.ok) throw new Error("gagal");
        return r.json();
      })
      .then(function (d) {
        dataProduksi = {};
        d.data.forEach(function (p) { dataProduksi[p.kode_prov] = p; });
        produksiMaks = d.maks_ton || 0;

        if (!opsiProduksiDimuat) {
          d.kelompok_tersedia.forEach(function (k) {
            var o = document.createElement("option");
            o.value = k;
            o.textContent = k.replace(/_/g, " ");
            selKelompok.appendChild(o);
          });
          d.tahun_tersedia.forEach(function (t) {
            var o = document.createElement("option");
            o.value = t; o.textContent = t;
            selTahun.appendChild(o);
          });
          opsiProduksiDimuat = true;
        }
        // Angka BPS ditampilkan apa adanya, jadi tidak ada peringatan
        // kewajaran yang perlu dimunculkan di legenda.
        if (kotakPeringatan) kotakPeringatan.hidden = true;
        gambarSkalaLegenda();
      });
  }

  function terapkanLapisan() {
    var produksi = lapisanAktif === "produksi";

    // Penyaring produksi hanya tampil pada lapisan produksi.
    grupKelompok.hidden = !produksi;
    grupTahun.hidden = !produksi;
    if (grupSaring) grupSaring.hidden = !produksi;

    // Jenjang dan tingkat kewaspadaan tidak berlaku bagi data produksi,
    // jadi disembunyikan seluruhnya, bukan sekadar dinonaktifkan.
    if (grupMenu) grupMenu.hidden = produksi;

    legendaKewaspadaan.hidden = produksi;
    legendaProduksi.hidden = !produksi;

    if (ketLapisan) {
      ketLapisan.textContent = produksi
        ? "Klik provinsi untuk melihat rincian komoditas yang diproduksi."
        : "Klik provinsi untuk melihat tingkat kewaspadaan dan menunya.";
    }

    if (produksi) {
      // Penyaring tingkat direset agar tidak menyisakan pewarnaan lama.
      filterTingkat = "";
      var ft = document.getElementById("f-tingkat");
      if (ft) ft.value = "";
      ambilProduksi().then(gambarUlang).catch(gambarUlang);
    } else {
      gambarUlang();
    }
  }

  if (selLapisan) {
    selLapisan.addEventListener("change", function (e) {
      lapisanAktif = e.target.value;
      terapkanLapisan();
    });
  }
  if (selKelompok) selKelompok.addEventListener("change", function () { ambilProduksi().then(gambarUlang); });
  if (selTahun) selTahun.addEventListener("change", function () { ambilProduksi().then(gambarUlang); });

  // --- Penyaring tingkat (FR-013) ----------------------------------------------
  document.getElementById("f-tingkat").addEventListener("change", function (e) {
    filterTingkat = e.target.value;
    gambarUlang();
  });

  // --- Atur ulang ------------------------------------------------------------
  document.getElementById("reset").addEventListener("click", function () {
    filterPulau = ""; filterTingkat = "";
    lapisanAktif = "kewaspadaan";
    if (selLapisan) selLapisan.value = "kewaspadaan";
    if (selKelompok) selKelompok.value = "";
    if (selTahun) selTahun.value = "";
    terapkanLapisan();
    document.getElementById("f-pulau").value = "";
    document.getElementById("f-jenjang").value = "";
    document.getElementById("f-tingkat").value = "";
    document.getElementById("cari").value = "";
    sembunyikanSaran();
    ambilWarna("").then(function () {
      gambarUlang();
      if (lapisan) peta.fitBounds(lapisan.getBounds(), { padding: [10, 10] });
    });
  });

  // --- Pencarian dengan saran (FR-012) --------------------------------------
  var inputCari = document.getElementById("cari");
  var kotakSaran = document.getElementById("saran");
  var timer = null;

  function sembunyikanSaran() { kotakSaran.classList.remove("show"); kotakSaran.innerHTML = ""; }

  function pusatkanKe(kode) {
    if (!lapisan) return;
    lapisan.eachLayer(function (l) {
      if (l.feature.properties.kode_db === kode) {
        try { peta.fitBounds(l.getBounds(), { padding: [40, 40] }); } catch (e) {}
        l.openTooltip();
      }
    });
  }

  inputCari.addEventListener("input", function () {
    var q = inputCari.value.trim();
    if (timer) clearTimeout(timer);
    if (q.length < 2) { sembunyikanSaran(); return; }
    timer = setTimeout(function () {
      fetch(M.apiSearch + "?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (rows) {
          if (!rows.length) { sembunyikanSaran(); return; }
          kotakSaran.innerHTML = "";
          rows.forEach(function (row) {
            var b = document.createElement("button");
            b.type = "button";
            b.textContent = row.provinsi;
            b.addEventListener("click", function () {
              inputCari.value = b.textContent;
              sembunyikanSaran();
              pusatkanKe(row.kode_prov);
              // Tujuan mengikuti lapisan yang sedang aktif, sama seperti
              // perilaku klik pada peta. Pada lapisan produksi, membuka
              // halaman tingkat kewaspadaan akan terasa seperti salah tempat.
              var tujuan = lapisanAktif === "produksi"
                ? M.produksiUrlBase + "?provinsi=" + encodeURIComponent(row.provinsi)
                : M.provinceUrlBase + row.kode_prov;
              // Buka detail setelah jeda singkat agar peta sempat bergerak.
              setTimeout(function () { window.location.href = tujuan; }, 350);
            });
            kotakSaran.appendChild(b);
          });
          kotakSaran.classList.add("show");
        });
    }, 200);
  });

  // --- Panel pencarian/filter bisa dilipat (collapsible) --------------------
  var panel = document.querySelector(".panel");
  var panelToggle = document.getElementById("panel-toggle");
  if (panel && panelToggle) {
    panelToggle.addEventListener("click", function () {
      var terlipat = panel.classList.toggle("collapsed");
      panelToggle.setAttribute("aria-expanded", terlipat ? "false" : "true");
      panelToggle.title = terlipat ? "Buka panel pencarian" : "Lipat panel pencarian";
    });
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".search-wrap")) sembunyikanSaran();
  });
})();
