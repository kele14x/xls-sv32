# Known issues

All eight findings below were fixed on 2026-10-12. The reproductions and line
numbers record the pre-fix code reviewed on 2026-10-10.

| Issue | Resolution | Regression coverage |
| --- | --- | --- |
| 1. Halfword strobes | Select lanes `0011`/`1100` using the byte offset | DSLX lane checks and RTL store/load preservation |
| 2. Register shifts | Use only the lowest five bits of `rs2` | DSLX and RTL counts 0, 31, 32, 33, and upper bits set |
| 3. Reset stores | Gate exported write strobes with `rst_n` | RTL store at the reset vector with preloaded memory |
| 4. Unsupported encodings | Validate fields before execution; halt without effects | 25 negative DSLX/RTL cases plus CSR/FENCE NOP checks |
| 5. Custom module names | Instantiate the requested module in the wrapper | Default and custom builds elaborate with Icarus |
| 6. Incomplete installations | Stage and validate executables/stdlib before publishing | Offline fixtures repair incomplete directories and preserve defaults on failure |
| 7. Interrupted downloads | Verify temporary downloads; replace invalid cache entries | Offline interruption, checksum, corruption, and retry fixtures |
| 8. Nangate45 links | Atomically refresh the symlink and verify the active library | Exact documentation recipe tested with fresh, stale, and dangling links |

Validation: 23 DSLX/JIT and IR-interpreter tests, 35 RTL programs, default
and custom wrapper builds, and 14 tooling tests all pass. The tooling tests
include the existing OpenSTA activity checks. Test commands are listed in
[README.md](README.md).

P1 issues affect valid RV32I instructions. P2 issues affect reset behavior,
the documented illegal-instruction halt policy, build configuration, or
toolchain installation.

## 1. [P1] Halfword stores corrupt memory at byte offset 2

**Location:** [src/sv32/sv32.x](src/sv32/sv32.x), lines 144–148,
`exec_store`.

For an address with byte offset 2, `half_strobe` is 1. Shifting the halfword
write strobe `0011` by 1 produces `0110`, but the upper halfword requires
`1100`. Store data is correctly shifted by 16 bits, so the incorrect strobes
clear byte lane 1, write byte lane 2, and leave byte lane 3 unchanged.

**Reproduction:** Initialize data word 0 to `0x11223344`, set `x2` to
`0x0000abcd`, and execute `sh x2, 2(x0)`.

| Observation | Expected | Actual RTL |
| --- | --- | --- |
| Write strobes | `1100` | `0110` |
| Data word after store | `0xabcd3344` | `0x11cd0044` |
| Subsequent `lhu x3, 2(x0)` | `0x0000abcd` | `0x000011cd` |

**Suggested fix:** Shift `u4:3` by `addr & 2`, rather than by the halfword
index. Add store tests at both aligned halfword offsets, checking preservation
of neighboring bytes and a subsequent load.

## 2. [P1] Register shifts use the full register as the shift count

**Location:** [src/sv32/sv32.x](src/sv32/sv32.x), lines 202, 206, and 210,
`exec_op`.

`SLL`, `SRL`, and `SRA` shift by all 32 bits of `rs2`. RV32I requires the
shift count to come from only the lowest five bits of `rs2`.
See the [RV32I specification](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html).

**Reproduction:** Set `x2` to 33 and execute the following instructions with
the indicated `x1` value. Each instruction must shift by 1.

| Instruction | `x1` | Expected `x3` | Actual RTL `x3` |
| --- | --- | --- | --- |
| `sll x3, x1, x2` | `0x00000001` | `0x00000002` | `0x00000000` |
| `srl x3, x1, x2` | `0x80000000` | `0x40000000` | `0x00000000` |
| `sra x3, x1, x2` | `0x80000000` | `0xc0000000` | `0xffffffff` |

**Suggested fix:** Use `b[0:5]` as the shift count for all three register
shift instructions. Add tests for counts 0, 31, 32, 33, and values with other
upper bits set. The immediate shift instructions already select five bits.

## 3. [P2] Store write strobes remain active during reset

**Location:** [scripts/build-sv32.py](scripts/build-sv32.py), line 173,
generated wrapper assignment to `dmem_wstrb`; and
[scripts/test-sv32.py](scripts/test-sv32.py), lines 54–58, memory writes.

The wrapper resets architectural state but forwards the combinational core's
write strobes regardless of `rst_n`. The supplied testbench memory also
accepts writes while reset is asserted. Consequently, a store instruction at
the reset address can modify memory on clock edges during reset.

**Reproduction:** Present `sw x0, 0(x0)` (`0x00002023`) at the reset address,
initialize data word 0 to `0xcafebabe`, assert `rst_n = 0`, and keep the clock
running. RTL simulation shows `dmem_wstrb = 1111` during reset and data word 0
becoming `0x00000000` after a rising clock edge.

**Suggested fix:** Gate exported store strobes with `rst_n`. Add a wrapper
test that holds reset across clock edges with a store at the reset address
and verifies that memory remains unchanged.

## 4. [P2] Unsupported encodings bypass the illegal-instruction halt policy

**Location:** [src/sv32/sv32.x](src/sv32/sv32.x), lines 198–214,
`exec_op`, and lines 145–150, `exec_store`. Similar missing legality checks
exist for immediate shifts, loads, branches, and `JALR`.

The documentation describes halting on illegal instructions, but recognizing
a major opcode is enough to enter an execution path without validating all
instruction fields. In `exec_op`, every `funct7` other than `0x20` enters
the base ALU path. In `exec_store`, every `funct3` other than 0 or 1 performs
a full-word store.

**Reproductions:**

- Set `x1 = 3` and `x2 = 4`, then execute `mul x3, x1, x2`
  (`0x022081b3`). Although the M extension is unsupported, the RTL executes
  it as `ADD`, writes `x3 = 7`, and continues without halting.
- Set `x2 = 7`, then execute store encoding `0x00203023`, whose `funct3` is
  3 and is not an RV32I store. The RTL issues a full-word write and overwrites
  data word 0 with 7 without halting.

The [Python reference model](tests/sv32/sv32_ref.py) repeats these decoding
choices, so RTL/reference agreement does not detect the problem. The demo
also uses an invalid immediate-shift encoding (`imm = 0x801`) in an
instruction commented as `SRAI`; both implementations accept it as `SRLI`.

This finding concerns the project's documented halt policy. It does not
assume that all reserved encodings must trap under every RISC-V execution
environment, or request implementation of architectural traps.

**Suggested fix:** Validate supported opcode/`funct3`/`funct7` combinations
before committing register or memory effects, and route unsupported
encodings to the existing halt path. Preserve the explicitly documented CSR
NOP behavior. Add negative decode tests with independently specified expected
behavior, and correct the demo's immediate-shift encoding.

## 5. [P2] Custom module names produce a wrapper that cannot compile

**Location:** [scripts/build-sv32.py](scripts/build-sv32.py), line 162,
inside `wrapper(signature, module)`.

The build script passes `--module-name` to XLS code generation, but the
wrapper always instantiates `sv32_core`, ignoring its `module` argument.

**Reproduction:**

```bash
python3 scripts/build-sv32.py \
    --module-name review_core --output-dir build/review-core
iverilog -g2012 -s sv32_top -o build/review-core/sim.vvp \
    build/review-core/sv32_core.v build/review-core/sv32_top.sv
```

Generation succeeds, but Icarus fails with `Unknown module type: sv32_core`
because the generated core module is named `review_core`.

**Suggested fix:** Interpolate the supplied module name in the wrapper's
core instantiation. Verify elaboration with both the default and a custom
module name.

## Review validation

- `python3 scripts/test-sv32.py` passed all 17 DSLX/JIT unit tests and the
  46-cycle RTL/reference demo, comparing all 32 registers and 256 data words.
- Six additional directed DSLX assertions failed: the three register shifts,
  the upper-halfword store strobe, unsupported `MUL` halting, and invalid
  store halting.
- Targeted Icarus simulations confirmed the shift results, halfword-store
  corruption, unsupported instruction effects, and writes during reset.
- A custom-module build reproduced the wrapper elaboration failure.
- Verilator lint of the default generated core and wrapper reported only
  unused-signal warnings.

The passing review baseline demonstrated that the original tests did not
cover these failures. The fixes and expanded tests are recorded above.

## Tooling review on 2026-10-10

### 6. [P2] An incomplete XLS installation can replace a working tool link

**Location:** [scripts/install-xls.sh](scripts/install-xls.sh), lines 29–38.

The installer treats the existence of the versioned directory as proof of a
complete installation. An interrupted extraction can leave that directory
present with missing executables. A subsequent run skips extraction and
changes `tools/xls` before validating the interpreter. The version check then
fails, leaving the default launcher pointing at the incomplete installation,
even if it previously pointed at a working version.

**Reproduction:** In an isolated project fixture, provide a valid,
checksum-matching release archive, an existing working `tools/xls` symlink,
and an empty directory at the manifest's `installed_directory`. The installer
skips extraction, replaces the working symlink, and exits 2 with
`XLS tool not found: interpreter_main`. Removing the incomplete directory
allows the same archive to install successfully.

**Suggested fix:** Extract into a staging directory and validate the expected
executables and standard library before publishing the versioned installation
and switching the default symlink. Detect and repair incomplete existing
directories while preserving a working default installation on failure.

### 7. [P2] An interrupted XLS download prevents later installer retries

**Location:** [scripts/install-xls.sh](scripts/install-xls.sh), lines 23–27.

`curl` writes directly to the final cached archive filename. An interrupted
download can leave a partial file behind. On subsequent runs, the installer
sees the file and skips downloading; checksum verification fails every time
until the user manually removes the cached file. The same problem affects an
otherwise corrupted cached archive.

**Reproduction:** In an isolated fixture, a downloader writes a partial
archive and exits 18. Enable successful downloading and rerun the installer.
The second run fails SHA-256 verification without calling the downloader.
Deleting the partial archive permits a successful retry.

**Suggested fix:** Download to a temporary filename, verify its checksum, and
rename it into the cache only after verification. Detect invalid existing cache
entries and redownload them rather than permanently blocking retries.

### 8. [P2] Nangate45 installation leaves an existing default link unchanged

**Location:** [docs/opensta.md](docs/opensta.md), lines 120–122, the library
installation recipe.

The recipe verifies the downloaded library and copies it into the versioned
directory, but creates `tools/nangate45` only if no file or symlink exists
there. If the default link points at an older library, it remains unchanged.
A dangling symlink is also left unrepaired. Tests and future timing/power
flows read through this default link, so the active library can differ from
the verified installation and manifest.

**Reproduction:** Run the exact documentation snippet in an isolated fixture
with `tools/nangate45` pointing at an older library and the manifest describing
a new versioned directory. The snippet succeeds and writes the verified new
library, but reading the manifest's `library_path` still returns the old
library. No upstream download or workspace tool modification is needed for
this reproduction.

**Suggested fix:** Refresh the default symlink to the verified versioned
directory and verify the checksum through `library_path` after the switch.
Handle an existing regular file or directory explicitly instead of silently
leaving it active.

### Tooling validation

- XLS, OpenSTA, and Yosys version commands succeed in the current workspace.
- All three cached source/release archive checksums match their manifests.
- Installed OpenSTA, Yosys, ABC, and Nangate45 checksums match their manifests.
- XLS, OpenSTA, Yosys, and ABC have no unresolved shared libraries.
- Both OpenSTA activity tests pass, including all four gated-clock cases.
- The three installation findings were reproduced in temporary fixtures;
  the workspace's installed tools and symlinks were left intact.

The current installations are healthy. These findings concern recovery from
interrupted setup and refreshing the default verification-library link.
