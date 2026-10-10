# Yosys toolchain

The optional synthesis toolchain is an unmodified Yosys 0.69 source release
with the bundled sv-elab/Slang SystemVerilog frontend and ABC enabled.
`config/tools/yosys-install.json` records the source archive checksum,
dependency revisions, build options, and installed executable checksums.
The source archive reports its version as `0.69+post`.

`bin/yosys` is a shell launcher, not a Yosys executable. After installation it
runs `tools/yosys/bin/yosys`, through the symlink
`tools/yosys -> yosys-0.69-linux-x64`. It does not use the Yosys on `PATH`.
The Homebrew Yosys installation is independent; the existing Homebrew 0.69_1
package has no `read_slang` command.

The normal core build and simulation use XLS and Icarus Verilog.
A complete synthesis, timing, and power flow for SV32 remains future work.

## Dependencies and host impact

This recipe uses the dependencies already installed on Ubuntu 26.04.1.
It requires no additional apt or Homebrew packages on this machine.
All new source files, build outputs, and installed Yosys files stay under
the repository's ignored `downloads/`, `build/`, and `tools/` directories.
Installation does not require `sudo`.

| Build requirement | Existing installation used |
| --- | --- |
| C++20 compiler | Ubuntu GCC 15.2.0, `/usr/bin/cc` and `/usr/bin/c++` |
| CMake | Homebrew 4.4.4 |
| Build generator | Ubuntu GNU Make 4.4.1; Ninja is not required |
| Python interpreter | Ubuntu Python 3.14, `/usr/bin/python3` |
| Bison and Flex | Homebrew Bison 3.8.2 and Flex 2.6.4 |
| pkg-config | Ubuntu pkg-config |
| Slang, ABC, fmt, Boost Regex, toml++ | Bundled source copies |

`YOSYS_USE_BUNDLED_LIBS=ON` avoids requiring separate system development
packages for fmt, Boost, and toml++. The official `yosys.tar.gz` release
archive includes the submodule contents. GitHub's automatically generated
“Source code” archives are not a substitute.

Optional features are configured as follows:

| Dependency or feature | Configuration and consequence |
| --- | --- |
| readline / ncurses | Existing Homebrew readline 8.3.6 and ncurses 6.6; interactive editing and history enabled |
| Tcl | Existing Homebrew Tcl 8.6.18; Tcl scripting enabled |
| zlib | Existing Ubuntu zlib 1.3.1; compressed input and FST support enabled |
| libffi | Existing Ubuntu libffi 3.5.2; Verilog DPI-C support enabled |
| editline | Disabled; readline provides interactive editing |
| GoogleTest | Missing; upstream unit-test targets disabled |
| Python bindings | Disabled; pybind11 and cxxheaderparser are absent |
| Verific frontend | Not configured; the bundled Slang frontend is used |

Disabling the upstream unit-test targets does not disable this project's
DSLX tests or RTL simulation. Python is still required to generate build data
even when Python bindings are disabled. Homebrew editline is installed, but its
pkg-config directory is intentionally unnecessary for this recipe.

The installed executables retain runtime dependencies on existing Ubuntu and
Homebrew shared libraries, including Tcl and readline. The install RPATH points
to their Homebrew `opt` directories. The installation is independent of the
disposable Yosys source/build directories, but it is not a fully static binary.

## Download and verify the source

Run from the project root. For an existing source checkout, skip extraction
and continue with configuration.

```bash
mkdir -p downloads build/tools/yosys
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
assert archive.stat().st_size == manifest['archive_size_bytes']
assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['sha256']
source_dir = Path(manifest['source_directory'])
if source_dir.exists():
    raise SystemExit('Source directory exists; keep it and skip extraction.')
source_dir.mkdir(parents=True)
with tarfile.open(archive) as source:
    source.extractall(source_dir, filter='data')
PY
```

The pinned archive is 16,403,186 bytes with SHA-256
`6dad6412cae417f5a53e2c943c2aee160162cfc1bdd31669230da1b7e3522571`.

## Configure and build

The pkg-config search path makes the existing Homebrew Tcl and readline
installations visible while retaining Ubuntu's zlib and libffi.

```bash
yosys_readline_prefix="$(brew --prefix readline)"
yosys_ncurses_prefix="$(brew --prefix ncurses)"
yosys_tcl_prefix="$(brew --prefix tcl-tk@8)"
yosys_tommath_prefix="$(brew --prefix libtommath)"

PKG_CONFIG_PATH="$yosys_readline_prefix/lib/pkgconfig:$yosys_ncurses_prefix/lib/pkgconfig:$yosys_tcl_prefix/lib/pkgconfig:$yosys_tommath_prefix/lib/pkgconfig" \
cmake -S build/tools/yosys/source -B build/tools/yosys/build \
  -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/tools/yosys-0.69-linux-x64" \
  -DCMAKE_INSTALL_RPATH="$yosys_readline_prefix/lib;$yosys_ncurses_prefix/lib;$yosys_tcl_prefix/lib" \
  -DCMAKE_C_COMPILER=/usr/bin/cc \
  -DCMAKE_CXX_COMPILER=/usr/bin/c++ \
  -DPython3_EXECUTABLE=/usr/bin/python3 \
  -DPython_EXECUTABLE=/usr/bin/python3 \
  -DYOSYS_USE_BUNDLED_LIBS=ON \
  -DYOSYS_WITHOUT_SLANG=OFF \
  -DYOSYS_WITHOUT_EDITLINE=ON \
  -DYOSYS_ENABLE_UNIT_TESTS=OFF \
  -DCMAKE_DISABLE_FIND_PACKAGE_Git=ON \
  -DYOSYS_CHECKOUT_INFO=143eb14f9cc55d6f8927e68523b0c9d2166ed02c \
  -DYOSYS_SLANG_REVISION=b4fd362f4c53dc8ffab6946b9f866a6ea89e366d \
  -DSLANG_REVISION=e222e7dc0250231312f14c37d47404a49df00fe2

CPATH="$yosys_readline_prefix/include${CPATH:+:$CPATH}" \
cmake --build build/tools/yosys/build --parallel 8 \
  > build/tools/yosys/build.log 2>&1
```

The `CPATH` setting supplies readline headers to the upstream `viz` component,
which does not inherit the pkg-config include directory in this release.
It avoids source patches and an additional Ubuntu `libreadline-dev` package.

The revision options preserve source and dependency metadata when building
from a release archive inside this repository. They prevent this workspace's
Git revision from being mistaken for a bundled library's revision.
Slang may print `error: No such remote 'origin'` while inspecting Git metadata;
configuration still succeeds, and its frontend revisions are supplied above.

Use `tail -f build/tools/yosys/build.log` to watch progress.
The build contains roughly 1,850 compilation commands, so initial compilation
is substantially slower than configuration. Eight parallel jobs are suitable
for this machine's 20 logical CPUs and 45 GiB RAM.

## Install and verify

Run installation only after the build succeeds:

```bash
cmake --install build/tools/yosys/build --strip \
  > build/tools/yosys/install.log 2>&1
ln -sfn yosys-0.69-linux-x64 tools/yosys
./bin/yosys -V
./bin/yosys -Q -T -p 'help read_slang'
ldd tools/yosys/bin/yosys
ldd tools/yosys/bin/yosys-abc
```

The version should identify commit
`143eb14f9cc55d6f8927e68523b0c9d2166ed02c`; the help command should describe
`read_slang`. Check that neither `ldd` output contains `not found`.
Installation includes ABC and Yosys's runtime data files under
`tools/yosys/share/yosys`.

Refresh the recorded executable checksums after rebuilding:

```bash
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

path = Path('config/tools/yosys-install.json')
manifest = json.loads(path.read_text())
manifest['binary_sha256'] = hashlib.sha256(
    Path(manifest['binary']).read_bytes()).hexdigest()
manifest['abc_binary_sha256'] = hashlib.sha256(
    Path('tools/yosys/bin/yosys-abc').read_bytes()).hexdigest()
path.write_text(json.dumps(manifest, indent=2) + '\n')
PY
```

## SystemVerilog input and synthesis validation

Use `read_slang` for SystemVerilog with unpacked array ports.
`read_verilog -sv` selects Yosys's older parser, even in a build with Slang.
`memory_map` lowers unpacked register arrays when needed.

For example:

```bash
./bin/yosys -p 'read_slang --top my_top design.sv; synth -top my_top; check -assert'
```

To check the generated core, build its RTL and synthesize the clocked wrapper:

```bash
python3 scripts/build-sv32.py
mkdir -p build/sv32/yosys
./bin/yosys -Q -T -l build/sv32/yosys/synth.log -p \
  'read_slang --top sv32_top build/sv32/sv32_core.v build/sv32/sv32_top.sv; synth -top sv32_top; check -assert; stat; write_verilog -noattr build/sv32/yosys/sv32_top.v'
```

This checks frontend elaboration, synthesis passes, and the bundled ABC
executable. It does not produce an OpenSTA timing or power report.

## Verified installation on 2026-10-10

The Release build and repository-local installation completed on Ubuntu
26.04.1 using eight parallel jobs and no newly installed host packages.
The source code required no patches; the readline include-path workaround
above was sufficient.

Validation passed for the installed executables:

- The launcher reports Yosys `0.69+post` at the pinned source revision.
- Slang elaborates and synthesizes a test with unpacked array input ports.
- Tcl scripting runs successfully, and all shared libraries resolve.
- SV32 synthesis completes through ABC with `check -assert` reporting zero
  problems. Its log is `build/sv32/yosys/synth.log`.
- The synthesized SV32 netlist passes the existing demo against the Python
  reference model: 46 cycles, 32 registers, and 256 memory words. The result
  is recorded in `build/sv32/yosys/verification/result.txt`.

The installed prefix uses approximately 72 MiB. The extracted source uses
104 MiB and the completed build directory uses 389 MiB. These measurements
are for this Release build; other build options can change disk usage.

Upstream reference: [Yosys build instructions](https://github.com/YosysHQ/yosys/blob/v0.69/README.md#building-from-source).
