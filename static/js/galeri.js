/* ===========================================================================
   galeri.js  —  Galeri menu dengan penyaring provinsi, jenjang, dan tingkat.

   Kartu dibangun dengan createElement, bukan innerHTML. Nama menu dan nama
   bahan berasal dari basis data, dan menyusunnya sebagai teks membuatnya
   tidak mungkin ditafsirkan sebagai HTML.
   =========================================================================== */

(function () {
  "use strict";
  var M = window.MBG;
  var grid = document.getElementById("g-grid");
  var hitung = document.getElementById("g-count");
  var selProvinsi = document.getElementById("g-provinsi");
  var selJenjang = document.getElementById("g-jenjang");
  var selTingkat = document.getElementById("g-tingkat");
  var tombolLagi = document.getElementById("g-lagi");

  // Galeri memuat bertahap. Merender 945 kartu sekaligus membuat peramban
  // tersendat dan muatannya mendekati satu megabita, padahal jarang ada yang
  // menggulir sejauh itu.
  var SEKALI_MUAT = 60;
  var batas = SEKALI_MUAT;

  // ISL tampil sebagai singkatan karena kartu sempit; kepanjangannya
  // disediakan sebagai tooltip, dan lengkapnya ada di halaman Daftar Istilah.
  function judulPanjang(simpul) {
    simpul.title = "Indeks Sumber Lokal: seberapa besar kebutuhan bahan menu " +
                   "dapat dipenuhi produksi provinsi sendiri";
    return simpul;
  }

  function el(tag, kelas, teks) {
    var n = document.createElement(tag);
    if (kelas) n.className = kelas;
    if (teks !== undefined && teks !== null) n.textContent = String(teks);
    return n;
  }

  function kartu(m) {
    var a = document.createElement("a");
    a.className = "menu-card";
    a.href = M.menuUrlBase + encodeURIComponent(m.menu_id);

    var atas = el("div", "menu-card-top");
    atas.style.background = m.warna;
    a.appendChild(atas);

    var body = el("div", "menu-card-body");

    var head = el("div", "mhead");
    head.appendChild(el("span", "mjenjang", m.jenjang));
    head.appendChild(el("span", "mtingkat", m.label_awam));
    head.appendChild(el("span", "vtag vtag-balanced", m.provinsi));
    body.appendChild(head);

    body.appendChild(el("h4", null, m.menu_label));

    var makro = el("div", "macro-line");
    makro.appendChild(el("span", "mnutri", Math.round(m.energi_kkal) + " kkal"));
    makro.appendChild(el("span", "mnutri", "P " + Math.round(m.protein_g) + "g"));
    makro.appendChild(el("span", "mnutri", "L " + Math.round(m.lemak_g) + "g"));
    makro.appendChild(el("span", "mnutri", "K " + Math.round(m.karbo_g) + "g"));
    if (m.isl !== null && m.isl !== undefined) {
      makro.appendChild(judulPanjang(el("span", "mnutri", "ISL " + Math.round(m.isl * 100) + "%")));
    }
    if (m.bahan_lokal) {
      // Jumlah bahan yang benar-benar diproduksi di provinsi menu ini.
      var tl = el("span", "mnutri", m.bahan_lokal + " bahan lokal");
      tl.title = "Bahan yang sebagian besar kebutuhannya dapat dipenuhi " +
                 "produksi provinsi ini sendiri";
      tl.style.color = "#3f9d5b";
      makro.appendChild(tl);
    }
    body.appendChild(makro);

    // Bahan ditandai satu per satu supaya yang diproduksi setempat terlihat
    // sebelum kartu dibuka.
    if (m.bahan_ringkas && m.bahan_ringkas.length) {
      var kepingWadah = el("div", "keping-baris");
      m.bahan_ringkas.forEach(function (b) {
        var keping = el("span", "keping keping-" + b.lokal, b.nama_bahan);
        keping.title = b.lokal === "utama"
          ? "Diproduksi di " + m.provinsi
          : (b.lokal === "sebagian" ? "Sebagian dari " + m.provinsi : "");
        kepingWadah.appendChild(keping);
      });
      body.appendChild(kepingWadah);
    }

    var baris = el("div", "badge-row");
    if (!m.halal) {
      baris.appendChild(el("span", "badge badge-alergen", "non-halal"));
    }
    m.alergen.forEach(function (x) { baris.appendChild(el("span", "badge badge-alergen", x)); });
    m.intoleransi.forEach(function (x) { baris.appendChild(el("span", "badge badge-intoleransi", x)); });
    if (m.fobia) { baris.appendChild(el("span", "badge badge-fobia", "sering ditolak")); }
    if (!baris.childNodes.length) {
      baris.appendChild(el("span", "safe-tag", "Tanpa penanda alergen atau intoleransi"));
    }
    body.appendChild(baris);

    a.appendChild(body);
    return a;
  }

  function muat() {
    var q = [];
    if (selProvinsi.value) q.push("provinsi=" + encodeURIComponent(selProvinsi.value));
    if (selJenjang.value) q.push("jenjang=" + encodeURIComponent(selJenjang.value));
    if (selTingkat.value) q.push("tingkat=" + encodeURIComponent(selTingkat.value));
    q.push("batas=" + batas);
    var url = M.apiMenus + "?" + q.join("&");

    grid.textContent = "";
    grid.appendChild(el("p", "empty-state", "Memuat…"));

    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("gagal");
        return r.json();
      })
      .then(function (d) {
        var rows = d.data;
        grid.textContent = "";
        hitung.textContent = rows.length === d.total
          ? d.total + " menu"
          : "Menampilkan " + rows.length + " dari " + d.total + " menu";
        if (!rows.length) {
          grid.appendChild(el("p", "empty-state", "Tidak ada menu yang cocok dengan penyaring ini."));
          if (tombolLagi) tombolLagi.hidden = true;
          return;
        }
        rows.forEach(function (m) { grid.appendChild(kartu(m)); });
        if (tombolLagi) {
          tombolLagi.hidden = rows.length >= d.total;
          tombolLagi.textContent = "Muat " +
            Math.min(SEKALI_MUAT, d.total - rows.length) + " menu lagi";
        }
      })
      .catch(function () {
        grid.textContent = "";
        grid.appendChild(el("p", "empty-state", "Gagal memuat menu. Coba muat ulang halaman."));
      });
  }

  [selProvinsi, selJenjang, selTingkat].forEach(function (s) {
    s.addEventListener("change", function () { batas = SEKALI_MUAT; muat(); });
  });
  if (tombolLagi) {
    tombolLagi.addEventListener("click", function () {
      batas += SEKALI_MUAT;
      muat();
    });
  }
  muat();
})();
