#!/usr/bin/env bash
# Download and install the pinned XLS toolchain described by
# config/tools/xls-install.json. Intended for Linux x64.
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$project_dir/config/tools/xls-install.json"
cd "$project_dir"

readarray -t fields < <(python3 - "$manifest" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
for key in ("archive", "download_url", "sha256", "installed_directory"):
    print(m[key])
PY
)
archive="${fields[0]}"
url="${fields[1]}"
checksum="${fields[2]}"
installed="${fields[3]}"

mkdir -p downloads tools
if [[ -e tools/xls && ! -L tools/xls ]]; then
    echo "Refusing to replace tools/xls: expected a symlink" >&2
    exit 1
fi

download_tmp=""
staging=""
cleanup() {
    if [[ -n "$download_tmp" ]]; then rm -f -- "$download_tmp"; fi
    if [[ -n "$staging" ]]; then rm -rf -- "$staging"; fi
}
trap cleanup EXIT

verify_archive() {
    printf '%s  %s\n' "$checksum" "$1" | sha256sum -c --status -
}

validate_installation() {
    local directory="$1" tool
    [[ -s "$directory/xls/dslx/stdlib/std.x" ]] || return 1
    for tool in interpreter_main ir_converter_main opt_main codegen_main; do
        [[ -x "$directory/$tool" ]] || return 1
        "$directory/$tool" --version >/dev/null 2>&1 || return 1
    done
}

if [[ ! -f "downloads/$archive" ]] || ! verify_archive "downloads/$archive"; then
    echo "Downloading $url"
    download_tmp="$(mktemp downloads/.xls-download.XXXXXX)"
    curl -fL --retry 3 -o "$download_tmp" "$url"
    if ! verify_archive "$download_tmp"; then
        echo "XLS archive checksum mismatch" >&2
        exit 1
    fi
    mv -- "$download_tmp" "downloads/$archive"
    download_tmp=""
fi
echo "Verified downloads/$archive"

staging="$(mktemp -d tools/.xls-install.XXXXXX)"
if ! validate_installation "$installed"; then
    echo "Extracting to $installed"
    tar -xzf "downloads/$archive" -C "$staging"
    candidate="$staging/$(basename "$installed")"
    if ! validate_installation "$candidate"; then
        echo "XLS archive contains an incomplete or unusable installation" >&2
        exit 1
    fi
    if [[ -e "$installed" || -L "$installed" ]]; then
        mv -- "$installed" "$staging/previous"
    fi
    if ! mv -- "$candidate" "$installed"; then
        if [[ -e "$staging/previous" || -L "$staging/previous" ]]; then
            mv -- "$staging/previous" "$installed"
        fi
        exit 1
    fi
fi
ln -s "$(basename "$installed")" "$staging/default-link"
mv -Tf -- "$staging/default-link" tools/xls

grep -q "$checksum  $archive" downloads/SHA256SUMS 2>/dev/null || \
    echo "$checksum  $archive" >> downloads/SHA256SUMS

"$project_dir/bin/xls" interpreter_main --version
echo "XLS installed at tools/xls"
