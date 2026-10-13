// RV32I single-cycle datapath, modeled as a pure state-transition function.
//
//   step(state, imem_rdata, dmem_rdata) -> (state', dmem_req, halt)
//
// sv32_core.x calls this function from a stateful proc. XLS generates both
// the instruction logic and the PC/register-file storage. Keeping step pure
// also lets the unit tests exercise instruction semantics directly.
//
// Supported: RV32I base integer instructions (LUI, AUIPC, JAL, JALR,
// branches, loads, stores, OP-IMM, OP, FENCE, ECALL/EBREAK). CSRs are
// ignored; FENCE is a no-op. No M/A/C/F/D extensions.
//
// The core is Harvard-style: instruction fetch uses state.pc, data memory
// uses the request emitted here. Both memories are combinational reads.
// Loads therefore complete in the same step: dmem_rdata must correspond to
// the emitted dmem.addr. Stores assert dmem.wstrb and update memory on the
// next clock edge in the generated core.

pub const XLEN: u32 = u32:32;

pub struct State {
    regs: u32[32],
    pc: u32,
}

pub struct DMemReq {
    addr: u32,
    wdata: u32,
    wstrb: u4,
}

pub struct StepResult {
    state: State,
    dmem: DMemReq,
    halt: bool,
}

fn no_req() -> DMemReq {
    DMemReq { addr: u32:0, wdata: u32:0, wstrb: u4:0 }
}

// ---------------------------------------------------------------------------
// Register file helpers
// ---------------------------------------------------------------------------

pub fn reg_read(regs: u32[32], index: u32) -> u32 {
    if index == u32:0 { u32:0 } else { regs[index] }
}

fn commit(regs: u32[32], next_pc: u32, write_enable: bool, dest: u32,
          value: u32, dmem: DMemReq, halt: bool) -> StepResult {
    let new_regs = if write_enable && dest != u32:0 {
        update(regs, dest, value)
    } else {
        regs
    };
    StepResult {
        state: State { regs: new_regs, pc: next_pc },
        dmem: dmem,
        halt: halt,
    }
}

// ---------------------------------------------------------------------------
// Instruction fields
// ---------------------------------------------------------------------------

fn opcode(instr: u32) -> u32 { instr[0:7] as u32 }
fn rd(instr: u32) -> u32 { instr[7:12] as u32 }
fn funct3(instr: u32) -> u32 { instr[12:15] as u32 }
fn rs1(instr: u32) -> u32 { instr[15:20] as u32 }
fn rs2(instr: u32) -> u32 { instr[20:25] as u32 }
fn funct7(instr: u32) -> u32 { instr[25:32] as u32 }

// Validate the supported encodings before any register or memory effects.
fn is_supported(instr: u32) -> bool {
    let op = opcode(instr);
    let f3 = funct3(instr);
    let f7 = funct7(instr);
    if op == u32:0x33 {
        f7 == u32:0 || (f7 == u32:0x20 && (f3 == u32:0 || f3 == u32:5))
    } else if op == u32:0x13 {
        if f3 == u32:1 { f7 == u32:0 }
        else if f3 == u32:5 { f7 == u32:0 || f7 == u32:0x20 }
        else { true }
    } else if op == u32:0x03 {
        f3 == u32:0 || f3 == u32:1 || f3 == u32:2 || f3 == u32:4 || f3 == u32:5
    } else if op == u32:0x23 {
        f3 <= u32:2
    } else if op == u32:0x63 {
        f3 == u32:0 || f3 == u32:1 || f3 >= u32:4
    } else if op == u32:0x67 || op == u32:0x0f {
        // FENCE's reserved operand/mode fields are intentionally ignored.
        f3 == u32:0
    } else if op == u32:0x73 {
        instr == u32:0x0000_0073 || instr == u32:0x0010_0073 ||
        f3 == u32:1 || f3 == u32:2 || f3 == u32:3 ||
        f3 == u32:5 || f3 == u32:6 || f3 == u32:7
    } else {
        op == u32:0x6f || op == u32:0x37 || op == u32:0x17
    }
}

// ---------------------------------------------------------------------------
// Immediates. DSLX slices are half-open [low:high); concatenation is high:low.
// ---------------------------------------------------------------------------

fn imm_i(instr: u32) -> u32 {
    (instr[20:32] as s12) as s32 as u32
}

fn imm_s(instr: u32) -> u32 {
    let raw: u12 = instr[25:32] ++ instr[7:12];
    (raw as s12) as s32 as u32
}

fn imm_b(instr: u32) -> u32 {
    let raw: u13 = instr[31:32] ++ instr[7:8] ++ instr[25:31] ++
        instr[8:12] ++ u1:0;
    (raw as s13) as s32 as u32
}

fn imm_u(instr: u32) -> u32 {
    (instr[12:32] as u32) << u32:12
}

fn imm_j(instr: u32) -> u32 {
    let raw: u21 = instr[31:32] ++ instr[12:20] ++ instr[20:21] ++
        instr[21:31] ++ u1:0;
    (raw as s21) as s32 as u32
}

// ---------------------------------------------------------------------------
// Execution units
// ---------------------------------------------------------------------------

fn load_signed(value: u32, width: u32) -> u32 {
    if width == u32:8 {
        (value as u8) as s8 as s32 as u32
    } else {
        (value as u16) as s16 as s32 as u32
    }
}

fn exec_load(regs: u32[32], pc: u32, dest: u32, addr: u32, rdata: u32,
             f3: u32) -> StepResult {
    let byte_offset: u32 = (addr & u32:3) * u32:8;
    let half_offset: u32 = (addr & u32:2) * u32:8;
    let value = if f3 == u32:2 {
        rdata
    } else if f3 == u32:0 {
        load_signed(rdata >> byte_offset, u32:8)
    } else if f3 == u32:4 {
        (rdata >> byte_offset) as u8 as u32
    } else if f3 == u32:1 {
        load_signed(rdata >> half_offset, u32:16)
    } else if f3 == u32:5 {
        (rdata >> half_offset) as u16 as u32
    } else {
        u32:0
    };
    let req = DMemReq {
        addr: addr & u32:0xffff_fffc,
        wdata: u32:0,
        wstrb: u4:0,
    };
    commit(regs, pc + u32:4, true, dest, value, req, false)
}

fn exec_store(regs: u32[32], pc: u32, addr: u32, src: u32, f3: u32) -> StepResult {
    let byte_offset: u32 = (addr & u32:3) * u32:8;
    let half_offset: u32 = (addr & u32:2) * u32:8;
    let half_strobe: u2 = (addr & u32:2) as u2;
    let (wdata, wstrb) = if f3 == u32:0 {
        (src << byte_offset, u4:1 << (addr & u32:3) as u2)
    } else if f3 == u32:1 {
        (src << half_offset, u4:3 << half_strobe)
    } else {
        (src, u4:15)
    };
    let req = DMemReq {
        addr: addr & u32:0xffff_fffc,
        wdata: wdata,
        wstrb: wstrb,
    };
    commit(regs, pc + u32:4, false, u32:0, u32:0, req, false)
}

fn branch_taken(f3: u32, a: u32, b: u32) -> bool {
    if f3 == u32:0 { a == b }
    else if f3 == u32:1 { a != b }
    else if f3 == u32:4 { (a as s32) < (b as s32) }
    else if f3 == u32:5 { (a as s32) >= (b as s32) }
    else if f3 == u32:6 { a < b }
    else if f3 == u32:7 { a >= b }
    else { false }
}

fn exec_branch(regs: u32[32], pc: u32, instr: u32, a: u32, b: u32,
               f3: u32) -> StepResult {
    let next_pc = if branch_taken(f3, a, b) { pc + imm_b(instr) } else { pc + u32:4 };
    commit(regs, next_pc, false, u32:0, u32:0, no_req(), false)
}

fn exec_op_imm(regs: u32[32], pc: u32, instr: u32, dest: u32, a: u32,
               f3: u32) -> StepResult {
    let imm = imm_i(instr);
    let shamt: u32 = instr[20:25] as u32;
    let value = if f3 == u32:0 { a + imm }
    else if f3 == u32:2 { if (a as s32) < (imm as s32) { u32:1 } else { u32:0 } }
    else if f3 == u32:3 { if a < imm { u32:1 } else { u32:0 } }
    else if f3 == u32:4 { a ^ imm }
    else if f3 == u32:6 { a | imm }
    else if f3 == u32:7 { a & imm }
    else if f3 == u32:1 { a << shamt }
    else if f3 == u32:5 {
        if funct7(instr) == u32:0x20 {
            ((a as s32) >> shamt) as u32
        } else {
            a >> shamt
        }
    }
    else { u32:0 };
    commit(regs, pc + u32:4, true, dest, value, no_req(), false)
}

fn exec_op(regs: u32[32], pc: u32, dest: u32, a: u32, b: u32, f3: u32,
           f7: u32) -> StepResult {
    let shamt = b[0:5];
    let value = if f7 == u32:0x20 {
        if f3 == u32:0 { a - b }
        else if f3 == u32:5 { ((a as s32) >> shamt) as u32 }
        else { u32:0 }
    } else {
        if f3 == u32:0 { a + b }
        else if f3 == u32:1 { a << shamt }
        else if f3 == u32:2 { if (a as s32) < (b as s32) { u32:1 } else { u32:0 } }
        else if f3 == u32:3 { if a < b { u32:1 } else { u32:0 } }
        else if f3 == u32:4 { a ^ b }
        else if f3 == u32:5 { a >> shamt }
        else if f3 == u32:6 { a | b }
        else { a & b }
    };
    commit(regs, pc + u32:4, true, dest, value, no_req(), false)
}

fn exec_system(regs: u32[32], pc: u32, instr: u32, f3: u32) -> StepResult {
    // ECALL (imm 0) and EBREAK (imm 1) halt the simulation. CSR
    // instructions are treated as NOPs in this base implementation.
    let imm = instr[20:32] as u32;
    let halt = f3 == u32:0 && (imm == u32:0 || imm == u32:1);
    commit(regs, if halt { pc } else { pc + u32:4 },
           false, u32:0, u32:0, no_req(), halt)
}

fn illegal(state: State) -> StepResult {
    StepResult {
        state: state,
        dmem: no_req(),
        halt: true,
    }
}

// ---------------------------------------------------------------------------
// Top-level step
// ---------------------------------------------------------------------------

pub fn step(state: State, imem_rdata: u32, dmem_rdata: u32) -> StepResult {
    let instr = imem_rdata;
    let op = opcode(instr);
    let dest = rd(instr);
    let f3 = funct3(instr);
    let a = reg_read(state.regs, rs1(instr));
    let b = reg_read(state.regs, rs2(instr));
    let regs = state.regs;
    let pc = state.pc;
    if !is_supported(instr) {
        illegal(state)
    } else if op == u32:0x33 {
        exec_op(regs, pc, dest, a, b, f3, funct7(instr))
    } else if op == u32:0x13 {
        exec_op_imm(regs, pc, instr, dest, a, f3)
    } else if op == u32:0x03 {
        exec_load(regs, pc, dest, a + imm_i(instr), dmem_rdata, f3)
    } else if op == u32:0x23 {
        exec_store(regs, pc, a + imm_s(instr), b, f3)
    } else if op == u32:0x63 {
        exec_branch(regs, pc, instr, a, b, f3)
    } else if op == u32:0x6f {
        commit(regs, pc + imm_j(instr), true, dest, pc + u32:4, no_req(), false)
    } else if op == u32:0x67 {
        commit(regs, (a + imm_i(instr)) & u32:0xffff_fffe, true, dest,
               pc + u32:4, no_req(), false)
    } else if op == u32:0x37 {
        commit(regs, pc + u32:4, true, dest, imm_u(instr), no_req(), false)
    } else if op == u32:0x17 {
        commit(regs, pc + u32:4, true, dest, pc + imm_u(instr), no_req(), false)
    } else if op == u32:0x73 {
        exec_system(regs, pc, instr, f3)
    } else if op == u32:0x0f {
        // FENCE is a no-op for this single-cycle, in-order core.
        commit(regs, pc + u32:4, false, u32:0, u32:0, no_req(), false)
    } else {
        illegal(state)
    }
}
