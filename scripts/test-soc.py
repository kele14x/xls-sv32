#!/usr/bin/env python3
"""Simulate synthesizable memories, the blinky SoC, and the board wrapper."""

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


def simulate(folder, sources, parameters=()):
    folder.mkdir(parents=True, exist_ok=True)
    executable = folder / "sim.vvp"
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                    *["-P" + value for value in parameters],
                    *map(str, sources)],
                   cwd=ROOT, check=True, timeout=120)
    result = subprocess.run(["vvp", str(executable)], cwd=folder,
                            text=True, capture_output=True, timeout=120)
    (folder / "simulation.log").write_text(result.stdout + result.stderr)
    print(result.stdout, end="")
    if result.returncode or "PASS:" not in result.stdout:
        raise SystemExit("Simulation failed:\n" + result.stdout + result.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/sv32_soc_test")
    parser.add_argument("--delay-iterations", type=int, default=8)
    parser.add_argument("--firmware", choices=("python", "c"), default="python")
    parser.add_argument("--toolchain-prefix", default=build_soc.build_firmware.DEFAULT_PREFIX)
    args = parser.parse_args()
    if not 1 <= args.delay_iterations <= 10000:
        parser.error("simulation delay must be between 1 and 10000")
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        parser.error("install Icarus Verilog (iverilog/vvp) for SoC tests")
    output = build_soc.build(args.output_dir, args.delay_iterations,
                             args.firmware, args.toolchain_prefix)
    memory_folder = output / "memories"
    memory_folder.mkdir(parents=True, exist_ok=True)
    (memory_folder / "memory.hex").write_text("11223344\n55667788\n12345678\ncafebabe\n")
    simulate(memory_folder, [*build_soc.SOC_SOURCES[:2], ROOT / "tests/sv32_soc/memories_tb.sv"])
    parameters = [f"tb.DELAY_ITERATIONS={args.delay_iterations}",
                  "tb.IMEM_INIT_FILE=" + json.dumps(str(output / "blinky.hex"))]
    if args.firmware == "c":
        config = json.loads((output / "firmware-config.json").read_text())
        bench = ROOT / "tests/sv32_soc/c_blinky_tb.sv"
        c_parameters = [*parameters,
                        f"tb.BSS_START={config['bss_start']}",
                        f"tb.BSS_END={config['bss_end']}",
                        f"tb.COUNTER_ADDRESS={config['blink_count_address']}"]
        simulate(output / "rtl", [output / "sv32_core.v", *build_soc.SOC_SOURCES, bench], c_parameters)
    else:
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
                               ROOT / "tests/sv32_soc/de25_tb.sv"],
             [*parameters, "tb.C_FIRMWARE=" + str(int(args.firmware == "c"))])


if __name__ == "__main__":
    main()
