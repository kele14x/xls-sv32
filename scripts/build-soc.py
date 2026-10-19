#!/usr/bin/env python3
"""Build SV32 and the blinky ROM image for a 100 MHz SoC."""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "programs"))
from blinky import DEFAULT_DELAY, program

spec = importlib.util.spec_from_file_location("build_firmware", ROOT / "scripts/build-firmware.py")
build_firmware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_firmware)

SOC_SOURCES = [ROOT / "src/sv32_soc" / name
               for name in ("sv32_imem.v", "sv32_dmem.v", "sv32_soc.v")]


def build(output, delay_iterations=DEFAULT_DELAY, firmware="python",
          toolchain_prefix=build_firmware.DEFAULT_PREFIX):
    if firmware not in ("python", "c"):
        raise ValueError("firmware must be 'python' or 'c'")
    output = output.resolve()
    subprocess.run([sys.executable, str(ROOT / "scripts/build-sv32.py"),
                    "--output-dir", str(output)], cwd=ROOT, check=True, timeout=1800)
    if firmware == "c":
        build_firmware.build(output, delay_iterations, toolchain_prefix)
    else:
        instructions = program(delay_iterations)
        words = [word for word, _ in instructions] + [0] * (256 - len(instructions))
        (output / "blinky.hex").write_text("".join(f"{word:08x}\n" for word in words))
        (output / "blinky.lst").write_text("".join(
            f"{index * 4:08x}  {word:08x}  {assembly}\n"
            for index, (word, assembly) in enumerate(instructions)))
    sources = [output / "sv32_core.v", *SOC_SOURCES]
    (output / "files.f").write_text("".join(f'"{path}"\n' for path in sources))
    (output / "soc-config.json").write_text(json.dumps({
        "top": "sv32_soc", "clock_hz": 100_000_000, "firmware": firmware,
        "delay_iterations": delay_iterations,
        "toggle_cycles": 2 * delay_iterations + 8 if firmware == "python" else None,
        "imem_words": 256, "dmem_words": 256,
        "ram_base": "0x00001000", "led_address": "0x10000000",
        "imem_init_file": str(output / "blinky.hex"),
    }, indent=2) + "\n")
    if firmware == "python":
        print(f"Blinky: {len(instructions)} instructions, LED toggles every "
              f"{(2 * delay_iterations + 8) / 100_000_000:g} seconds at 100 MHz")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/sv32_soc")
    parser.add_argument("--delay-iterations", type=int, default=DEFAULT_DELAY)
    parser.add_argument("--firmware", choices=("python", "c"), default="python")
    parser.add_argument("--toolchain-prefix", default=build_firmware.DEFAULT_PREFIX)
    args = parser.parse_args()
    if not 1 <= args.delay_iterations <= 0xFFFFFFFF:
        parser.error("--delay-iterations must be between 1 and 0xffffffff")
    build(args.output_dir, args.delay_iterations, args.firmware, args.toolchain_prefix)


if __name__ == "__main__":
    main()
