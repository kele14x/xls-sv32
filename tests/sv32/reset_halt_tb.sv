// Check sequential behavior independently of the instruction reference model.
`timescale 1ns/1ps
module tb;
  reg clk = 0;
  reg rst_n = 1;
  reg boot_store = 0;
  reg [31:0] imem_rdata;
  wire [31:0] imem_addr, dmem_addr, dmem_wdata, debug_pc;
  wire [3:0] dmem_wstrb;
  wire halted;
  wire [1023:0] debug_regs;
  integer writes = 0;
  reg [31:0] stored = 32'hdeadbeef;
  reg [1023:0] halted_regs;

  `CORE_MODULE dut (
      .clk(clk), .rst_n(rst_n),
`ifdef DIRECT_CORE
      .reset_n(rst_n),
`endif
      .imem_addr(imem_addr), .imem_rdata(imem_rdata),
      .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata),
      .dmem_wstrb(dmem_wstrb), .dmem_rdata(32'b0),
      .halted(halted), .debug_pc(debug_pc), .debug_regs(debug_regs)
  );

  always @* begin
    case (imem_addr)
      0: imem_rdata = boot_store ? 32'h00002023 : 32'h00500093; // sw x0,0(x0) / addi x1,x0,5
      4: imem_rdata = 32'h00708113; // addi x2,x1,7
      8: imem_rdata = 32'h00202023; // sw x2,0(x0)
      default: imem_rdata = 32'h00100073; // ebreak
    endcase
  end
  always @(posedge clk) begin
    if (|dmem_wstrb) begin
      if (dmem_wstrb !== 4'hf || dmem_addr !== 0)
        $fatal(1, "unexpected store request");
      writes = writes + 1;
      stored = dmem_wdata;
    end
  end

  task tick;
    begin
      #5 clk = 1;
      #5 clk = 0;
      #1;
    end
  endtask

  task reset_without_clock;
    begin
      // Both reset assertion and checks happen while the clock is stopped.
      rst_n = 0;
      boot_store = 1;
      #1;
      if (debug_pc !== 0 || imem_addr !== 0 || debug_regs !== 1024'b0)
        $fatal(1, "architectural state did not reset asynchronously");
      if (dmem_wstrb !== 0) $fatal(1, "store active during asynchronous reset");
      tick();
      if (dmem_wstrb !== 0) $fatal(1, "store active while reset held");
      boot_store = 0;
      rst_n = 1;
      #1;
    end
  endtask

  initial begin
    reset_without_clock();
    if (writes !== 0 || stored !== 32'hdeadbeef) $fatal(1, "reset wrote memory");
    tick();
    if (debug_pc !== 4 || debug_regs[32 +: 32] !== 5)
      $fatal(1, "first instruction has extra latency");
    // Reset nonzero state in the middle of execution, then restart.
    reset_without_clock();
    if (writes !== 0) $fatal(1, "mid-program reset wrote memory");
    tick();
    tick();
    if (debug_pc !== 8 || debug_regs[64 +: 32] !== 12)
      $fatal(1, "dependent instruction did not execute in the next cycle");
    tick();
    if (writes !== 1 || stored !== 12 || halted !== 1 || debug_pc !== 12)
      $fatal(1, "store/halt timing changed");
    halted_regs = debug_regs;
    repeat (4) begin
      tick();
      if (halted !== 1 || debug_pc !== 12 || debug_regs !== halted_regs ||
          dmem_wstrb !== 0 || writes !== 1)
        $fatal(1, "halt did not preserve state and suppress stores");
    end
    reset_without_clock();
    if (writes !== 1 || stored !== 12) $fatal(1, "halt reset changed memory");
    tick();
    if (halted !== 0 || debug_pc !== 4 || debug_regs[32 +: 32] !== 5)
      $fatal(1, "core did not restart after halt/reset");
    $display("PASS: asynchronous reset, store suppression, halt hold, and restart");
    $finish;
  end
endmodule
