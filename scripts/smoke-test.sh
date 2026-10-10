#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
tool_dir="$project_dir/tools/xls"
stdlib_dir="$tool_dir/xls/dslx/stdlib"
output_dir="$project_dir/build/riscv_core"
mkdir -p "$output_dir"
exec > >(tee "$output_dir/smoke-test.log") 2>&1

echo "Running XLS on $(hostname) ($(uname -m))"
for tool in interpreter_main ir_converter_main opt_main codegen_main; do
    "$tool_dir/$tool" --version
done

echo "Running DSLX unit tests and comparing function results with LLVM JIT"
"$tool_dir/interpreter_main" --dslx_stdlib_path="$stdlib_dir" \
    --dslx_path="$project_dir/src/riscv_core" \
    --compare=jit --lower_to_ir=true --convert_tests=true --seed=42 \
    tests/riscv_core/riscv_core_test.x

echo "Running the same tests using the IR interpreter"
"$tool_dir/interpreter_main" --dslx_stdlib_path="$stdlib_dir" \
    --dslx_path="$project_dir/src/riscv_core" \
    --evaluator=ir-interpreter --lower_to_ir=true --convert_tests=true \
    --run_quickcheck_when_interpreting=true --seed=42 \
    tests/riscv_core/riscv_core_test.x

echo "Generating combinational RV32I RTL and the clocked wrapper"
python3 scripts/build-riscv.py
test -s "$output_dir/riscv_core.v"
test -s "$output_dir/riscv_top.sv"

echo "PASS: DSLX tests, JIT comparison, and Verilog generation"
echo "Outputs: $output_dir"
