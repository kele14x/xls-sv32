// Asynchronous instruction ROM for the single-cycle SV32 core.
`default_nettype none
module sv32_imem #(
    parameter integer WORDS = 256,
    parameter INIT_FILE = ""
) (
    input wire [31:0] addr,
    output wire [31:0] rdata
);
  localparam integer ADDR_WIDTH = (WORDS > 1) ? $clog2(WORDS) : 1;
  reg [31:0] mem [0:WORDS-1];
  wire [ADDR_WIDTH-1:0] index = addr[ADDR_WIDTH+1:2];
  wire in_range = (addr >> 2) < WORDS;
  integer i;
  initial begin
    // Unused words are illegal instructions, so runaway code halts.
    for (i = 0; i < WORDS; i = i + 1) mem[i] = 32'b0;
    if (INIT_FILE != "") $readmemh(INIT_FILE, mem);
  end
  assign rdata = in_range ? mem[index] : 32'b0;
endmodule
`default_nettype wire
