#!/usr/bin/env bash
#
# pin-actions.sh: ganti tag action pada workflow dengan SHA commit.
#
# Alasan. Tag pada GitHub bukan penanda tetap. Pemiliknya, atau siapa pun yang
# berhasil mengambil alih akunnya, dapat memindahkan tag ke commit lain kapan
# saja. Repo yang menulis `uses: sesuatu@v4` akan ikut menjalankan commit baru
# itu tanpa ada perubahan apa pun di repo sendiri. Pada Maret 2026, 75 tag
# milik aquasecurity/trivy-action dipindahkan ke commit yang memuat pencuri
# kredensial dengan cara persis seperti itu.
#
# SHA commit tidak dapat dipindahkan. Setelah dipatok, Dependabot yang
# memperbaruinya lewat pull request yang dapat dibaca sebelum digabung.
#
# Cara pakai:
#   bash deploy/pin-actions.sh              # tampilkan saja, tidak mengubah
#   bash deploy/pin-actions.sh --tulis      # tulis perubahannya
#
# Butuh: git, curl, dan koneksi ke api.github.com.
# Bila punya GITHUB_TOKEN, ekspor lebih dulu agar tidak kena batas laju.

set -euo pipefail

TULIS=0
[ "${1:-}" = "--tulis" ] && TULIS=1

AKAR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW_DIR="$AKAR/.github/workflows"

if [ ! -d "$WORKFLOW_DIR" ]; then
  echo "Folder workflow tidak ditemukan: $WORKFLOW_DIR" >&2
  exit 1
fi

sha_untuk() {
  local repo="$1" tag="$2" auth=()
  [ -n "${GITHUB_TOKEN:-}" ] && auth=(-H "Authorization: Bearer $GITHUB_TOKEN")

  # Tag anotasi menunjuk ke objek tag, bukan langsung ke commit. Dereferensi
  # dengan ^{} supaya yang didapat selalu SHA commit.
  curl --silent --show-error --fail "${auth[@]}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$repo/git/matching-refs/tags/$tag" \
  | grep -o '"sha": *"[0-9a-f]\{40\}"' \
  | tail -1 \
  | grep -o '[0-9a-f]\{40\}'
}

ADA_GAGAL=0

for berkas in "$WORKFLOW_DIR"/*.yml "$WORKFLOW_DIR"/*.yaml; do
  [ -e "$berkas" ] || continue
  echo "== $(basename "$berkas")"

  # Kumpulkan pasangan repo@tag yang belum berupa SHA 40 heksadesimal.
  while IFS= read -r rujukan; do
    repo="${rujukan%@*}"
    tag="${rujukan#*@}"

    if [[ "$tag" =~ ^[0-9a-f]{40}$ ]]; then
      echo "   sudah dipatok: $repo"
      continue
    fi

    if ! sha="$(sha_untuk "$repo" "$tag")" || [ -z "$sha" ]; then
      echo "   GAGAL mengambil SHA: $repo@$tag" >&2
      ADA_GAGAL=1
      continue
    fi

    echo "   $repo@$tag  ->  $sha"

    if [ "$TULIS" = "1" ]; then
      # Komentar versi dipertahankan supaya masih terbaca manusia, dan supaya
      # Dependabot tahu versi mana yang sedang dipakai.
      python3 - "$berkas" "$repo" "$tag" "$sha" <<'PY'
import re, sys
berkas, repo, tag, sha = sys.argv[1:5]
teks = open(berkas, encoding="utf-8").read()
pola = re.compile(rf"(uses:\s*){re.escape(repo)}@{re.escape(tag)}(?:\s*#[^\n]*)?")
teks = pola.sub(rf"\g<1>{repo}@{sha} # {tag}", teks)
open(berkas, "w", encoding="utf-8").write(teks)
PY
    fi
  done < <(grep -oE 'uses:[[:space:]]*[^[:space:]#]+@[^[:space:]#]+' "$berkas" \
           | sed 's/uses:[[:space:]]*//' | sort -u)
done

if [ "$TULIS" = "1" ]; then
  echo
  echo "Selesai ditulis. Periksa diff-nya sebelum commit:"
  echo "  git diff .github/workflows"
else
  echo
  echo "Belum ada yang diubah. Jalankan ulang dengan --tulis untuk menerapkan."
fi

exit "$ADA_GAGAL"
