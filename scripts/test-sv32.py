#!/usr/bin/env python3
"""Run DSLX unit tests, build RV32I RTL, and simulate programs.

The generated testbench loads `imem.hex`/`dmem.hex`, runs until the core
halts, and dumps its register file and data memory. This script compares that
dump against the Python reference model in tests/sv32/sv32_ref.py.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "sv32"))
import sv32_ref
import sv32_cases


def testbench(imem_words, dmem_words, max_cycles, module):
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
  reg [31:0] reset_dmem [0:DMEM_WORDS-1];

  {module} dut (
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
    for (i = 0; i < DMEM_WORDS; i = i + 1) reset_dmem[i] = dmem[i];
    repeat (2) begin
      @(negedge clk);
      if (dmem_wstrb !== 4'b0) $fatal(1, "store strobes active during reset");
      for (i = 0; i < DMEM_WORDS; i = i + 1)
        if (dmem[i] !== reset_dmem[i]) $fatal(1, "memory changed during reset");
    end
    rst_n = 1;
    #1;
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
    pc = cycles = None
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
                elif token.startswith("pc="):
                    pc = int(token.split("=")[1], 16)
    return registers, memory, halted, pc, cycles


def simulate_program(output, core, program, max_cycles, module):
    output.mkdir(parents=True, exist_ok=True)
    imem = program.instructions
    dmem_init = program.data
    dmem_words = program.data_words
    expected_regs, expected_pc, expected_mem, expected_cycles, expected_halt = \
        sv32_ref.run(imem, dmem_init, dmem_words, max_cycles)
    if not expected_halt:
        raise SystemExit(f"{program.name}: reference did not halt within {max_cycles} cycles")
    # Directed expectations catch shared decoder mistakes in RTL and reference.
    for index, value in program.registers.items():
        if expected_regs[index] != value:
            raise SystemExit(f"{program.name}: reference x{index} differs from directed expectation")
    for index, value in program.memory.items():
        if expected_mem[index] != value:
            raise SystemExit(f"{program.name}: reference dmem[{index}] differs from directed expectation")
    if program.halt_pc is not None and expected_pc != program.halt_pc:
        raise SystemExit(f"{program.name}: reference halt PC differs from directed expectation")

    imem_words = 1
    while imem_words < len(imem):
        imem_words <<= 1
    write_hex(output / "imem.hex", imem, imem_words)
    write_hex(output / "dmem.hex", dmem_init, dmem_words)
    (output / "tb.sv").write_text(testbench(imem_words, dmem_words, max_cycles, module))
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", output / "sim.vvp",
                    core / "sv32_core.v", core / "sv32_top.sv", output / "tb.sv"],
                   cwd=ROOT, check=True, timeout=1800)
    result = subprocess.run(["vvp", "sim.vvp"], cwd=output,
                            text=True, capture_output=True, timeout=1800)
    (output / "simulation.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit(f"{program.name}: simulation failed\n" + result.stdout + result.stderr)
    registers, memory, halted, pc, cycles = parse_simulation(result.stdout)
    if not halted:
        raise SystemExit(f"{program.name}: simulation did not report a halt\n" + result.stdout)

    errors = []
    for index, expected in enumerate(expected_regs):
        actual = registers.get(index)
        if actual != expected:
            errors.append(f"x{index}: RTL={actual!r} ref={expected:#010x}")
    for index, expected in enumerate(expected_mem):
        actual = memory.get(index)
        if actual != (expected & 0xFFFFFFFF):
            errors.append(f"dmem[{index}]: RTL={actual!r} ref={expected:#010x}")
    if pc != expected_pc:
        errors.append(f"halt PC: RTL={pc!r} ref={expected_pc:#010x}")
    if cycles is None or cycles + 1 != expected_cycles:
        errors.append(f"cycles before halt: RTL={cycles!r} ref={expected_cycles - 1}")
    if errors:
        raise SystemExit(f"{program.name}: RTL/reference mismatch:\n  " + "\n  ".join(errors))
    print(f"PASS: {program.name}: RTL matched the reference for {expected_cycles} cycles")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-dslx", action="store_true")
    parser.add_argument("--simulate-only", type=Path,
                        help="simulate an existing build directory")
    parser.add_argument("--max-cycles", type=int, default=2000)
    parser.add_argument("--top-module",
                        help="module under test (default: clocked core from config.json)")
    args = parser.parse_args()
    if args.max_cycles < 1:
        parser.error("--max-cycles must be positive")

    if not shutil.which("iverilog") or not shutil.which("vvp"):
        raise SystemExit("RTL tests need iverilog and vvp on PATH")

    if args.simulate_only:
        output = args.simulate_only.resolve()
    else:
        if not args.skip_dslx:
            subprocess.run([str(ROOT / "bin/xls"), "interpreter_main",
                            "--dslx_path=" + str(ROOT / "src" / "sv32"),
                            "--compare=jit", "--lower_to_ir=true",
                            "--convert_tests=true", "--seed=42",
                            str(ROOT / "tests" / "sv32" / "sv32_test.x")],
                           cwd=ROOT, check=True, timeout=600)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build-sv32.py")],
                       cwd=ROOT, check=True, timeout=1800)
        output = ROOT / "build" / "sv32"

    config_path = output / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    module = args.top_module or (config["core_module"] if config.get("interface") == "clocked_harvard"
                                else "sv32_top")
    print(f"Compiling and simulating {module} regression programs", flush=True)
    count = 0
    for program in sv32_cases.programs():
        case_output = output if program.name == "demo" else output / "cases" / program.name
        simulate_program(case_output, output, program, args.max_cycles, module)
        count += 1
    print(f"PASS: {count} RTL programs; all registers, data words, halt PCs, and cycles checked")
    print(f"Outputs in {output}")


if __name__ == "__main__":
    main()
