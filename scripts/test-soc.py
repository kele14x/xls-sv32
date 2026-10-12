#!/usr/bin/env python3
"""Simulate synthesizable memories and the blinky SoC, optionally after synthesis."""

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_soc", ROOT / "scripts/build-soc.py")
build_soc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_soc)
sys.path.insert(0, str(ROOT / "tests/sv32"))
sys.path.insert(0, str(ROOT / "tests/sv32_soc"))
import mmio_probe


def simulate(folder, sources, parameters=(), defines=()):
    folder.mkdir(parents=True, exist_ok=True)
    executable = folder / "sim.vvp"
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                    *["-P" + value for value in parameters],
                    *["-D" + value for value in defines], *map(str, sources)],
                   cwd=ROOT, check=True, timeout=120)
    result = subprocess.run(["vvp", str(executable)], cwd=folder,
                            text=True, capture_output=True, timeout=120)
    (folder / "simulation.log").write_text(result.stdout + result.stderr)
    print(result.stdout, end="")
    if result.returncode or "PASS:" not in result.stdout:
        raise SystemExit("Simulation failed:\n" + result.stdout + result.stderr)


def synthesize(output):
    """Map the actual ROM/RAM/core to generic gates and verify that netlist."""
    folder = output / "yosys"
    folder.mkdir(parents=True, exist_ok=True)
    # read_slang passes -G values to Slang; keep the Verilog string quotes.
    image = json.dumps(str(output / "blinky.hex"))
    script = folder / "synth.ys"
    script.write_text(
        "read_slang --top sv32_soc -G IMEM_INIT_FILE=" + image +
        f" -f {output / 'files.f'}\n"
        "synth -top sv32_soc\ncheck -assert\nstat\n"
        f"write_verilog -noattr {json.dumps(str(folder / 'sv32_soc.v'))}\n")
    result = subprocess.run([str(ROOT / "bin/yosys"), "-Q", "-T", "-s", str(script)],
                            cwd=ROOT, text=True, capture_output=True, timeout=600)
    (folder / "synth.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit("SoC synthesis failed:\n" + result.stdout[-6000:] + result.stderr)
    print("PASS: Yosys synthesis and structural checks")
    return folder / "sv32_soc.v"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/sv32_soc_test")
    parser.add_argument("--delay-iterations", type=int, default=8)
    parser.add_argument("--synthesize", action="store_true", help="also simulate a Yosys gate netlist")
    args = parser.parse_args()
    if not 1 <= args.delay_iterations <= 10000:
        parser.error("simulation delay must be between 1 and 10000")
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        parser.error("install Icarus Verilog (iverilog/vvp) for SoC tests")
    output = build_soc.build(args.output_dir, args.delay_iterations)
    memory_folder = output / "memories"
    memory_folder.mkdir(parents=True, exist_ok=True)
    (memory_folder / "memory.hex").write_text("11223344\n55667788\n12345678\ncafebabe\n")
    simulate(memory_folder, [*build_soc.SOC_SOURCES[:2], ROOT / "tests/sv32_soc/memories_tb.sv"])
    parameters = [f"tb.DELAY_ITERATIONS={args.delay_iterations}",
                  "tb.IMEM_INIT_FILE=" + json.dumps(str(output / "blinky.hex"))]
    bench = ROOT / "tests/sv32_soc/blinky_tb.sv"
    simulate(output / "rtl", [output / "sv32_core.v", *build_soc.SOC_SOURCES, bench], parameters)
    words, halt_pc = mmio_probe.program()
    (output / "mmio.hex").write_text("".join(f"{word:08x}\n" for word in words + [0] * (256 - len(words))))
    simulate(output / "mmio", [output / "sv32_core.v", *build_soc.SOC_SOURCES,
                               ROOT / "tests/sv32_soc/mmio_tb.sv"],
             ["tb.IMEM_INIT_FILE=" + json.dumps(str(output / "mmio.hex")),
              f"tb.EXPECTED_PC={halt_pc}"])
    simulate(output / "de25", [output / "sv32_core.v", *build_soc.SOC_SOURCES,
                               ROOT / "boards/de25_nano/sv32_de25_nano.v",
                               ROOT / "tests/sv32_soc/de25_tb.sv"], parameters)
    if args.synthesize:
        netlist = synthesize(output)
        simulate(output / "gate", [netlist, bench], parameters[:1], ["GATE_SIM"])


if __name__ == "__main__":
    main()
