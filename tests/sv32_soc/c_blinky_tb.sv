`timescale 1ns/1ps
module tb;
  parameter IMEM_INIT_FILE = "blinky.hex";
  parameter integer DELAY_ITERATIONS = 8;
  parameter [31:0] BSS_START = 32'h1000;
  parameter [31:0] BSS_END = 32'h1004;
  parameter [31:0] COUNTER_ADDRESS = 32'h1000;
  localparam integer MAX_CYCLES = 200 + 20 * DELAY_ITERATIONS;
  reg clk = 0;
  always #5 clk = ~clk;
  reg rst_n = 0;
  wire led, halted;
  wire [31:0] debug_pc;
  sv32_soc #(.IMEM_INIT_FILE(IMEM_INIT_FILE)) dut (
      .clk(clk), .rst_n(rst_n), .led(led), .halted(halted), .debug_pc(debug_pc)
  );
  integer i, epoch, cycles, toggles, last_toggle, interval, first_toggle;
  integer expected_first = 0, expected_interval = 0;
  reg previous_led, saw_stack_write;
  wire [31:0] stack_pointer = dut.cpu.debug_regs[64 +: 32];

  // Detect bad startup/linker addresses rather than silently ignoring writes.
  always @(posedge clk) begin
    if (rst_n && dut.dmem_wstrb != 0 && dut.dmem_addr != 32'h10000000) begin
      if (dut.dmem_addr >= 32'h1300 && dut.dmem_addr < 32'h1400)
        saw_stack_write = 1;
      else if (dut.dmem_addr < BSS_START || dut.dmem_addr >= BSS_END)
        $fatal(1, "C firmware wrote outside BSS/stack: %08x", dut.dmem_addr);
    end
  end

  initial begin
    $dumpfile("blinky.vcd");
    $dumpvars(0, clk, rst_n, led, halted, debug_pc, stack_pointer);
    // Power-up RAM is unspecified. Startup must clear BSS before C reads it.
    for (i = 0; i < 256; i = i + 1) dut.dmem.mem[i] = 32'hdeadbeef;
    for (epoch = 0; epoch < 2; epoch = epoch + 1) begin
      rst_n = 0;
      saw_stack_write = 0;
      repeat (3) begin
        @(negedge clk);
        if (led !== 0 || debug_pc !== 0) $fatal(1, "reset did not clear LED/PC");
      end
      rst_n = 1;
      previous_led = 0;
      cycles = 0;
      toggles = 0;
      last_toggle = 0;
      interval = 0;
      first_toggle = 0;
      while (toggles < 6 && cycles < MAX_CYCLES) begin
        @(negedge clk);
        cycles = cycles + 1;
        if (halted !== 0) $fatal(1, "C firmware halted at pc=%08x", debug_pc);
        if (led !== 0 && led !== 1) $fatal(1, "unknown LED value");
        if (led != previous_led) begin
          if (dut.dmem.mem[(COUNTER_ADDRESS - 32'h1000) >> 2] !== toggles + 1)
            $fatal(1, "C counter was not initialized/incremented correctly");
          if (stack_pointer < 32'h1300 || stack_pointer > 32'h1400 || stack_pointer[3:0] != 0)
            $fatal(1, "C stack is outside RAM or not ABI aligned");
          if (toggles == 0) first_toggle = cycles;
          else if (toggles == 1) interval = cycles - last_toggle;
          else if (cycles - last_toggle != interval) $fatal(1, "unstable C blink interval");
          $display("C LED epoch=%0d toggle=%0d value=%0d cycle=%0d", epoch, toggles, led, cycles);
          last_toggle = cycles;
          previous_led = led;
          toggles = toggles + 1;
        end
      end
      if (toggles != 6 || !saw_stack_write) $fatal(1, "C blink/call-stack verification failed");
      if (interval < 2 * DELAY_ITERATIONS || interval > 2 * DELAY_ITERATIONS + 40)
        $fatal(1, "C delay was removed or has unexpected instruction overhead");
      if (epoch == 0) begin
        expected_first = first_toggle;
        expected_interval = interval;
      end else if (first_toggle != expected_first || interval != expected_interval)
        $fatal(1, "C startup/blink timing changed after warm reset");
    end
    $display("PASS: C firmware BSS startup, call stack, blink cadence, and warm reset (interval=%0d)",
             expected_interval);
    $finish;
  end
endmodule
