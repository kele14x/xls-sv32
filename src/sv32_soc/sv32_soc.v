// Small Harvard SoC: SV32, boot ROM, byte-write RAM, and one LED register.
`default_nettype none
module sv32_soc #(
    parameter integer IMEM_WORDS = 256,
    parameter integer DMEM_WORDS = 256,
    parameter IMEM_INIT_FILE = "build/sv32_soc/blinky.hex",
    parameter DMEM_INIT_FILE = ""
) (
    input wire clk,
    input wire rst_n,
    output reg led,
    output wire halted,
    output wire [31:0] debug_pc
);
  localparam [31:0] RAM_BASE = 32'h0000_1000;
  localparam [31:0] LED_ADDR = 32'h1000_0000;
  wire [31:0] imem_addr, imem_rdata;
  wire [31:0] dmem_addr, dmem_wdata, dmem_rdata, ram_rdata;
  wire [3:0] dmem_wstrb;
  wire [31:0] ram_addr = dmem_addr - RAM_BASE;
  wire ram_selected = (dmem_addr >= RAM_BASE) && ((ram_addr >> 2) < DMEM_WORDS);
  wire led_selected = dmem_addr == LED_ADDR;

  sv32_core cpu (
      .clk(clk), .rst_n(rst_n),
      .imem_addr(imem_addr), .imem_rdata(imem_rdata),
      .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata),
      .dmem_wstrb(dmem_wstrb), .dmem_rdata(dmem_rdata),
      .halted(halted), .debug_pc(debug_pc), .debug_regs()
  );
  sv32_imem #(.WORDS(IMEM_WORDS), .INIT_FILE(IMEM_INIT_FILE)) imem (
      .addr(imem_addr), .rdata(imem_rdata)
  );
  sv32_dmem #(.WORDS(DMEM_WORDS), .INIT_FILE(DMEM_INIT_FILE)) dmem (
      .clk(clk), .rst_n(rst_n), .addr(ram_addr), .wdata(dmem_wdata),
      .wstrb(dmem_wstrb & {4{ram_selected}}), .rdata(ram_rdata)
  );
  assign dmem_rdata = led_selected ? {31'b0, led} :
                      ram_selected ? ram_rdata : 32'b0;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) led <= 1'b0;
    else if (led_selected && dmem_wstrb[0]) led <= dmem_wdata[0];
  end
endmodule
`default_nettype wire
