#!/usr/bin/env python3
"""Run DSLX unit tests, build RV32I RTL, and simulate programs.

The generated testbench loads `imem.hex`/`dmem.hex`, runs until the core
halts, and dumps its register file and data memory. This script compares that
dump against the Python reference model in tests/riscv_core/rv32_ref.py.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "riscv_core"))
import rv32_ref


def testbench(imem_words, dmem_words, max_cycles):
    return f'''`timescale 1ns/1ps
module tb;
  localparam IMEM_WORDS = {imem_words};
  localparam DMEM_WORDS = {dmem_words};
  localparam IMEM_AW = $clog2(IMEM_WORDS);
  localparam DMEM_AW = $clog2(DMEM_WORDS);
  localparam MAX_CYCLES = {max_cycles};

  reg clk = 0;
  always #5 clk = ~clk;
  reg rst_n = 0;

  wire [31:0] imem_addr, imem_rdata;
  wire [31:0] dmem_addr, dmem_wdata, dmem_rdata;
  wire [3:0] dmem_wstrb;
  wire halted;
  wire [31:0] debug_pc;
  wire [1023:0] debug_regs;

  reg [31:0] imem [0:IMEM_WORDS-1];
  reg [31:0] dmem [0:DMEM_WORDS-1];

  riscv_top dut (
      .clk(clk), .rst_n(rst_n),
      .imem_addr(imem_addr), .imem_rdata(imem_rdata),
      .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata),
      .dmem_wstrb(dmem_wstrb), .dmem_rdata(dmem_rdata),
      .halted(halted), .debug_pc(debug_pc), .debug_regs(debug_regs)
  );

  assign imem_rdata = imem[imem_addr[IMEM_AW+1:2]];
  assign dmem_rdata = dmem[dmem_addr[DMEM_AW+1:2]];

  always @(posedge clk) begin
    if (dmem_wstrb[0]) dmem[dmem_addr[DMEM_AW+1:2]][7:0]   <= dmem_wdata[7:0];
    if (dmem_wstrb[1]) dmem[dmem_addr[DMEM_AW+1:2]][15:8]  <= dmem_wdata[15:8];
    if (dmem_wstrb[2]) dmem[dmem_addr[DMEM_AW+1:2]][23:16] <= dmem_wdata[23:16];
    if (dmem_wstrb[3]) dmem[dmem_addr[DMEM_AW+1:2]][31:24] <= dmem_wdata[31:24];
  end

  integer i, cycles;
  initial begin
    $readmemh("imem.hex", imem);
    $readmemh("dmem.hex", dmem);
    repeat (2) @(negedge clk);
    rst_n = 1;
    cycles = 0;
    while (!halted && cycles < MAX_CYCLES) begin
      @(negedge clk);
      cycles = cycles + 1;
    end
    if (!halted) $fatal(1, "timeout after %0d cycles", cycles);
    $display("HALT pc=%08x cycles=%0d", debug_pc, cycles);
    for (i = 0; i < 32; i = i + 1)
      $display("REG %0d %08x", i, debug_regs[i*32 +: 32]);
    for (i = 0; i < DMEM_WORDS; i = i + 1)
      $display("MEM %0d %08x", i, dmem[i]);
    $finish;
  end
endmodule
'''


def write_hex(path, values, count):
    words = list(values) + [0] * (count - len(values))
    path.write_text("".join(f"{word & 0xFFFFFFFF:08x}\n" for word in words))


def parse_simulation(log):
    registers, memory = {}, {}
    halted = False
    cycles = None
    for line in log.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "REG":
            registers[int(parts[1])] = int(parts[2], 16)
        elif len(parts) == 3 and parts[0] == "MEM":
            memory[int(parts[1])] = int(parts[2], 16)
        elif line.startswith("HALT"):
            halted = True
            for token in parts[1:]:
                if token.startswith("cycles="):
                    cycles = int(token.split("=")[1])
    return registers, memory, halted, cycles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-dslx", action="store_true")
    parser.add_argument("--simulate-only", type=Path,
                        help="simulate an existing build directory")
    parser.add_argument("--max-cycles", type=int, default=2000)
    args = parser.parse_args()

    if not shutil.which("iverilog") or not shutil.which("vvp"):
        raise SystemExit("RTL tests need iverilog and vvp on PATH")

    if args.simulate_only:
        output = args.simulate_only.resolve()
    else:
        if not args.skip_dslx:
            subprocess.run([str(ROOT / "bin/xls"), "interpreter_main",
                            "--dslx_path=" + str(ROOT / "src" / "riscv_core"),
                            "--compare=jit", "--lower_to_ir=true",
                            "--convert_tests=true", "--seed=42",
                            str(ROOT / "tests" / "riscv_core" / "riscv_core_test.x")],
                           cwd=ROOT, check=True, timeout=600)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build-riscv.py")],
                       cwd=ROOT, check=True, timeout=1800)
        output = ROOT / "build" / "riscv_core"

    imem, dmem_init, dmem_words = rv32_ref.demo_program()
    imem_words = 1
    while imem_words < len(imem):
        imem_words <<= 1
    write_hex(output / "imem.hex", imem, imem_words)
    write_hex(output / "dmem.hex", dmem_init, dmem_words)
    (output / "tb.sv").write_text(testbench(imem_words, dmem_words, args.max_cycles))

    print("Compiling RTL with Icarus Verilog", flush=True)
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", output / "sim.vvp",
                    output / "riscv_core.v", output / "riscv_top.sv", output / "tb.sv"],
                   cwd=ROOT, check=True, timeout=1800)
    print("Simulating", flush=True)
    result = subprocess.run(["vvp", "sim.vvp"], cwd=output, check=True,
                            text=True, capture_output=True, timeout=1800)
    registers, memory, halted, cycles = parse_simulation(result.stdout)
    if not halted:
        raise SystemExit("simulation did not report a halt\n" + result.stdout)

    expected_regs, expected_pc, expected_mem, expected_cycles, expected_halt = \
        rv32_ref.run(imem, dmem_init, dmem_words)
    errors = []
    for index in range(32):
        actual = registers.get(index)
        if actual != expected_regs[index]:
            errors.append(f"x{index}: RTL={actual:#010x} ref={expected_regs[index]:#010x}")
    for index in range(dmem_words):
        actual = memory.get(index)
        if actual != (expected_mem[index] & 0xFFFFFFFF):
            errors.append(f"dmem[{index}]: RTL={actual:#010x} ref={expected_mem[index]:#010x}")
    if expected_halt and cycles is not None and cycles + 1 != expected_cycles:
        errors.append(f"cycles: RTL={cycles + 1} ref={expected_cycles}")
    if errors:
        raise SystemExit("RTL/reference mismatch:\n  " + "\n  ".join(errors))

    print(f"PASS: RTL matched the reference model for {expected_cycles} cycles")
    print(f"Registers checked: 32, data words checked: {dmem_words}")
    print(f"Outputs in {output}")


if __name__ == "__main__":
    main()
