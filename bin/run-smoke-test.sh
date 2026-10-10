#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(uname -s)" == Darwin ]]; then
    exec orb -m "${XLS_VM:-ubuntu24}" -w "$project_dir" \
        bash "$project_dir/scripts/smoke-test.sh"
fi
exec bash "$project_dir/scripts/smoke-test.sh"
