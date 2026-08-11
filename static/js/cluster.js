/* ===========================================================================
   cluster.js — Visualisasi profil kelompok daerah.

   Rancangan ini menggantikan radar chart dan bar chart bertumpuk pada versi
   sebelumnya. Tiga alasan penggantian:

   1. Radar memaksa dimensi yang rentangnya berbeda jauh berbagi satu sumbu.
      Pada data ini fobia berkisar 0,004 sampai 4,02 persen sementara alergi
      berkisar 1,04 sampai 11,26 persen, sehingga fobia tergencet mendekati
      pusat dan tidak menyampaikan apa pun.
   2. Radar mengkodekan besaran sebagai luas, yang tumbuh kuadratik sehingga
      melebih-lebihkan selisih. Bentuk poligonnya juga berubah hanya dengan
      menukar urutan sumbu, jadi bentuk itu artefak, bukan informasi.
   3. Posisi pada skala bersama adalah encoding yang paling akurat dibaca
      mata, sedangkan sudut dan luas termasuk paling sulit.

   Penggantinya panel kecil per dimensi, masing-masing pada skalanya sendiri,
   dengan angka pasti ditulis di samping batang. Digambar memakai HTML dan
   variabel CSS, bukan kanvas, supaya ikut mode gelap dan tetap tajam saat
   diperbesar untuk keperluan gambar naskah.
   =========================================================================== */

(function () {
  "use strict";
  var M = window.MBG;

  var DIMENSI = [
    {
      kunci: "mean_alergi",
      judul: "Alergi makanan",
      ket: "Bobot terbesar pada skor gabungan. Reaksi sistem kekebalan tubuh yang dapat berakibat serius."
    },
    {
      kunci: "mean_intoleransi",
      judul: "Intoleransi",
      ket: "Kesulitan mencerna komponen tertentu, misalnya laktosa atau gluten. Bukan reaksi kekebalan tubuh."
    },
    {
      kunci: "mean_fobia",
      judul: "Fobia makanan",
      ket: "Kecenderungan menolak makanan karena selera atau ketidakbiasaan, bukan alasan medis."
    },
    {
      kunci: "mean_weighted_score",
      judul: "Skor gabungan",
      ket: "Gabungan ketiga dimensi dengan bobot dari Analytic Hierarchy Process (AHP). Nilai inilah yang menentukan tingkat kewaspadaan."
    }
  ];

  var URUTAN = ["Tinggi", "Sedang", "Rendah"];

  function el(tag, kelas, teks) {
    var n = document.createElement(tag);
    if (kelas) n.className = kelas;
    if (teks !== undefined && teks !== null) n.textContent = String(teks);
    return n;
  }

  function persen(v, desimal) {
    return (v * 100).toFixed(desimal === undefined ? 2 : desimal) + "%";
  }

  function urutkan(rows) {
    return rows.slice().sort(function (a, b) {
      return URUTAN.indexOf(a.tingkat) - URUTAN.indexOf(b.tingkat);
    });
  }

  // Kartu ringkas tiap kelompok
  function gambarKartu(rows) {
    var wadah = document.getElementById("kl-kartu");
    wadah.textContent = "";
    urutkan(rows).forEach(function (r) {
      var k = el("div", "kl-kartu");
      k.style.setProperty("--c", r.warna);

      k.appendChild(el("h3", null, r.label_awam));
      k.appendChild(el("div", "kl-jumlah", r.n_provinsi));
      k.appendChild(el("div", "kl-ket", r.n_provinsi === 1 ? "provinsi" : "provinsi"));

      var skor = el("div", "kl-skor");
      skor.appendChild(document.createTextNode("Skor gabungan "));
      skor.appendChild(el("b", null, persen(r.mean_weighted_score)));
      k.appendChild(skor);

      // Kluster beranggota satu provinsi disebutkan terbuka, sebab
      // keanggotaannya rawan berubah bila data diperbarui.
      if (r.n_provinsi === 1) {
        k.appendChild(el("p", "kl-peringatan",
          "Kelompok ini hanya beranggota satu provinsi, sehingga keanggotaannya " +
          "rawan berubah bila data diperbarui."));
      }
      wadah.appendChild(k);
    });
  }

  // Panel kecil per dimensi
  function gambarPanel(rows) {
    var wadah = document.getElementById("kl-panel");
    wadah.textContent = "";
    var terurut = urutkan(rows);

    DIMENSI.forEach(function (d) {
      var nilai = terurut.map(function (r) { return r[d.kunci] || 0; });
      // Sumbu tiap panel berdiri sendiri: nol sampai nilai tertinggi panel itu.
      var maks = Math.max.apply(null, nilai) || 1;

      var p = el("div", "kl-panel");
      p.appendChild(el("h3", null, d.judul));
      p.appendChild(el("span", "kl-sub", d.ket));

      terurut.forEach(function (r, i) {
        var baris = el("div", "kl-baris");
        baris.appendChild(el("span", "kl-nama", r.label_awam));

        var track = el("div", "kl-track");
        var isi = el("div", "kl-isi");
        isi.style.width = Math.max(1, (nilai[i] / maks) * 100) + "%";
        isi.style.background = r.warna;
        track.appendChild(isi);
        baris.appendChild(track);

        baris.appendChild(el("span", "kl-nilai", persen(nilai[i])));
        p.appendChild(baris);
      });

      var skala = el("div", "kl-skala");
      skala.appendChild(el("span", null, "0%"));
      skala.appendChild(el("span", null, persen(maks)));
      p.appendChild(skala);

      wadah.appendChild(p);
    });
  }

  // Perbandingan antar jenjang
  function gambarAntarJenjang(semua, jenjangAktif) {
    var wadah = document.getElementById("kl-antar");
    wadah.textContent = "";

    var perJenjang = {};
    semua.forEach(function (r) {
      (perJenjang[r.jenjang] = perJenjang[r.jenjang] || []).push(r);
    });

    // Skala dibuat sama untuk keempat jenjang agar besarnya dapat dibandingkan.
    var maks = Math.max.apply(null, semua.map(function (r) {
      return r.mean_weighted_score || 0;
    })) || 1;

    Object.keys(perJenjang).sort().forEach(function (j) {
      var kartu = el("div", "kl-antar-kartu" + (j === jenjangAktif ? " aktif" : ""));
      kartu.appendChild(el("h4", null, "Jenjang " + j));

      urutkan(perJenjang[j]).forEach(function (r) {
        // Tata letak dan tinggi batang diserahkan sepenuhnya ke CSS, supaya
        // penyesuaian tampilan cukup dilakukan di satu tempat dan batangnya
        // ikut memanjang saat kartunya melebar.
        var baris = el("div", "kl-baris");
        baris.appendChild(el("span", "kl-nama", r.tingkat));

        var track = el("div", "kl-track");
        var isi = el("div", "kl-isi");
        isi.style.width = Math.max(1, ((r.mean_weighted_score || 0) / maks) * 100) + "%";
        isi.style.background = r.warna;
        track.appendChild(isi);
        baris.appendChild(track);

        baris.appendChild(el("span", "kl-nilai", persen(r.mean_weighted_score, 1)));
        kartu.appendChild(baris);
      });
      wadah.appendChild(kartu);
    });
  }

  // Tabel angka pasti
  function gambarTabel(rows) {
    var tbody = document.getElementById("kl-tabel");
    tbody.textContent = "";
    urutkan(rows).forEach(function (r) {
      var tr = el("tr");

      var td = el("td");
      var titik = el("span", "kl-titik");
      titik.style.background = r.warna;
      td.appendChild(titik);
      td.appendChild(document.createTextNode(r.label_awam));
      tr.appendChild(td);

      tr.appendChild(el("td", "num", r.n_provinsi));
      tr.appendChild(el("td", "num", persen(r.mean_alergi)));
      tr.appendChild(el("td", "num", persen(r.mean_intoleransi)));
      tr.appendChild(el("td", "num", persen(r.mean_fobia)));
      tr.appendChild(el("td", "num", persen(r.mean_weighted_score)));
      tbody.appendChild(tr);
    });
  }

  // Daftar provinsi anggota
  function gambarDaftar(rows) {
    var wadah = document.getElementById("kl-daftar");
    wadah.textContent = "";
    urutkan(rows).forEach(function (r) {
      var kartu = el("div", "kl-daftar-kartu");
      kartu.style.setProperty("--c", r.warna);
      kartu.appendChild(el("h4", null,
        r.label_awam + " (" + r.n_provinsi + " provinsi)"));

      var daftar = el("div", "kl-prov");
      (r.provinces || []).forEach(function (p) {
        var a = document.createElement("a");
        a.href = "/provinsi/" + p.kode_prov;
        a.textContent = p.provinsi;
        daftar.appendChild(a);
      });
      if (!(r.provinces || []).length) {
        daftar.appendChild(el("span", "empty-state", "Daftar provinsi tidak tersedia."));
      }
      kartu.appendChild(daftar);
      wadah.appendChild(kartu);
    });
  }

  // Pemuatan
  var semuaJenjang = null;

  function muat(jenjang) {
    var muatEl = document.getElementById("kl-muat");
    var isiEl = document.getElementById("kl-isi");
    muatEl.hidden = false;
    muatEl.textContent = "Memuat data kelompok…";
    isiEl.hidden = true;

    var permintaan = [fetch(M.apiClusters + "?jenjang=" + encodeURIComponent(jenjang))
      .then(function (r) { if (!r.ok) throw new Error("gagal"); return r.json(); })];

    if (!semuaJenjang) {
      permintaan.push(fetch(M.apiClusters)
        .then(function (r) { if (!r.ok) throw new Error("gagal"); return r.json(); }));
    }

    Promise.all(permintaan)
      .then(function (hasil) {
        var rows = hasil[0];
        if (hasil.length > 1) semuaJenjang = hasil[1];

        gambarKartu(rows);
        gambarPanel(rows);
        gambarAntarJenjang(semuaJenjang, jenjang);
        gambarTabel(rows);
        gambarDaftar(rows);

        muatEl.hidden = true;
        isiEl.hidden = false;
      })
      .catch(function () {
        muatEl.textContent = "Gagal memuat data kelompok. Coba muat ulang halaman.";
      });
  }

  var sel = document.getElementById("c-jenjang");
  sel.addEventListener("change", function (e) { muat(e.target.value); });
  muat(sel.value);
})();
