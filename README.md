# XLS SV32

SV32 is an [RV32I](https://riscv.org/) core implemented in DSLX and built
with the official [Google XLS](https://github.com/google/xls) toolchain. This
repository is a testbed for using XLS on real RTL: DSLX is type-checked and
simulated with the XLS interpreter and LLVM JIT, lowered to optimized IR,
emitted as Verilog, wrapped in a clocked SystemVerilog shell, and simulated
with Icarus Verilog against an independent Python reference model.

The design is documented in [docs/sv32.md](docs/sv32.md).

## Folder structure

```text
xls-sv32/
├── README.md                    # Project overview and commands
├── .gitignore                   # Local tools, builds, and caches
├── bin/                         # Executable launchers (tracked)
│   ├── xls                      # Linux XLS tool launcher
│   ├── sta                      # Linux OpenSTA launcher
│   ├── yosys                    # Linux Slang-enabled Yosys launcher
│   └── run-smoke-test.sh        # Smoke-test launcher
├── config/
│   └── tools/                   # Pinned installation manifests (tracked)
│       ├── xls-install.json
│       ├── opensta-install.json
│       ├── yosys-install.json
│       └── nangate45-install.json
├── src/
│   └── sv32/
│       └── sv32.x               # Pure RV32I state-transition function
├── tests/
│   ├── sv32/
│   │   ├── sv32_test.x          # DSLX unit tests for every instruction class
│   │   ├── sv32_ref.py          # Assembler and reference interpreter
│   │   ├── sv32_cases.py        # Directed RTL programs and expected results
│   │   └── test_build_sv32.py   # Default/custom module elaboration checks
│   └── tools/
│       ├── test_install_xls.py  # Offline installer recovery fixtures
│       ├── test_nangate_install.py
│       └── test_opensta_activity.py
├── scripts/
│   ├── install-xls.sh           # Download/verify the pinned XLS release
│   ├── build-sv32.py            # DSLX -> IR -> RTL -> clocked wrapper
│   ├── test-sv32.py             # DSLX/JIT tests plus RTL-vs-reference simulation
│   └── smoke-test.sh            # Toolchain smoke test
├── docs/
│   ├── sv32.md                  # Interface, ISA coverage, and verification
│   ├── opensta.md               # Pinned analyzer and rebuild instructions
│   └── yosys.md                 # Pinned synthesis flow
├── build/                       # Generated artifacts (ignored)
│   └── sv32/
│       ├── sv32.ir / sv32.opt.ir
│       ├── sv32_core.v          # Combinational datapath
│       ├── sv32_core.sig.textproto
│       ├── sv32_top.sv          # Registered wrapper
│       ├── imem.hex / dmem.hex / tb.sv / sim.vvp
│       └── config.json
├── tools/                       # Installed tools (ignored)
└── downloads/                   # Cached downloads and SHA256SUMS (ignored)
```

Add hardware designs under `src/<design>/`, verification code under
`tests/<design>/`, and notes under `docs/`. Build scripts place generated
files under `build/<design>/`. Commit source, tests, scripts, launchers,
configuration, and documentation; keep downloaded binaries, archives, and
generated output out of Git. `.gitignore` excludes `tools/`, `downloads/`,
and `build/` rather than all `.v`/`.x` files, so hand-written HDL and test
fixtures can still be versioned.

## Install the toolchain

The supported host platform is Linux x64. The binary XLS release pinned in
`config/tools/xls-install.json` is installed locally; no Bazel or source build
is required:

```bash
./scripts/install-xls.sh
```

The script downloads into a temporary file and caches the archive only after
its SHA-256 digest matches the manifest. It repairs corrupt cache entries and
incomplete installations, validates a staged installation, then refreshes
`tools/xls`. Failed downloads or extraction leave a working default link intact.

`bin/xls` launches any installed XLS executable directly. Relative paths
resolve from the project root:

```bash
./bin/xls interpreter_main --version
./bin/xls interpreter_main --dslx_path=src/sv32 \
    tests/sv32/sv32_test.x
```

## Generate and test the core

```bash
python3 scripts/build-sv32.py     # DSLX -> IR -> RTL + wrapper
python3 scripts/test-sv32.py      # DSLX tests, RTL build, and simulation
python3 -m unittest discover -s tests/sv32 -p 'test_*.py' -v  # Wrapper builds
```

`test-sv32.py`:

1. Runs the DSLX unit tests with the interpreter and compares results with
   the LLVM JIT (23 tests across ALU, branches, jumps, memory, and decoding).
2. Converts `step` to XLS IR, optimizes it, and emits combinational Verilog
   plus a module signature.
3. Generates `sv32_top.sv`, which registers the architectural state and
   exposes Harvard instruction/data memory ports.
4. Simulates 35 programs with Icarus Verilog and compares every register,
   data-memory word, halt PC, and cycle count against `tests/sv32/sv32_ref.py`.
   Directed expectations also check reset writes, halfword lanes, shift counts,
   and unsupported encodings independently of the reference interpreter.

To simulate an existing build without rerunning the DSLX checks:

```bash
python3 scripts/test-sv32.py --simulate-only build/sv32
```

The quicker smoke test skips simulation and only checks the XLS flow:

```bash
./bin/run-smoke-test.sh
```

Installer regression tests run offline in temporary projects:

```bash
python3 -m unittest discover -s tests/tools -p 'test_install_xls.py' -v
python3 -m unittest discover -s tests/tools -p 'test_nangate_install.py' -v
```

## The core in one function

`src/sv32/sv32.x` is a pure function. XLS codegen turns it into
combinational logic, and `scripts/build-sv32.py` adds the state register:

```text
step(state, imem_rdata, dmem_rdata) -> (state', dmem_req, halt)
```

| Signal | Direction | Width | Purpose |
| --- | --- | --- | --- |
| `state` | in | 1056 | `pc` in `[31:0]`, 32 registers above it |
| `imem_rdata` | in | 32 | Instruction word at the current PC |
| `dmem_rdata` | in | 32 | Data word at the emitted address |
| `out` | out | 1125 | next state, data-memory request, and halt flag |

The wrapper registers `state` and freezes it when `halt` is asserted, so
`ECALL`/`EBREAK` and unsupported encodings stop without committing effects.
Store strobes are suppressed during reset. The build script parses the module
signature and computes the packed-field offsets, so it adapts if the design
changes. See [docs/sv32.md](docs/sv32.md) for the port table, ISA
coverage, memory model, and verification details.

## Toolchain notes

- `config/tools/xls-install.json` pins the XLS release URL, platform, size,
  and checksum.
- `config/tools/opensta-install.json`, `yosys-install.json`, and
  `nangate45-install.json` pin the optional synthesis and power-analysis
  tools inherited from the original XLS test project. Their launchers
  (`bin/sta`, `bin/yosys`) are ready to use; a RISC-V PPA script is a
  future addition.
- Icarus Verilog (`iverilog`/`vvp`) is required for RTL simulation. Verilator
  and Yosys are useful for lint and synthesis.

Upstream references: [XLS installation](https://github.com/google/xls#install-latest-release),
[XLS tool quick start](https://google.github.io/xls/tools_quick_start/), and
the [RISC-V unprivileged ISA specification](https://riscv.org/technical/specifications/).
