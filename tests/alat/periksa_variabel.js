/* Menjalankan satu berkas skrip sisi depan di dalam lingkungan tiruan.
 *
 * `node --check` hanya memeriksa sintaks. Variabel yang dipakai tetapi tidak
 * pernah dideklarasikan lolos pemeriksaan itu, padahal ketika dijalankan di
 * peramban ia melempar ReferenceError dan menghentikan seluruh sisa berkas.
 *
 * Cacat semacam itu pernah terjadi: sisa rujukan ke kotak centang yang sudah
 * dihapus membuat pemasangan pendengar pencarian tidak pernah berjalan,
 * sehingga kotak Cari provinsi diam saja tanpa gejala apa pun.
 *
 * Skrip ini menjalankan berkas di dalam VM dengan DOM tiruan yang menerima
 * panggilan apa pun, lalu melaporkan ReferenceError bila ada.
 */
const fs = require("fs");
const vm = require("vm");

// Galat asinkron berasal dari DOM tiruan yang tidak sempurna, bukan dari cacat
// yang dicari, sehingga tidak boleh menghentikan proses.
process.on("unhandledRejection", () => {});
process.on("uncaughtException", (e) => {
  if (e && e.name === "ReferenceError") {
    console.log("REFERENCE_ERROR " + e.message);
    process.exit(2);
  }
});

const berkas = process.argv[2];
const kode = fs.readFileSync(berkas, "utf8");

// Objek yang menerima properti dan panggilan apa pun tanpa mengeluh, sehingga
// yang tersisa sebagai kegagalan hanyalah variabel yang benar-benar tidak ada.
function boneka() {
  const fn = function () { return boneka(); };
  return new Proxy(fn, {
    get(t, k) {
      if (k === Symbol.toPrimitive) return () => "";
      if (k === "then") return undefined;            // supaya tidak dikira Promise
      if (k === "length") return 0;
      if (k === "classList" || k === "style") return boneka();
      return boneka();
    },
    set() { return true; },
    apply() { return boneka(); },
    has() { return true; },
  });
}

const konteks = {
  document: boneka(),
  L: boneka(),
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
  console,
  setTimeout: () => 0,
  clearTimeout: () => {},
  Promise,
  URL: { createObjectURL: () => "", revokeObjectURL: () => {} },
  Blob: function () {},
  Number, Math, JSON, String, Array, Object, Date, isFinite, parseInt, parseFloat,
};
// `window` juga dijadikan boneka supaya panggilan seperti
// window.addEventListener tidak menghentikan penelusuran sebelum seluruh
// berkas sempat dijalankan. Yang dicari hanyalah ReferenceError.
konteks.window = boneka();
konteks.globalThis = konteks;
konteks.addEventListener = () => {};
konteks.matchMedia = () => boneka();
konteks.localStorage = boneka();
konteks.location = boneka();
konteks.encodeURIComponent = encodeURIComponent;
konteks.Blob = function () {};

try {
  vm.createContext(konteks);
  vm.runInContext(kode, konteks, { filename: berkas, timeout: 5000 });
  console.log("OK");
} catch (e) {
  // Dibandingkan lewat nama, bukan instanceof. Galat yang dilempar di dalam VM
  // berasal dari ranah lain, sehingga instanceof selalu bernilai salah.
  if (e && e.name === "ReferenceError") {
    console.log("REFERENCE_ERROR " + e.message);
    process.exit(2);
  }
  // Galat lain berasal dari DOM tiruan yang tidak sempurna, bukan dari cacat
  // variabel, sehingga tidak dianggap kegagalan.
  console.log("OK (galat lingkungan tiruan diabaikan: " + e.name + ")");
}
