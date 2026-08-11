/* ===========================================================================
   provinsi.js  —  Accordion jenjang dan pemuatan kartu menu per jenjang.

   Menu kini disusun per provinsi, jadi permintaan ke API menyertakan nama
   provinsi. Sebelumnya halaman ini menampilkan menu tingkat nasional yang
   kebetulan setingkat, bukan menu provinsi yang sedang dibuka.
   =========================================================================== */

(function () {
  "use strict";
  var M = window.MBG;
  var sudahDimuat = {};

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

  function kartuMenu(m) {
    var a = document.createElement("a");
    a.className = "menu-card";
    a.href = M.menuUrlBase + encodeURIComponent(m.menu_id);

    var atas = el("div", "menu-card-top");
    atas.style.background = m.warna;
    a.appendChild(atas);

    var body = el("div", "menu-card-body");
    body.appendChild(el("h4", null, m.menu_label));

    var makro = el("div", "macro-line");
    makro.appendChild(el("span", null, Math.round(m.energi_kkal) + " kkal"));
    makro.appendChild(el("span", null, "P " + Math.round(m.protein_g) + "g"));
    makro.appendChild(el("span", null, "L " + Math.round(m.lemak_g) + "g"));
    makro.appendChild(el("span", null, "K " + Math.round(m.karbo_g) + "g"));
    if (m.isl !== null && m.isl !== undefined) {
      makro.appendChild(judulPanjang(el("span", null, "ISL " + Math.round(m.isl * 100) + "%")));
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

    if (m.bahan_ringkas && m.bahan_ringkas.length) {
      var kepingWadah = el("div", "keping-baris");
      m.bahan_ringkas.forEach(function (b) {
        var keping = el("span", "keping keping-" + b.lokal, b.nama_bahan);
        if (b.lokal === "utama") keping.title = "Diproduksi di provinsi ini";
        else if (b.lokal === "sebagian") keping.title = "Sebagian dari provinsi ini";
        kepingWadah.appendChild(keping);
      });
      body.appendChild(kepingWadah);
    }

    var baris = el("div", "badge-row");
    if (!m.halal) baris.appendChild(el("span", "badge badge-alergen", "non-halal"));
    m.alergen.forEach(function (x) {
      baris.appendChild(el("span", "badge badge-alergen", "Alergen: " + x));
    });
    m.intoleransi.forEach(function (x) {
      baris.appendChild(el("span", "badge badge-intoleransi", "Intoleransi: " + x));
    });
    if (m.fobia) {
      baris.appendChild(el("span", "badge badge-fobia", "sebagian anak mungkin kurang suka"));
    }
    if (!baris.childNodes.length) {
      baris.appendChild(el("span", "safe-tag", "Tanpa penanda bahan"));
    }
    body.appendChild(baris);

    a.appendChild(body);
    return a;
  }

  function muatMenu(section) {
    var jenjang = section.getAttribute("data-jenjang");
    var slot = section.querySelector("[data-menu-slot]");
    if (!slot || sudahDimuat[jenjang]) return;
    sudahDimuat[jenjang] = true;

    slot.textContent = "";
    slot.appendChild(el("p", "empty-state", "Memuat menu…"));

    var url = M.apiMenus +
      "?provinsi=" + encodeURIComponent(M.provinsi) +
      "&jenjang=" + encodeURIComponent(jenjang);

    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("gagal");
        return r.json();
      })
      .then(function (d) {
        var rows = d.data || d;
        slot.textContent = "";
        if (!rows.length) {
          slot.appendChild(el("p", "empty-state", "Belum ada menu untuk jenjang ini."));
          return;
        }
        rows.forEach(function (m) { slot.appendChild(kartuMenu(m)); });
      })
      .catch(function () {
        slot.textContent = "";
        slot.appendChild(el("p", "empty-state", "Gagal memuat menu. Coba muat ulang halaman."));
      });
  }

  document.querySelectorAll(".jenjang[data-jenjang]").forEach(function (section) {
    var head = section.querySelector(".jenjang-head");
    if (head && !head.disabled) {
      head.addEventListener("click", function () {
        var terbuka = section.classList.toggle("open");
        head.setAttribute("aria-expanded", terbuka ? "true" : "false");
        if (terbuka) muatMenu(section);
      });
    }
    if (section.classList.contains("open")) muatMenu(section);
  });
})();
