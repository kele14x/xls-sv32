# SV32 roadmap

Findings recorded on 2026-10-12 against commit `c7949ea`.

Test the existing blinky on DE25-NANO first. After that passes, work through
the milestones below in order, adding verification with each change. Update
this checklist with results and commit IDs as items are completed.

The first architectural target is **RV32I + Zicsr, machine mode only**, with
precise traps and interrupts. RV32IMC is a later embedded target. Extensions
such as floating point, atomics, and virtual memory are separate scope
decisions; implementing every RISC-V extension is not required for a complete
core with a declared ISA and execution environment.

## Existing baseline

- [x] Clocked public core with explicit PC/register storage and memory ports;
  the packed XLS state bus is internal.
- [x] Synthesizable 1 KiB instruction ROM, 1 KiB data RAM, LED MMIO, and a
  13-instruction blinky program.
- [x] DE25-NANO pins, vendor PLL/reset-release IP, and a 100 MHz CPU clock.
- [x] DSLX, directed core RTL, memory/MMIO, board-wrapper simulation, and
  synthesized-netlist blinky checks.
- [x] Quartus synthesis, fitting, timing, and assembly. The existing build has
  setup slack +0.553 ns and hold slack +0.111 ns at 100 MHz.
- [ ] Physical board programming and observation.

Build commands, address maps, test coverage, and timing details are in
[docs/soc.md](docs/soc.md). The eight earlier fixed findings are preserved in
[KNOWN_ISSUES.md](KNOWN_ISSUES.md); the gaps below are additional work.

## Findings in the current implementation

| Area | Current behavior | Work required |
| --- | --- | --- |
| Exceptions | `exec_system` and `illegal` in [sv32.x](src/sv32/sv32.x) halt permanently. | Enter a software trap handler with the correct cause, PC, and trap value. |
| CSRs and privilege | CSR instructions are accepted as NOPs; `State` contains only registers and PC. | Implement Zicsr and the selected machine-level architecture, including access rules and trap state. |
| Alignment | Loads/stores round addresses into word/halfword lanes; jumps do not check four-byte target alignment. | Detect misalignment before architectural or memory effects; initially trap rather than emulate. |
| Memory interface | The [public interface](docs/sv32.md) requires same-cycle reads and has no request-valid, completion, or error signals. | Explicit transactions, stalls, and fault responses, including a read enable for MMIO side effects. |
| Memory implementation | [IMEM](src/sv32_soc/sv32_imem.v) and [DMEM](src/sv32_soc/sv32_dmem.v) use asynchronous reads. | Synchronous block RAM and a controller that waits for responses as memory sizes grow. |
| Address faults | [sv32_soc](src/sv32_soc/sv32_soc.v) returns zero for unmapped data reads and ignores writes; invalid fetches return zero and halt as illegal instructions. | Define region permissions and return instruction/load/store access faults where appropriate. |
| Interrupts and peripherals | The SoC has an LED register, with no interrupt inputs, timer, or UART. | Machine interrupt handling, timer/compare registers, and useful firmware I/O. |
| Firmware | [blinky.py](programs/blinky.py) emits instruction words directly. | A reproducible compiler, linker, startup, and ELF-to-memory flow. |
| Verification | Directed tests and a local Python model cover the current halt policy. | Architectural tests, retirement-level reference comparisons, and trap/interrupt/stall coverage. |

Example alignment failure to address: `LW` at `0x1001` currently reads the
word at `0x1000`; it neither implements the requested unaligned access nor
reports a fault. Misaligned `SH` can similarly write a neighboring halfword.
Without C, a taken branch or jump to an address ending in binary `10` must
raise an instruction-address-misaligned exception. An untaken branch must
not raise that exception.

## 0. Test the current blinky on DE25-NANO

- [ ] Program `build/de25_nano/output_files/sv32_de25_nano.sof` through
  Quartus Programmer and the onboard USB-Blaster III, following
  [the board flow](docs/soc.md#de25-nano-at-100-mhz).
- [ ] Confirm LED 0 alternates approximately 0.5 seconds on / 0.5 seconds off
  at the 100 MHz target, and continues blinking for several minutes.
- [ ] Hold KEY0: LED 0 should turn off. Release KEY0: blinky should restart.
  Repeat reset several times.
- [ ] Power-cycle, reload the volatile `.sof`, and verify startup again.
- [ ] Record the image/source commit, Quartus version, board observations,
  and any failures here before starting milestone 1.

Hardware result: **pending**.

## 1. Machine CSRs and precise exceptions

CSRs and traps form one milestone because trap handlers need CSR access.

- [ ] Declare the supported ISA, privileged specification version, reset
  vector, memory map, and policy for unsupported instructions.
- [ ] Implement all six Zicsr instructions, including suppressed reads/writes,
  read-only CSR checks, and illegal accesses to unavailable CSRs.
- [ ] Add machine trap/control registers, including `mstatus`, `mtvec`,
  `mepc`, `mcause`, `mtval`, and `mscratch`. Audit all mandatory CSRs and
  permitted fixed values for the selected machine-mode configuration.
- [ ] Implement ECALL, EBREAK, illegal-instruction, and alignment exceptions;
  prevent register writeback and stores from faulting instructions.
- [ ] Implement trap entry and `MRET`, including interrupt-enable state.
- [ ] Add machine cycle/instruction counters and RV32 high halves as required
  by the chosen configuration; do not count faulting instructions as retired.
  Declare Zicntr separately if exposing its unprivileged counter interface.
- [ ] Replace simulation termination by ECALL/EBREAK with an explicit test
  completion mechanism, and update the reference model and directed tests.

Acceptance: software reads the correct trap cause/PC/value and returns to
execution; a misaligned or illegal instruction cannot corrupt registers or RAM.

## 2. Memory transactions and synchronous block RAM

- [ ] Define instruction/data request and response ports with valid/acceptance,
  read/write identity, byte enables, completion, and error reporting.
- [ ] Add a simple multicycle controller that holds requests and architectural
  state correctly while waiting; keep XLS execution logic and RTL state
  storage responsibilities explicit.
- [ ] Replace asynchronous memories with synchronous block-RAM-compatible
  implementations; verify actual RAM inference in Quartus.
- [ ] Define ROM/RAM/MMIO permissions and generate instruction/load/store
  access faults. Preserve the original effective address for trap reporting.
- [ ] Ensure loads to `x0` still perform required device accesses and faults.
- [ ] Test variable latency, backpressure, reset during a pending request, and
  errors. Verify that each accepted store or MMIO access occurs exactly once.
- [ ] Recheck FENCE ordering with pending transactions; retain a NOP only
  where completion and ordering guarantees make it correct.

Acceptance: blinky passes with synchronous memories and injected wait states;
the updated DE25-NANO design meets 100 MHz and uses the intended RAM resources.

## 3. Machine interrupts and a timer

- [ ] Add timer, software, and external interrupt inputs with `mie`/`mip`
  behavior, global masking, priority, and documented synchronization.
- [ ] Add a 64-bit timer and compare registers, with a documented RV32 access
  sequence, plus a software-interrupt register if selected by the platform.
- [ ] Take interrupts at instruction boundaries, including correct behavior
  while a memory transaction is pending.
- [ ] Implement legal `WFI` behavior; a specification-permitted NOP is a
  valid initial implementation, with clock/power optimization deferred.
- [ ] Test masking, pending interrupts, trap entry/return, repeated interrupts,
  and interrupts coinciding with exceptions or memory completion.

Acceptance: a timer handler drives the LED while foreground code continues
running, with correct state preservation across repeated interrupts.

## 4. Compiled C firmware and useful I/O

- [ ] Pin a RISC-V GCC or LLVM toolchain and use matching ISA/ABI flags
  (initially `rv32i_zicsr` and `ilp32`).
- [ ] Add a linker script and startup code for the reset vector, stack/global
  pointer, `.data` copying, `.bss` clearing, and trap entry.
- [ ] Define how instruction fetch and data loads access code and `.rodata`
  in the Harvard memory map; size ROM/RAM for the linked firmware.
- [ ] Generate ROM/RAM images from ELF files with overflow checks and retain
  disassembly and symbols for debugging.
- [ ] Add UART output, documenting verified board pins and voltage standards
  before connecting external hardware.
- [ ] Build C tests for functions, stack use, initialized/global data, and
  timer-driven blinky; test in simulation and on the board.

Acceptance: a reproducible compiler build produces C blinky driven by timer
interrupts, with observable UART output, running on DE25-NANO at 100 MHz.

## 5. Architectural verification and regression automation

Add focused tests during milestones 1-4; this milestone broadens coverage.

- [ ] Integrate RISC-V architectural tests for exactly the declared ISA and
  privilege configuration, with the required platform hooks.
- [ ] Expose an instruction-retirement trace and compare randomized programs
  against Spike or Sail, matching memory-map and interrupt assumptions.
- [ ] Add formal checks where useful: `x0`, precise traps, valid retirement,
  reset suppression, and no lost or duplicated memory transactions. Consider
  RVFI for compatible formal tooling.
- [ ] Automate reproducible regression runs and track coverage gaps. Passing
  architectural tests alone does not establish complete implementation safety.
- [ ] Repeat Quartus timing/resource checks and physical board tests after
  changes to execution, memory, clocking, or reset behavior.

## 6. Extensions and performance, one change at a time

- [ ] Add M multiplication/division with corner-case tests, including division
  by zero and signed overflow; support multicycle execution if needed.
- [ ] Add C decoding and fetch across word boundaries; update PC increments,
  link addresses, and instruction alignment rules.
- [ ] Add Zifencei when supporting writable/downloaded executable code;
  ensure instruction fetch observes prior code writes.
- [ ] Evaluate a short pipeline using measured throughput, timing, and resource
  data. Design stalls, forwarding, flushes, and precise traps explicitly;
  switching XLS to pipeline code generation alone is insufficient.
- [ ] Add debug access for halt/resume, single stepping, and breakpoints;
  consider the standard RISC-V debug interface and a JTAG transport.
- [ ] Evaluate an RTOS port once timer interrupts, context switching, memory,
  and compiled firmware support are verified.

## Separate future scope: Linux with virtual memory

- [ ] Decide whether conventional Linux support is a project goal and choose
  its supported ISA/ABI and platform requirements before implementation.
- [ ] Add supervisor/user modes, supervisor CSRs, trap delegation, and
  supervisor trap entry/return.
- [ ] Add an Sv32 MMU, page-table walking, permission checks, page faults,
  and `SFENCE.VMA`; evaluate a TLB for performance.
- [ ] Add the atomic support required by the selected software configuration.
- [ ] Provide much larger RAM, boot firmware/SBI as appropriate, a device tree,
  console, and a way to load the kernel and root filesystem.

The project name `SV32` does not mean the core currently implements the
RISC-V Sv32 virtual-memory scheme.

## References

- [RV32I and alignment rules](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html)
- [Zicsr instruction semantics](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html)
- [Machine-level architecture](https://docs.riscv.org/reference/isa/v20260120/priv/machine.html)
- [Supervisor architecture and Sv32](https://docs.riscv.org/reference/isa/priv/supervisor.html)
- [RISC-V architectural tests](https://github.com/riscv/riscv-arch-test)
- [Spike reference simulator](https://github.com/riscv-software-src/riscv-isa-sim)
- [Linux RISC-V boot requirements](https://docs.kernel.org/arch/riscv/boot.html)
