#!/usr/bin/env python3
"""Build a DE25-NANO Quartus project for the 100 MHz blinky SoC."""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_soc", ROOT / "scripts/build-soc.py")
build_soc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_soc)


def verify_timing(output):
    reports = output / "output_files"
    text = (reports / "sv32_de25_nano.sta.rpt").read_text()
    cpu_clock = None
    for line in text.splitlines():
        fields = [field.strip() for field in line.split(";")]
        if (len(fields) > 4 and fields[1].endswith("pll_outclk0") and
                fields[2] == "Generated" and float(fields[3]) == 10.0):
            cpu_clock = fields[1]
            break
    summary = (reports / "sv32_de25_nano.sta.summary").read_text()
    checks = [{"check": name, "slack_ns": float(slack)} for name, slack in
              re.findall(r"Type\s*:\s*([^\n]+)\nSlack\s*:\s*(-?[\d.]+)", summary)]
    required = {f"Setup '{cpu_clock}'", f"Hold '{cpu_clock}'"}
    if (not cpu_clock or not required.issubset({check["check"] for check in checks}) or
            any(check["slack_ns"] < 0 for check in checks)):
        raise SystemExit("100 MHz timing verification failed; inspect output_files/*.sta.rpt")
    (output / "timing-verification.json").write_text(json.dumps({
        "cpu_clock": cpu_clock, "period_ns": 10.0, "checks": checks,
    }, indent=2) + "\n")
    print("PASS: 100 MHz CPU clock and all reported timing checks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/de25_nano")
    parser.add_argument("--compile", action="store_true", help="also run the full Quartus flow")
    args = parser.parse_args()
    quartus = shutil.which("quartus_sh")
    if not quartus:
        parser.error("Quartus Prime Pro must be on PATH to generate the board clock/reset IP")
    qsys_bin = Path(quartus).resolve().parents[2] / "qsys/bin"
    output = build_soc.build(args.output_dir)
    board = ROOT / "boards/de25_nano"
    sources = [output / "sv32_core.v", *build_soc.SOC_SOURCES, board / "sv32_de25_nano.v"]
    qsf = [f"source {json.dumps(str(board / 'pins.qsf'))}",
           'set_global_assignment -name TOP_LEVEL_ENTITY sv32_de25_nano',
           'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
           'set_global_assignment -name NUM_PARALLEL_PROCESSORS 8',
           f"set_global_assignment -name SDC_FILE {json.dumps(str(board / 'timing.sdc'))}",
           "set_parameter -name IMEM_INIT_FILE " + json.dumps(json.dumps(str(output / "blinky.hex")))]
    qsf.extend("set_global_assignment -name VERILOG_FILE " + json.dumps(str(path))
               for path in sources)
    (output / "sv32_de25_nano.qsf").write_text("\n".join(qsf) + "\n")
    (output / "sv32_de25_nano.qpf").write_text('PROJECT_REVISION = "sv32_de25_nano"\n')
    commands = [
        [str(qsys_bin / "qsys-script"), "--quartus-project=sv32_de25_nano",
         "--script=" + str(board / "create-clocking.tcl")],
        [str(qsys_bin / "qsys-generate"), "sv32_clocking.qsys",
         "--quartus-project=sv32_de25_nano", "--synthesis=VERILOG", "--parallel=off"],
    ]
    for command in commands:
        print("Running " + Path(command[0]).name, flush=True)
        result = subprocess.run(command, cwd=output, text=True, capture_output=True, timeout=300)
        (output / (Path(command[0]).name + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit("Clock/reset IP generation failed:\n" + result.stdout + result.stderr)
    # Platform Designer adds QSYS_FILE and child IP_FILE assignments to the
    # project. Adding its generated QIP as well would duplicate the same IP.
    print(f"Quartus project: {output / 'sv32_de25_nano.qpf'}", flush=True)
    if args.compile:
        print("Running Quartus synthesis, fitting, timing, and assembly", flush=True)
        result = subprocess.run([quartus, "--flow", "compile", "sv32_de25_nano"],
                                cwd=output, text=True, capture_output=True, timeout=3600)
        (output / "quartus-build.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit("Quartus compilation failed; see " + str(output / "quartus-build.log"))
        verify_timing(output)
        print(f"Compiled {output / 'output_files/sv32_de25_nano.sof'}")


if __name__ == "__main__":
    main()
