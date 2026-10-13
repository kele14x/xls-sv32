// Stateful SV32 core. XLS owns all architectural registers and next-state logic.
// The build maps these channels to unbuffered single-value XLS IR ports and
// schedules exactly one cycle per activation, with no input/output registers.
import sv32_execute;

pub proc sv32_core {
    imem_rdata: chan<u32> in;
    dmem_rdata: chan<u32> in;
    reset_n: chan<bool> in;
    imem_addr: chan<u32> out;
    dmem_addr: chan<u32> out;
    dmem_wdata: chan<u32> out;
    dmem_wstrb: chan<u4> out;
    halted: chan<bool> out;
    debug_pc: chan<u32> out;
    debug_regs: chan<u32[32]> out;

    config(imem_rdata: chan<u32> in, dmem_rdata: chan<u32> in,
           reset_n: chan<bool> in, imem_addr: chan<u32> out,
           dmem_addr: chan<u32> out, dmem_wdata: chan<u32> out,
           dmem_wstrb: chan<u4> out, halted: chan<bool> out,
           debug_pc: chan<u32> out, debug_regs: chan<u32[32]> out) {
        (imem_rdata, dmem_rdata, reset_n, imem_addr, dmem_addr,
         dmem_wdata, dmem_wstrb, halted, debug_pc, debug_regs)
    }

    // Codegen uses this value for the asynchronous active-low rst_n reset.
    init { sv32_execute::State { regs: u32[32]:[u32:0, ...], pc: u32:0 } }

    next(state: sv32_execute::State) {
        let (ti, instruction) = recv(join(), imem_rdata);
        let (_td, read_data) = recv(join(), dmem_rdata);
        let (tr, reset_released) = recv(join(), reset_n);
        let result = sv32_execute::step(state, instruction, read_data);
        send(join(), imem_addr, state.pc);
        send(join(), debug_pc, state.pc);
        send(join(), debug_regs, state.regs);
        send(ti, dmem_addr, result.dmem.addr);
        send(ti, dmem_wdata, result.dmem.wdata);
        // The generated register reset is not visible to DSLX expressions.
        // Connect reset_n and rst_n to the same signal at the Verilog boundary.
        send(join(ti, tr), dmem_wstrb,
             if reset_released { result.dmem.wstrb } else { u4:0 });
        send(ti, halted, result.halt);
        if result.halt { state } else { result.state }
    }
}
