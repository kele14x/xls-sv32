# XLS RISC-V

An [RV32I](https://riscv.org/) core implemented in DSLX and built with the
official [Google XLS](https://github.com/google/xls) toolchain. This
repository is a testbed for using XLS on real RTL: DSLX is type-checked and
simulated with the XLS interpreter and LLVM JIT, lowered to optimized IR,
emitted as Verilog, wrapped in a clocked SystemVerilog shell, and simulated
with Icarus Verilog against an independent Python reference model.

The design is documented in [docs/riscv-core.md](docs/riscv-core.md).

## Folder structure

```text
xls-riscv/
├── README.md                    # Project overview and commands
├── .gitignore                   # Local tools, builds, and caches
├── bin/                         # Executable launchers (tracked)
│   ├── xls                      # XLS tool launcher (macOS or Linux)
│   ├── sta                      # OpenSTA launcher (macOS or Linux)
│   ├── yosys                    # Slang-enabled Yosys launcher (macOS or Linux)
│   └── run-smoke-test.sh        # Smoke-test launcher
├── config/
│   └── tools/                   # Pinned installation manifests (tracked)
│       ├── xls-install.json
│       ├── opensta-install.json
│       ├── yosys-install.json
│       └── nangate45-install.json
├── src/
│   └── riscv_core/
│       └── riscv_core.x         # Pure RV32I state-transition function
├── tests/
│   ├── riscv_core/
│   │   ├── riscv_core_test.x    # DSLX unit tests for every instruction class
│   │   └── rv32_ref.py          # Assembler and reference interpreter
│   └── tools/
│       └── test_opensta_activity.py
├── scripts/
│   ├── install-xls.sh           # Download/verify the pinned XLS release
│   ├── build-riscv.py           # DSLX -> IR -> RTL -> clocked wrapper
│   ├── test-riscv.py            # DSLX/JIT tests plus RTL-vs-reference simulation
│   └── smoke-test.sh            # Toolchain smoke test
├── docs/
│   ├── riscv-core.md            # Interface, ISA coverage, and verification
│   ├── opensta.md               # Pinned analyzer and rebuild instructions
│   └── yosys.md                 # Pinned synthesis flow
├── build/                       # Generated artifacts (ignored)
│   └── riscv_core/
│       ├── riscv.ir / riscv.opt.ir
│       ├── riscv_core.v         # Combinational datapath
│       ├── riscv_core.sig.textproto
│       ├── riscv_top.sv         # Registered wrapper
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

The binary XLS release pinned in `config/tools/xls-install.json` is installed
locally; no Bazel or source build is required. On Linux x64:

```bash
./scripts/install-xls.sh
```

The script downloads the archive into `downloads/`, checks it against the
published SHA-256 digest, extracts it under `tools/`, and points the
`tools/xls` symlink at it. On macOS, run it inside the shared OrbStack VM:

```bash
orb -m ubuntu24 -w "$PWD" ./scripts/install-xls.sh
```

`bin/xls` launches any XLS executable and, on macOS, forwards the command
into the VM. Relative paths resolve from the project root:

```bash
./bin/xls interpreter_main --version
./bin/xls interpreter_main --dslx_path=src/riscv_core \
    tests/riscv_core/riscv_core_test.x
```

## Generate and test the core

```bash
python3 scripts/build-riscv.py     # DSLX -> IR -> RTL + wrapper
python3 scripts/test-riscv.py      # DSLX tests, RTL build, and simulation
```

`test-riscv.py`:

1. Runs the DSLX unit tests with the interpreter and compares results with
   the LLVM JIT (17 tests across ALU, branches, jumps, loads, and stores).
2. Converts `step` to XLS IR, optimizes it, and emits combinational Verilog
   plus a module signature.
3. Generates `riscv_top.sv`, which registers the architectural state and
   exposes Harvard instruction/data memory ports.
4. Writes a demo program, simulates the RTL with Icarus Verilog, and compares
   every register and data-memory word against `tests/riscv_core/rv32_ref.py`.

To simulate an existing build without rerunning the DSLX checks:

```bash
python3 scripts/test-riscv.py --simulate-only build/riscv_core
```

The quicker smoke test skips simulation and only checks the XLS flow:

```bash
./bin/run-smoke-test.sh
```

On another OrbStack VM, set `XLS_VM`:

```bash
XLS_VM=ubuntu24 ./bin/run-smoke-test.sh
```

## The core in one function

`src/riscv_core/riscv_core.x` is a pure function. XLS codegen turns it into
combinational logic, and `scripts/build-riscv.py` adds the state register:

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
`ECALL`/`EBREAK` cleanly stop the program. The build script parses the module
signature and computes the packed-field offsets, so it adapts if the design
changes. See [docs/riscv-core.md](docs/riscv-core.md) for the port table, ISA
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
