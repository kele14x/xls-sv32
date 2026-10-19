#!/usr/bin/env python3
"""Compile bare-metal blinky.c into the SV32 instruction ROM image."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DELAY = 24_999_996
DEFAULT_PREFIX = "riscv32-unknown-elf-"
IMEM_BYTES = 1024


def build(output, delay_iterations=DEFAULT_DELAY, toolchain_prefix=DEFAULT_PREFIX):
    if not 1 <= delay_iterations <= 0xFFFFFFFF:
        raise ValueError("delay iterations must be between 1 and 0xffffffff")
    tools = {name: shutil.which(toolchain_prefix + name)
             for name in ("gcc", "objcopy", "objdump", "size", "nm")}
    if any(path is None for path in tools.values()):
        missing = ", ".join(toolchain_prefix + name for name, path in tools.items() if path is None)
        raise SystemExit("RISC-V tools missing from PATH: " + missing)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    elf = output / "blinky.elf"
    flags = ["-march=rv32i", "-mabi=ilp32", "-mno-relax", "-msmall-data-limit=0",
             "-Os", "-g", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie",
             "-fno-stack-protector", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
             "-Wall", "-Wextra", "-Werror", "-nostdlib", "-nostartfiles",
             "-Wl,--no-relax,--build-id=none", "-T", str(ROOT / "programs/sv32.ld"),
             "-Wl,-Map=" + str(output / "blinky.map"),
             "-DDELAY_ITERATIONS=" + str(delay_iterations) + "u"]
    subprocess.run([tools["gcc"], *flags, str(ROOT / "programs/crt0.S"),
                    str(ROOT / "programs/blinky.c"), "-o", str(elf)], check=True, timeout=120)
    binary = output / "blinky.bin"
    subprocess.run([tools["objcopy"], "-O", "binary", "--only-section=.text",
                    str(elf), str(binary)], check=True, timeout=30)
    data = binary.read_bytes()
    if not data or len(data) > IMEM_BYTES or len(data) % 4:
        raise SystemExit("Firmware must fit the 1 KiB ROM as complete 32-bit instructions")
    words = [int.from_bytes(data[offset:offset + 4], "little")
             for offset in range(0, len(data), 4)]
    padded = words + [0] * (IMEM_BYTES // 4 - len(words))
    (output / "blinky.hex").write_text("".join(f"{word:08x}\n" for word in padded))
    listing = subprocess.run([tools["objdump"], "-d", "-S", str(elf)],
                             check=True, capture_output=True, text=True, timeout=30)
    (output / "blinky.lst").write_text(listing.stdout)
    sizes = subprocess.run([tools["size"], str(elf)], check=True, capture_output=True,
                           text=True, timeout=30)
    (output / "blinky.size").write_text(sizes.stdout)
    symbol_output = subprocess.run([tools["nm"], "-n", str(elf)], check=True,
                                  capture_output=True, text=True, timeout=30)
    symbols = {fields[2]: int(fields[0], 16)
               for line in symbol_output.stdout.splitlines()
               if len(fields := line.split()) == 3}
    version = subprocess.run([tools["gcc"], "--version"], check=True, capture_output=True,
                             text=True, timeout=30).stdout.splitlines()[0]
    config = {"source": "programs/blinky.c", "compiler": version, "compiler_path": tools["gcc"],
              "architecture": "rv32i", "abi": "ilp32", "flags": flags,
              "entry_address": symbols["_start"], "text_bytes": len(data),
              "imem_bytes": IMEM_BYTES, "ram_base": 0x1000, "ram_bytes": 1024,
              "stack_top": symbols["__stack_top"], "stack_bottom": symbols["__stack_bottom"],
              "bss_start": symbols["__bss_start"], "bss_end": symbols["__bss_end"],
              "blink_count_address": symbols["blink_count"],
              "delay_iterations": delay_iterations}
    (output / "firmware-config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"C firmware: {len(data)} / {IMEM_BYTES} ROM bytes; RV32I/ILP32; {elf}", flush=True)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/firmware/blinky")
    parser.add_argument("--delay-iterations", type=int, default=DEFAULT_DELAY)
    parser.add_argument("--toolchain-prefix", default=DEFAULT_PREFIX)
    args = parser.parse_args()
    if not 1 <= args.delay_iterations <= 0xFFFFFFFF:
        parser.error("--delay-iterations must be between 1 and 0xffffffff")
    build(args.output_dir, args.delay_iterations, args.toolchain_prefix)


if __name__ == "__main__":
    main()
