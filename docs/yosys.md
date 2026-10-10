# Yosys toolchain

The project uses an unmodified Yosys 0.69 source release built for Linux x64,
with the bundled sv-elab/slang frontend and ABC
enabled. `config/tools/yosys-install.json` pins the source archive checksum,
source and dependency revisions, build options, and installed binary checksums.

`bin/yosys` runs `tools/yosys/bin/yosys` directly.
`tools/yosys` points to `yosys-0.69-linux-x64`. The installation
includes ABC and Yosys's runtime data files; it does not depend on the
disposable source/build directories.

```bash
./bin/yosys -V
./bin/yosys -p 'help read_slang'
```

## SystemVerilog input

Use `read_slang` for SystemVerilog with unpacked array ports, as XLS and
hand-written wrappers often use. `memory_map` lowers any unpacked register
arrays before optimization. This is the frontend a RISC-V synthesis flow would
use.

`read_verilog -sv` selects Yosys's older parser, even in a build with slang.
Use `read_slang` explicitly for comprehensive SystemVerilog support:

```bash
./bin/yosys -p 'read_slang --top my_top design.sv; synth -top my_top; check -assert'
```

Other Yosys installations are independent. Project scripts invoke the
local launcher explicitly and do not resolve Yosys through `PATH`.
Historical PPA reports retain the tool/frontend provenance of their original
runs; changing the frontend can change optimization, naming, and PPA results.

## Validation

The installation is valid when the launcher reports the pinned version and
`read_slang` is available. The OpenSTA integration test under `tests/tools`
exercises the shared Nangate45 library when it is installed.

```bash
./bin/yosys -V
./bin/yosys -p 'help read_slang'
```

A synthesis and power flow for the RV32I core is future work; the core is
currently validated with Icarus Verilog against a Python reference model.

## Rebuild in Ubuntu 24.04

Run from the project root on Ubuntu 24.04. The official release archive
contains Yosys, ABC, sv-elab, slang, and the other bundled libraries.

```bash
sudo apt-get install cmake g++ make ninja-build git python3 bison flex gawk \
  libffi-dev libreadline-dev tcl-dev zlib1g-dev libboost-dev libfmt-dev \
  libtommath-dev libtomlplusplus-dev
mkdir -p downloads build/tools/yosys/source
curl --fail --location --retry 3 \
  -o downloads/yosys-0.69-source.tar.gz \
  https://github.com/YosysHQ/yosys/releases/download/v0.69/yosys.tar.gz
python3 - <<'PY'
import hashlib
import json
import tarfile
from pathlib import Path
manifest = json.loads(Path('config/tools/yosys-install.json').read_text())
archive = Path('downloads') / manifest['archive']
assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['sha256']
with tarfile.open(archive) as source:
    source.extractall(manifest['source_directory'], filter='data')
PY
cmake -S build/tools/yosys/source -B build/tools/yosys/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/tools/yosys-0.69-linux-x64" \
  -DYOSYS_WITHOUT_SLANG=OFF -DYOSYS_WITHOUT_EDITLINE=ON \
  -DCMAKE_DISABLE_FIND_PACKAGE_Git=ON \
  -DYOSYS_CHECKOUT_INFO=143eb14f9cc55d6f8927e68523b0c9d2166ed02c \
  -DYOSYS_SLANG_REVISION=b4fd362f4c53dc8ffab6946b9f866a6ea89e366d \
  -DSLANG_REVISION=e222e7dc0250231312f14c37d47404a49df00fe2
cmake --build build/tools/yosys/build --parallel 4
cmake --install build/tools/yosys/build --strip
ln -sfn yosys-0.69-linux-x64 tools/yosys
./bin/yosys -V
```

The revision options supply accurate source and dependency metadata when building
from the release archive without Git submodule checkouts. They prevent CMake from
mistaking this workspace's Git revision for the bundled libraries' revisions.

Refresh the recorded executable checksums after rebuilding:

```bash
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
path = Path('config/tools/yosys-install.json')
manifest = json.loads(path.read_text())
manifest['binary_sha256'] = hashlib.sha256(Path(manifest['binary']).read_bytes()).hexdigest()
manifest['abc_binary_sha256'] = hashlib.sha256(Path('tools/yosys/bin/yosys-abc').read_bytes()).hexdigest()
path.write_text(json.dumps(manifest, indent=2) + '\n')
PY
```
