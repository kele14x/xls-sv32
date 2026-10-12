// DE25-NANO: 50 MHz oscillator -> 100 MHz CPU, KEY0 reset, active-low LED0.
`default_nettype none
module sv32_de25_nano #(
    parameter IMEM_INIT_FILE = "build/sv32_soc/blinky.hex"
) (
    input wire CLOCK1_50,
    input wire KEY0_N,
    output wire LED0_N
);
  wire clk_100, pll_locked;
  wire ninit_done;
  // Vendor-generated 50 -> 100 MHz PLL and Agilex 5 configuration reset release.
  sv32_clocking clock_gen (
      .ref_clk_clk(CLOCK1_50), .pll_reset_reset(!KEY0_N || ninit_done),
      .soc_clk_clk(clk_100), .locked_export(pll_locked),
      .config_reset_ninit_done(ninit_done)
  );
  wire async_rst_n = KEY0_N && !ninit_done && pll_locked;
  (* async_reg = "true" *) reg [1:0] reset_sync;
  always @(posedge clk_100 or negedge async_rst_n) begin
    if (!async_rst_n) reset_sync <= 2'b0;
    else reset_sync <= {reset_sync[0], 1'b1};
  end
  wire led;
  sv32_soc #(.IMEM_INIT_FILE(IMEM_INIT_FILE)) soc (
      .clk(clk_100), .rst_n(reset_sync[1]), .led(led), .halted(), .debug_pc()
  );
  assign LED0_N = !led;
endmodule
`default_nettype wire
