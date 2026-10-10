# Known issues

Recorded during the initial SV32 review on 2026-10-10. All five issues below
remain open; this document records the findings without changing the core.

P1 issues affect valid RV32I instructions. P2 issues affect reset behavior,
the documented illegal-instruction halt policy, or build configuration.

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

The passing baseline demonstrates that the current tests do not cover these
failures. No core fixes were applied as part of this review.
