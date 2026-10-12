`timescale 1ns/1ps
module tb;
  parameter IMEM_INIT_FILE = "blinky.hex";
  parameter integer DELAY_ITERATIONS = 8;
  localparam integer INTERVAL = 2 * DELAY_ITERATIONS + 8;
  reg clk = 0;
  always #5 clk = ~clk; // 100 MHz
  reg rst_n = 0;
  wire led, halted;
  wire [31:0] debug_pc;
`ifdef GATE_SIM
  sv32_soc dut (
`else
  sv32_soc #(.IMEM_INIT_FILE(IMEM_INIT_FILE)) dut (
`endif
      .clk(clk), .rst_n(rst_n), .led(led), .halted(halted), .debug_pc(debug_pc)
  );
  integer epoch, cycles, toggles;
  reg previous_led;
  initial begin
    $dumpfile("blinky.vcd");
    $dumpvars(0, clk, rst_n, led, halted, debug_pc);
    for (epoch = 0; epoch < 2; epoch = epoch + 1) begin
      // Restart after RAM has been used, proving firmware reinitializes it.
      rst_n = 0;
      repeat (3) begin
        @(negedge clk);
        if (led !== 0 || debug_pc !== 0) $fatal(1, "reset did not clear LED/PC");
      end
      rst_n = 1;
      previous_led = 0;
      cycles = 0;
      toggles = 0;
      while (toggles < 6 && cycles < 8 + 6 * INTERVAL) begin
        @(negedge clk);
        cycles = cycles + 1;
        if (halted !== 0) $fatal(1, "unexpected halt at pc=%08x", debug_pc);
        if (led !== 0 && led !== 1) $fatal(1, "unknown LED value");
        if (led != previous_led) begin
          if (cycles != 8 + toggles * INTERVAL)
            $fatal(1, "LED timing: cycle=%0d expected=%0d", cycles, 8 + toggles * INTERVAL);
          if (debug_pc !== 32'd32) $fatal(1, "LED changed outside the MMIO store");
          $display("LED epoch=%0d toggle=%0d value=%0d cycle=%0d", epoch, toggles, led, cycles);
          previous_led = led;
          toggles = toggles + 1;
        end
      end
      if (toggles != 6) $fatal(1, "LED did not blink six times");
    end
    $display("PASS: SoC blinky, exact toggle timing, and reset/restart");
    $finish;
  end
endmodule
