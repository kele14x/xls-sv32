#!/usr/bin/env python3
"""Generate the entire clocked RV32I core from a stateful DSLX proc.

The only IR adaptation selects single-value channels for the plain memory
ports. XLS generates all core RTL, including architectural state and reset.
A separate wiring-only sv32_top alias preserves the original reset interface.
Run scripts/test-sv32.py to build and simulate in one step.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Module-signature parsing
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r'\s*(\{|\}|:|"[^"]*"|[^\s{}:]+)')


def parse_signature(text):
    """Parse the small textproto subset used by XLS module signatures."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    tokens = _TOKEN.findall("\n".join(lines))
    position = 0

    def parse_message():
        nonlocal position
        message = {}
        while position < len(tokens):
            token = tokens[position]
            if token == "}":
                position += 1
                return message
            position += 1
            name = token
            if tokens[position] == ":":
                position += 1
                value = tokens[position].strip('"')
                position += 1
                message.setdefault(name, []).append(value)
            elif tokens[position] == "{":
                position += 1
                message.setdefault(name, []).append(parse_message())
            else:
                raise ValueError(f"unexpected token {tokens[position]!r} after {name!r}")
        return message

    return parse_message()


def run_tool(tool, arguments, destination):
    print(f"Running {tool}", flush=True)
    try:
        with destination.open("w") as stream:
            subprocess.run([str(ROOT / "bin/xls"), tool, *map(str, arguments)],
                           cwd=ROOT, stdout=stream, check=True, timeout=1800)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"{tool} timed out")


# Public data ports emitted directly by XLS. Clock/reset are codegen ports.
PORTS = {
    "imem_rdata": ("input", 32),
    "dmem_rdata": ("input", 32),
    "reset_n": ("input", 1),
    "imem_addr": ("output", 32),
    "dmem_addr": ("output", 32),
    "dmem_wdata": ("output", 32),
    "dmem_wstrb": ("output", 4),
    "halted": ("output", 1),
    "debug_pc": ("output", 32),
    "debug_regs": ("output", 1024),
}


def single_value_ports(ir):
    """Lower the pinned DSLX frontend's streaming ports to plain XLS wires.

    This is interface metadata only: state, init, next_value, and all logic
    remain the DSLX compiler's IR. Do this before optimization/scheduling.
    Fail closed if the frontend changes its channel representation.
    """
    pattern = re.compile(r"^(  chan_interface )(\w+)\(([^\n]+)\)$", re.MULTILINE)
    names = {}

    def lower(match):
        old_name = match[2]
        name = old_name.removeprefix("_")
        if name not in PORTS or name in names.values():
            raise ValueError(f"unexpected or duplicate core channel: {old_name}")
        attributes = dict(item.split("=", 1) for item in match[3].split(", "))
        direction = "receive" if PORTS[name][0] == "input" else "send"
        expected = {
            "direction": direction, "kind": "streaming",
            "strictness": "proven_mutually_exclusive",
            "flow_control": "ready_valid", "flop_kind": "none",
        }
        if attributes != expected:
            raise ValueError(f"unexpected channel attributes: {match[0]}")
        names[old_name] = name
        return f"{match[1]}{old_name}(direction={direction}, kind=single_value)"

    ir = pattern.sub(lower, ir)
    if set(names.values()) != set(PORTS):
        raise ValueError("core channels do not match the expected Harvard interface")
    # Rename identifier tokens, not substrings (or source filenames).
    identifiers = re.compile(r'"[^"\n]*"|\b[A-Za-z_][A-Za-z_0-9]*\b')
    return identifiers.sub(lambda match: names.get(match[0], match[0]), ir)


def validate_signature(signature, module):
    actual = {
        port["name"][0]: (port["direction"][0], int(port["width"][0]))
        for port in signature["data_ports"]
    }
    expected = {name: ("PORT_DIRECTION_" + direction.upper(), width)
                for name, (direction, width) in PORTS.items()}
    if actual != expected or signature["module_name"] != [module]:
        raise ValueError("XLS generated an unexpected core interface")
    if signature.get("clock_name") != ["clk"]:
        raise ValueError("XLS core is missing its clock")
    pipeline = signature.get("pipeline", [{}])[0]
    if (pipeline.get("latency") != ["0"]
            or pipeline.get("initiation_interval") != ["1"]):
        raise ValueError("XLS core must execute every cycle without registered I/O")
    reset = signature["reset"][0]
    if (reset["name"] != ["rst_n"] or reset["asynchronous"] != ["true"]
            or reset["active_low"] != ["true"]):
        raise ValueError("XLS core reset must remain asynchronous and active-low")


def wrapper(module):
    """A wiring-only alias preserving the original single-reset interface."""
    ports = ["    input wire clk", "    input wire rst_n"]
    connections = [".clk(clk)", ".rst_n(rst_n)", ".reset_n(rst_n)"]
    for name, (direction, width) in PORTS.items():
        if name == "reset_n":
            continue
        size = f" [{width - 1}:0]" if width > 1 else ""
        ports.append(f"    {direction} wire{size} {name}")
        connections.append(f".{name}({name})")
    return ("// Generated compatibility wiring; all core logic is XLS-generated.\n"
            "`default_nettype none\nmodule sv32_top (\n" + ",\n".join(ports) +
            f"\n);\n  {module} core (\n      " + ",\n      ".join(connections) +
            "\n  );\nendmodule\n`default_nettype wire\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        help="build directory (default build/sv32)")
    parser.add_argument("--module-name", default="sv32_core")
    args = parser.parse_args()
    if args.module_name == "sv32_top":
        parser.error("--module-name cannot be sv32_top (reserved for the compatibility wrapper)")

    output = (args.output_dir or ROOT / "build/sv32").resolve()
    output.mkdir(parents=True, exist_ok=True)
    dslx_ir = output / "sv32.dslx.ir"
    ir = output / "sv32.ir"
    run_tool("ir_converter_main",
             ["--dslx_path=" + str(ROOT / "src/sv32"),
              "--lower_to_proc_scoped_channels=true", "--top=sv32_core",
              ROOT / "src/sv32/sv32_core.x"], dslx_ir)
    ir.write_text(single_value_ports(dslx_ir.read_text()))
    run_tool("opt_main", [ir], output / "sv32.opt.ir")
    signature_path = output / "sv32_core.sig.textproto"
    core_path = output / "sv32_core.v"
    # One proc activation per clock, combinational memory ports. XLS generates
    # all state registers from the proc; never prepend or patch core RTL.
    run_tool("codegen_main",
             ["--generator=pipeline", "--pipeline_stages=1", "--delay_model=unit",
              "--flop_inputs=false", "--flop_outputs=false",
              "--flop_single_value_channels=false",
              "--reset=rst_n", "--reset_active_low=true", "--reset_asynchronous=true",
              "--reset_data_path=true", f"--module_name={args.module_name}",
              "--use_system_verilog=false",
              f"--output_signature_path={signature_path}",
              f"--output_schedule_path={output / 'sv32.schedule.textproto'}",
              output / "sv32.opt.ir"], core_path)
    validate_signature(parse_signature(signature_path.read_text()), args.module_name)
    (output / "sv32_top.sv").write_text(wrapper(args.module_name))
    (output / "config.json").write_text(json.dumps({
        "module": args.module_name,
        "isa": "RV32I",
        "generator": "pipeline",
        "pipeline_stages": 1,
        "interface": "clocked_harvard",
        "core_module": args.module_name,
        "dslx_top": "sv32_core",
        "channel_kind": "single_value",
        "reset_data_port": "reset_n",
    }, indent=2) + "\n")
    print(f"Generated {core_path} and {output / 'sv32_top.sv'}")


if __name__ == "__main__":
    main()
