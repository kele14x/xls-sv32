// Asynchronous reads and rising-edge writes with little-endian byte enables.
// RAM is preserved on reset; firmware initializes the words it uses.
`default_nettype none
module sv32_dmem #(
    parameter integer WORDS = 256,
    parameter INIT_FILE = ""
) (
    input wire clk,
    input wire rst_n,
    input wire [31:0] addr,
    input wire [31:0] wdata,
    input wire [3:0] wstrb,
    output wire [31:0] rdata
);
  localparam integer ADDR_WIDTH = (WORDS > 1) ? $clog2(WORDS) : 1;
  reg [31:0] mem [0:WORDS-1];
  wire [ADDR_WIDTH-1:0] index = addr[ADDR_WIDTH+1:2];
  wire in_range = (addr >> 2) < WORDS;
  initial begin
    if (INIT_FILE != "") $readmemh(INIT_FILE, mem);
  end
  assign rdata = in_range ? mem[index] : 32'b0;
  always @(posedge clk) begin
    if (rst_n && in_range) begin
      if (wstrb[0]) mem[index][7:0] <= wdata[7:0];
      if (wstrb[1]) mem[index][15:8] <= wdata[15:8];
      if (wstrb[2]) mem[index][23:16] <= wdata[23:16];
      if (wstrb[3]) mem[index][31:24] <= wdata[31:24];
    end
  end
endmodule
`default_nettype wire
