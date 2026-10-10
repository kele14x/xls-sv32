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
if [[ ! -f "downloads/$archive" ]]; then
    echo "Downloading $url"
    curl -fL --retry 3 -o "downloads/$archive" "$url"
fi
echo "$checksum  downloads/$archive" | sha256sum -c -

if [[ ! -d "$installed" ]]; then
    echo "Extracting to $installed"
    tar -xzf "downloads/$archive" -C tools/
fi
ln -sfn "$(basename "$installed")" tools/xls

grep -q "$checksum  $archive" downloads/SHA256SUMS 2>/dev/null || \
    echo "$checksum  $archive" >> downloads/SHA256SUMS

"$project_dir/bin/xls" interpreter_main --version
echo "XLS installed at tools/xls"
