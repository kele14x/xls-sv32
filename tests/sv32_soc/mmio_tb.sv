`timescale 1ns/1ps
module tb;
  parameter IMEM_INIT_FILE = "mmio.hex";
  parameter [31:0] EXPECTED_PC = 0;
  reg clk = 0;
  always #5 clk = ~clk;
  reg rst_n = 0;
  wire led, halted;
  wire [31:0] debug_pc;
  sv32_soc #(.IMEM_INIT_FILE(IMEM_INIT_FILE)) dut (
      .clk(clk), .rst_n(rst_n), .led(led), .halted(halted), .debug_pc(debug_pc)
  );
  integer cycles;
  initial begin
    repeat (3) @(negedge clk);
    rst_n = 1;
    cycles = 0;
    while (!halted && cycles < 100) begin
      @(negedge clk);
      cycles = cycles + 1;
    end
    if (halted !== 1 || debug_pc !== EXPECTED_PC || led !== 1)
      $fatal(1, "MMIO probe failed: halted=%b pc=%x expected=%x led=%b", halted, debug_pc, EXPECTED_PC, led);
    $display("PASS: SoC RAM halfwords, LED byte enables/readback, and unmapped accesses");
    $finish;
  end
endmodule
