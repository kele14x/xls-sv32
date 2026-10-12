#!/usr/bin/env python3
"""Generate a clocked RV32I core with explicit instruction/data memory ports.

The DSLX `step` function is purely combinational. This script:

1. Converts and optimizes it to XLS IR.
2. Emits an internal combinational datapath plus its module signature.
3. Parses the signature to connect named PC/register state to the datapath.
4. Writes `sv32_core.v` with clock/reset, memory, halt, and debug ports, and
   `sv32_top.sv` as a compatibility wrapper.

Run `scripts/test-sv32.py` to build and simulate in one step.
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


def type_width(node):
    if "bit_count" in node:
        return int(node["bit_count"][0])
    if "array_size" in node:
        return int(node["array_size"][0]) * type_width(node["array_element"][0])
    if "tuple_elements" in node:
        return sum(type_width(element) for element in node["tuple_elements"])
    raise ValueError(f"cannot size type node: {node}")


def tuple_fields(node):
    """Return [(field_type, lsb)] for a tuple, field 0 at the high end.

    XLS packs the first tuple element into the most significant bits, so the
    last field starts at bit zero.
    """
    high = type_width(node)
    fields = []
    for element in node["tuple_elements"]:
        width = type_width(element)
        high -= width
        fields.append((element, high))
    return fields


def array_element_offset(node, index):
    return index * type_width(node["array_element"][0])


def data_port(signature, name):
    for port in signature["data_ports"]:
        if port["name"][0] == name:
            return port
    raise KeyError(f"port {name!r} not present in module signature")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_directory(module):
    return ROOT / "build" / "sv32"


def run_tool(tool, arguments, destination):
    print(f"Running {tool}", flush=True)
    try:
        with destination.open("w") as stream:
            subprocess.run([str(ROOT / "bin/xls"), tool, *map(str, arguments)],
                           cwd=ROOT, stdout=stream, check=True, timeout=1800)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"{tool} timed out")


def interface_ports(signature):
    """Share the public port declarations between the core and its alias."""
    state_type = data_port(signature, "state")["type"][0]
    (regs_type, _), (pc_type, _) = tuple_fields(state_type)
    out_type = data_port(signature, "out")["type"][0]
    (_, _), (dmem_type, _), (_, _) = tuple_fields(out_type)
    (addr_type, _), (wdata_type, _), (wstrb_type, _) = tuple_fields(dmem_type)
    return f'''    input wire clk,
    input wire rst_n,
    output wire [{type_width(addr_type) - 1}:0] imem_addr,
    input wire [{type_width(addr_type) - 1}:0] imem_rdata,
    output wire [{type_width(addr_type) - 1}:0] dmem_addr,
    output wire [{type_width(wdata_type) - 1}:0] dmem_wdata,
    output wire [{type_width(wstrb_type) - 1}:0] dmem_wstrb,
    input wire [{type_width(wdata_type) - 1}:0] dmem_rdata,
    output wire halted,
    output wire [{type_width(pc_type) - 1}:0] debug_pc,
    output wire [{type_width(regs_type) - 1}:0] debug_regs'''


def core(signature, module):
    state_port = data_port(signature, "state")
    out_port = data_port(signature, "out")
    state_width = int(state_port["width"][0])
    out_width = int(out_port["width"][0])
    state_type = state_port["type"][0]
    out_type = out_port["type"][0]

    (regs_type, regs_offset), (pc_type, pc_offset) = tuple_fields(state_type)
    regs_width = type_width(regs_type)
    reg_width = type_width(regs_type["array_element"][0])
    reg_count = int(regs_type["array_size"][0])
    pc_width = type_width(pc_type)

    (next_state_type, next_state_offset), (dmem_type, dmem_offset), (halt_type, halt_offset) = \
        tuple_fields(out_type)
    (addr_type, addr_base), (wdata_type, wdata_base), (wstrb_type, wstrb_base) = \
        tuple_fields(dmem_type)
    addr_offset = dmem_offset + addr_base
    wdata_offset = dmem_offset + wdata_base
    wstrb_offset = dmem_offset + wstrb_base

    next_state_width = type_width(next_state_type)
    (next_regs_type, next_regs_base), (next_pc_type, next_pc_base) = tuple_fields(next_state_type)
    next_regs_offset = next_state_offset + next_regs_base
    next_pc_offset = next_state_offset + next_pc_base
    addr_width = type_width(addr_type)
    wdata_width = type_width(wdata_type)
    wstrb_width = type_width(wstrb_type)
    assert state_width == next_state_width
    assert regs_width == type_width(next_regs_type)
    assert pc_width == type_width(next_pc_type)

    return f'''// Generated by scripts/build-sv32.py. Do not edit.
// Clocked RV32I core. Packed XLS ports are internal to the datapath.
`default_nettype none
module {module} (
{interface_ports(signature)}
);
  reg [{pc_width - 1}:0] pc;
  reg [{reg_width - 1}:0] regs [0:{reg_count - 1}];
  wire [{pc_width - 1}:0] next_pc;
  wire [{reg_width - 1}:0] next_regs [0:{reg_count - 1}];
  wire [{state_width - 1}:0] packed_state;
  wire [{out_width - 1}:0] packed_result;

  {signature["module_name"][0]} datapath (
      .state(packed_state),
      .imem_rdata(imem_rdata),
      .dmem_rdata(dmem_rdata),
      .out(packed_result)
  );

  // Only this connection layer depends on the XLS tuple/array packing.
  assign packed_state[{pc_offset} +: {pc_width}] = pc;
  assign next_pc = packed_result[{next_pc_offset} +: {pc_width}];
  genvar i;
  generate
    for (i = 0; i < {reg_count}; i = i + 1) begin : register_connections
      assign packed_state[{regs_offset} + i*{reg_width} +: {reg_width}] = regs[i];
      assign next_regs[i] = packed_result[{next_regs_offset} + i*{reg_width} +: {reg_width}];
      assign debug_regs[i*{reg_width} +: {reg_width}] = regs[i];
    end
  endgenerate

  assign imem_addr = pc;
  assign dmem_addr = packed_result[{addr_offset} +: {addr_width}];
  assign dmem_wdata = packed_result[{wdata_offset} +: {wdata_width}];
  assign dmem_wstrb = rst_n ? packed_result[{wstrb_offset} +: {wstrb_width}] : {wstrb_width}'b0;
  assign halted = packed_result[{halt_offset}];
  assign debug_pc = pc;

  integer r;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      pc <= {pc_width}'b0;
      for (r = 0; r < {reg_count}; r = r + 1) regs[r] <= {reg_width}'b0;
    end else if (!halted) begin
      pc <= next_pc;
      for (r = 0; r < {reg_count}; r = r + 1) regs[r] <= next_regs[r];
    end
  end
endmodule
`default_nettype wire
'''


def wrapper(signature, module):
    """Keep the existing sv32_top port names as a thin alias for the core."""
    return f'''// Generated by scripts/build-sv32.py. Do not edit.
// Compatibility wrapper; new integrations can instantiate {module} directly.
`default_nettype none
module sv32_top (
{interface_ports(signature)}
);
  {module} core (
      .clk(clk), .rst_n(rst_n),
      .imem_addr(imem_addr), .imem_rdata(imem_rdata),
      .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata),
      .dmem_wstrb(dmem_wstrb), .dmem_rdata(dmem_rdata),
      .halted(halted), .debug_pc(debug_pc), .debug_regs(debug_regs)
  );
endmodule
`default_nettype wire
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        help="build directory (default build/sv32)")
    parser.add_argument("--module-name", default="sv32_core")
    args = parser.parse_args()
    if args.module_name == "sv32_top":
        parser.error("--module-name cannot be sv32_top (reserved for the compatibility wrapper)")

    output = (args.output_dir or build_directory(args.module_name)).resolve()
    output.mkdir(parents=True, exist_ok=True)

    run_tool("ir_converter_main",
             ["--dslx_path=" + str(ROOT / "src" / "sv32"),
              "--top=step", ROOT / "src" / "sv32" / "sv32.x"],
             output / "sv32.ir")
    run_tool("opt_main", [output / "sv32.ir"], output / "sv32.opt.ir")
    signature_path = output / "sv32_core.sig.textproto"
    core_path = output / "sv32_core.v"
    datapath_module = args.module_name + "_datapath"
    run_tool("codegen_main",
             ["--generator=combinational", f"--module_name={datapath_module}",
              "--use_system_verilog=false",
              f"--output_signature_path={signature_path}", output / "sv32.opt.ir"],
             core_path)

    signature = parse_signature(signature_path.read_text())
    datapath = core_path.read_text()
    core_path.write_text(core(signature, args.module_name) +
                         "\n// Internal combinational XLS implementation of step.\n"
                         "// Bundled with the public core for standalone compilation.\n"
                         "/* verilator lint_off DECLFILENAME */\n" + datapath +
                         "\n/* verilator lint_on DECLFILENAME */\n")
    (output / "sv32_top.sv").write_text(wrapper(signature, args.module_name))
    (output / "config.json").write_text(json.dumps({
        "module": args.module_name,
        "isa": "RV32I",
        "generator": "combinational",
        "interface": "clocked_harvard",
        "core_module": args.module_name,
        "datapath_module": datapath_module,
        "state_width": int(data_port(signature, "state")["width"][0]),
        "output_width": int(data_port(signature, "out")["width"][0]),
    }, indent=2) + "\n")
    print(f"Generated {core_path} and {output / 'sv32_top.sv'}")


if __name__ == "__main__":
    main()
