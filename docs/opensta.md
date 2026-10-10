# OpenSTA toolchain

The default analyzer is an **OpenSTA development snapshot (source version 3.1.0)**,
built from official Parallax upstream
commit [`7b261909c1730d963252142e136daaa0199e333c`](https://github.com/parallaxsw/OpenSTA/commit/7b261909c1730d963252142e136daaa0199e333c),
dated October 9, 2026. `config/tools/opensta-install.json` pins its full commit,
source archive, SHA-256 checksums, compiler, and installed dependency versions.
The source is unpatched; `patches` is empty.

`bin/sta` runs `tools/opensta/sta` directly on Linux. `tools/opensta` points to
`opensta-3.1.0-g7b261909c173-linux-x64`. CUDD 3.0.0 is linked statically and
Eigen 5.0.1 supplies headers at build time. The installed executable uses
Homebrew's Tcl 8.6 and the host's zlib, C++ runtime, and standard system
libraries. It has no runtime dependency on files under `build/`.

## Build dependencies

Homebrew supplies the packages listed in upstream's `Brewfile`. CUDD comes
from the `mht208/formal` tap named in that file. The verified Linux build used:

| Dependency | Installed version |
| --- | --- |
| GCC | 15.2.0, system compiler |
| CMake | 4.4.4 |
| Bison | 3.8.2 |
| Flex | 2.6.4, Homebrew revision 2 |
| SWIG | 4.5.1 |
| Eigen | 5.0.1 |
| Tcl/Tk | 8.6.18, `tcl-tk@8` |
| CUDD | 3.0.0, `mht208/formal/cudd` |

GCC provides C++20 `std::format`, so this build needs no separate fmt library.
Homebrew installs the Tcl header at `include/tcl-tk/tcl.h`; pass that path
explicitly to CMake. Pass the CUDD static archive explicitly as well, so the
result does not require a CUDD shared library at runtime.

## Power activity

The verified upstream power analyzer retains explicit pin annotations during
propagation and uses annotated gated-clock pulse density. The tests exercise
the public `set_power_activity -pins` command against Nangate45 cells.

The integration tests check that a measured cell-output annotation survives
power propagation, and that gated clocks retain 2, 1, 0.5, and 0 transitions
per cycle. Both checks use the installed analyzer and Nangate45 library:

```bash
python3 -m unittest discover -s tests/tools -p 'test_*.py' -v
```

These tests require OpenSTA and the Nangate45 library to be installed. The
October 9 snapshot passed both tests, including all four gated-clock activity
cases. A RISC-V power/timing flow is future work; the RV32I core uses only the
XLS and simulation toolchain today.

## Rebuild on Linux with Homebrew

Run from the project root with a C++20 compiler and Homebrew available. For a
fresh checkout, fetch the pinned source revision:

```bash
mkdir -p build/tools/opensta/source
git -C build/tools/opensta/source init
git -C build/tools/opensta/source fetch --depth=1 \
  https://github.com/parallaxsw/OpenSTA.git \
  7b261909c1730d963252142e136daaa0199e333c
git -C build/tools/opensta/source checkout --detach FETCH_HEAD
```

Install dependencies, configure, and build. Disabling Homebrew's GitHub API
lookups avoids an unnecessary GitHub CLI authentication lookup for this public
source build:

```bash
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_GITHUB_API=1 \
  brew bundle --file=build/tools/opensta/source/Brewfile

cmake -S build/tools/opensta/source -B build/tools/opensta/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DUSE_TCL_READLINE=OFF \
  -DCMAKE_PREFIX_PATH="$(brew --prefix eigen)" \
  -DCUDD_DIR="$(brew --prefix mht208/formal/cudd)" \
  -DCUDD_LIB="$(brew --prefix mht208/formal/cudd)/lib/libcudd.a" \
  -DCUDD_HEADER="$(brew --prefix mht208/formal/cudd)/include/cudd.h" \
  -DTCL_LIBRARY="$(brew --prefix tcl-tk@8)/lib/libtcl8.6.so" \
  -DTCL_HEADER="$(brew --prefix tcl-tk@8)/include/tcl-tk/tcl.h"
cmake --build build/tools/opensta/build --parallel 8
```

The source version remains `3.1.0` across development commits; the full commit
in the manifest identifies the actual build. The verified source archive is
cached as `downloads/opensta-3.1.0-g7b261909c173-source.tar.gz` and its checksum
is recorded in both the manifest and `downloads/SHA256SUMS`.

## Install the verification library

The activity tests use the typical Nangate45 library pinned in
`config/tools/nangate45-install.json`. Download and verify it before testing:

```bash
python3 - <<'PY'
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

manifest = json.loads(Path('config/tools/nangate45-install.json').read_text())
archive = Path(manifest['download_path'])
archive.parent.mkdir(parents=True, exist_ok=True)
url = ('https://raw.githubusercontent.com/The-OpenROAD-Project/'
       'OpenROAD-flow-scripts/master/' + manifest['source_path'])
with urllib.request.urlopen(url) as source, archive.open('wb') as destination:
    shutil.copyfileobj(source, destination)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['sha256']
assert archive.stat().st_size == manifest['size_bytes']
installed = Path(manifest['installed_directory'])
installed.mkdir(parents=True, exist_ok=True)
shutil.copy2(archive, installed / manifest['filename'])
link = Path('tools/nangate45')
if not link.exists() and not link.is_symlink():
    link.symlink_to(installed.name, target_is_directory=True)
PY
```

## Verify and install OpenSTA

Test the built executable, then install a stripped copy and the upstream
license into the versioned tool directory:

```bash
OPENSTA_TEST_BINARY="$PWD/build/tools/opensta/build/sta" \
  python3 -m unittest discover -s tests/tools -p 'test_*.py' -v

mkdir -p tools/opensta-3.1.0-g7b261909c173-linux-x64
install -m755 build/tools/opensta/build/sta \
  tools/opensta-3.1.0-g7b261909c173-linux-x64/sta
strip tools/opensta-3.1.0-g7b261909c173-linux-x64/sta
install -m644 build/tools/opensta/source/LICENSE \
  tools/opensta-3.1.0-g7b261909c173-linux-x64/LICENSE
ln -sfn opensta-3.1.0-g7b261909c173-linux-x64 tools/opensta
./bin/sta -version
python3 -m unittest discover -s tests/tools -p 'test_*.py' -v
```

Refresh the recorded executable checksum after rebuilding. Different compiler
or dependency versions can produce a different binary checksum:

```bash
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
path = Path('config/tools/opensta-install.json')
manifest = json.loads(path.read_text())
manifest['binary_sha256'] = hashlib.sha256(Path(manifest['binary']).read_bytes()).hexdigest()
path.write_text(json.dumps(manifest, indent=2) + '\n')
PY
```
