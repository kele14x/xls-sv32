`timescale 1ns/1ps
// Functional clock/reset model for board-wrapper tests. Quartus validates
// the real vendor PLL/reset IP and its timing separately.
module sv32_clocking (
    input wire ref_clk_clk,
    input wire pll_reset_reset,
    output reg soc_clk_clk = 0,
    output reg locked_export = 0,
    output reg config_reset_ninit_done = 1
);
  integer count = 0;
  initial #60 config_reset_ninit_done = 0;
  // Keep clocks running during reset to stress architectural reset behavior.
  always #5 soc_clk_clk = ~soc_clk_clk;
  always @(posedge ref_clk_clk or posedge pll_reset_reset) begin
    if (pll_reset_reset) begin count <= 0; locked_export <= 0; end
    else if (count == 3) locked_export <= 1;
    else count <= count + 1;
  end
endmodule

module tb;
  parameter IMEM_INIT_FILE = "blinky.hex";
  parameter integer DELAY_ITERATIONS = 8;
  parameter integer C_FIRMWARE = 0;
  localparam integer INTERVAL = 2 * DELAY_ITERATIONS + 8;
  localparam integer MAX_CYCLES = C_FIRMWARE ? 200 + 12 * DELAY_ITERATIONS : 8 + 4 * INTERVAL;
  reg clk50 = 0;
  always #10 clk50 = ~clk50;
  reg key_n = 0;
  wire led_n;
  sv32_de25_nano #(.IMEM_INIT_FILE(IMEM_INIT_FILE)) dut (
      .CLOCK1_50(clk50), .KEY0_N(key_n), .LED0_N(led_n)
  );
  integer epoch, cycles, toggles;
  reg previous_led;
  initial begin
    for (epoch = 0; epoch < 2; epoch = epoch + 1) begin
      key_n = 0;
      repeat (6) begin
        @(negedge clk50);
        if (led_n !== 1) $fatal(1, "active-low board LED must be off during reset");
      end
      key_n = 1;
      wait (dut.reset_sync === 2'b11);
      @(negedge dut.clk_100);
      previous_led = 1;
      cycles = 0;
      toggles = 0;
      while (toggles < 4 && cycles < MAX_CYCLES) begin
        @(negedge dut.clk_100);
        cycles = cycles + 1;
        if (dut.soc.halted !== 0) $fatal(1, "board firmware halted");
        if (led_n !== 0 && led_n !== 1) $fatal(1, "board LED unknown");
        if (led_n != previous_led) begin
          if (!C_FIRMWARE && cycles != 8 + toggles * INTERVAL)
            $fatal(1, "board LED timing/polarity mismatch");
          previous_led = led_n;
          toggles = toggles + 1;
        end
      end
      if (toggles != 4) $fatal(1, "board did not blink");
    end
    $display("PASS: DE25-NANO reset and LED polarity (behavioral clocking model)");
    $finish;
  end
  initial begin
    #(2000 + 20 * MAX_CYCLES);
    $fatal(1, "board reset/PLL-lock timeout");
  end
endmodule
