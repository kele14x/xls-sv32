`timescale 1ns/1ps
module tb;
  reg clk = 0;
  always #5 clk = ~clk;
  reg rst_n = 1;
  reg [31:0] addr = 0, wdata = 0;
  reg [3:0] wstrb = 0;
  wire [31:0] rdata, instruction;
  sv32_imem #(.WORDS(4), .INIT_FILE("memory.hex")) rom (.addr(addr), .rdata(instruction));
  sv32_dmem #(.WORDS(4)) ram (
      .clk(clk), .rst_n(rst_n), .addr(addr), .wdata(wdata), .wstrb(wstrb), .rdata(rdata)
  );
  task write_word(input [31:0] address, input [31:0] value, input [3:0] strobes);
    begin
      @(negedge clk);
      addr = address; wdata = value; wstrb = strobes;
      @(negedge clk);
      wstrb = 0;
      #1;
    end
  endtask
  task expect_word(input [31:0] expected);
    begin
      #1;
      if (rdata !== expected) $fatal(1, "RAM at %x: got %x expected %x", addr, rdata, expected);
    end
  endtask
  initial begin
    #1;
    if (instruction !== 32'h11223344) $fatal(1, "ROM initialization");
    write_word(0, 32'h11223344, 4'b1111);
    write_word(0, 32'habcd0000, 4'b1100); expect_word(32'habcd3344);
    write_word(0, 32'h00005678, 4'b0011); expect_word(32'habcd5678);
    write_word(0, 32'h000000aa, 4'b0001); expect_word(32'habcd56aa);
    write_word(0, 32'h0000bb00, 4'b0010); expect_word(32'habcdbbaa);
    write_word(0, 32'h00cc0000, 4'b0100); expect_word(32'habccbbaa);
    write_word(0, 32'hdd000000, 4'b1000); expect_word(32'hddccbbaa);
    write_word(12, 32'hcafebabe, 4'b1111); expect_word(32'hcafebabe);
    if (instruction !== 32'hcafebabe) $fatal(1, "last ROM word");
    write_word(16, 32'hffffffff, 4'b1111); expect_word(0);
    if (instruction !== 0) $fatal(1, "out-of-range ROM aliases valid data");
    addr = 0; expect_word(32'hddccbbaa);
    rst_n = 0;
    write_word(0, 32'hffffffff, 4'b1111); expect_word(32'hddccbbaa);
    rst_n = 1;
    addr = 32'h10000000; expect_word(0);
    if (instruction !== 0) $fatal(1, "high ROM address aliases valid data");
    $display("PASS: ROM initialization/bounds and RAM byte writes/reset/bounds");
    $finish;
  end
endmodule
