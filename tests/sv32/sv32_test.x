// Unit tests for the RV32I core's step function.
//
// Instructions are built with small encoding helpers so the tests read like
// assembly. Each test calls `step` directly, which is the same function XLS
// turns into hardware.

import sv32;

// ---------------------------------------------------------------------------
// Instruction encoding helpers
// ---------------------------------------------------------------------------

fn r_type(f7: u32, rs2: u32, rs1: u32, f3: u32, dest: u32) -> u32 {
    (f7 << u32:25) | (rs2 << u32:20) | (rs1 << u32:15) |
        (f3 << u32:12) | (dest << u32:7) | u32:0x33
}

fn i_type(imm: s32, rs1: u32, f3: u32, dest: u32, op: u32) -> u32 {
    (imm as u32 & u32:0xfff) << u32:20 |
        (rs1 << u32:15) | (f3 << u32:12) | (dest << u32:7) | op
}

fn s_type(imm: s32, rs2: u32, rs1: u32, f3: u32) -> u32 {
    let value = imm as u32;
    ((value >> u32:5) & u32:0x7f) << u32:25 |
        (rs2 << u32:20) | (rs1 << u32:15) | (f3 << u32:12) |
        (value & u32:0x1f) << u32:7 | u32:0x23
}

fn b_type(imm: s32, rs2: u32, rs1: u32, f3: u32) -> u32 {
    let value = imm as u32;
    ((value >> u32:12) & u32:1) << u32:31 |
        ((value >> u32:5) & u32:0x3f) << u32:25 |
        (rs2 << u32:20) | (rs1 << u32:15) | (f3 << u32:12) |
        ((value >> u32:1) & u32:0xf) << u32:8 |
        ((value >> u32:11) & u32:1) << u32:7 | u32:0x63
}

fn u_type(imm: s32, dest: u32, op: u32) -> u32 {
    ((imm as u32 >> u32:12) & u32:0xfffff) << u32:12 |
        (dest << u32:7) | op
}

fn j_type(imm: s32, dest: u32) -> u32 {
    let value = imm as u32;
    ((value >> u32:20) & u32:1) << u32:31 |
        ((value >> u32:1) & u32:0x3ff) << u32:21 |
        ((value >> u32:11) & u32:1) << u32:20 |
        ((value >> u32:12) & u32:0xff) << u32:12 |
        (dest << u32:7) | u32:0x6f
}

// ---------------------------------------------------------------------------
// State helpers
// ---------------------------------------------------------------------------

fn init() -> sv32::State {
    sv32::State { regs: zero!<u32[32]>(), pc: u32:0 }
}

fn set_reg(state: sv32::State, index: u32, value: u32) -> sv32::State {
    sv32::State { regs: update(state.regs, index, value), pc: state.pc }
}

fn set_pc(state: sv32::State, pc: u32) -> sv32::State {
    sv32::State { regs: state.regs, pc: pc }
}

fn reg(result: sv32::StepResult, index: u32) -> u32 {
    sv32::reg_read(result.state.regs, index)
}

// ---------------------------------------------------------------------------
// ALU and immediate tests
// ---------------------------------------------------------------------------

#[test]
fn addi_add_sub() {
    let s = init();
    let s = set_reg(s, u32:1, u32:5);
    let r = sv32::step(s, i_type(s32:3, u32:1, u32:0, u32:2, u32:0x13), u32:0);
    assert_eq(reg(r, u32:2), u32:8);
    let r = sv32::step(r.state,
        r_type(u32:0, u32:2, u32:1, u32:0, u32:3), u32:0);
    assert_eq(reg(r, u32:3), u32:13);
    let r = sv32::step(r.state,
        r_type(u32:0x20, u32:1, u32:3, u32:0, u32:4), u32:0);
    assert_eq(reg(r, u32:4), u32:8);
    assert_eq(r.state.pc, u32:12);
}

#[test]
fn sign_extends_negative_immediates() {
    let s = set_reg(init(), u32:1, u32:10);
    let r = sv32::step(s, i_type(s32:-1, u32:1, u32:0, u32:2, u32:0x13), u32:0);
    assert_eq(reg(r, u32:2), u32:9);
}

#[test]
fn logic_and_shifts() {
    let s = set_reg(init(), u32:1, u32:0xf0);
    let r = sv32::step(s, i_type(s32:15, u32:1, u32:7, u32:2, u32:0x13), u32:0);
    assert_eq(reg(r, u32:2), u32:0);
    let r = sv32::step(r.state, i_type(s32:15, u32:1, u32:6, u32:3, u32:0x13), u32:0);
    assert_eq(reg(r, u32:3), u32:255);
    let r = sv32::step(r.state, i_type(s32:4, u32:1, u32:1, u32:4, u32:0x13), u32:0);
    assert_eq(reg(r, u32:4), u32:0xf00);
    let r = sv32::step(r.state, i_type(s32:4, u32:1, u32:5, u32:5, u32:0x13), u32:0);
    assert_eq(reg(r, u32:5), u32:0xf);
}

#[test]
fn arithmetic_shift_right_keeps_sign() {
    let s = set_reg(init(), u32:1, u32:0x8000_0000);
    let instr = i_type(s32:0x401, u32:1, u32:5, u32:2, u32:0x13);
    let r = sv32::step(s, instr, u32:0);
    assert_eq(reg(r, u32:2), u32:0xc000_0000);
}

#[test]
fn set_less_than_signed_and_unsigned() {
    let s = init();
    let s = set_reg(s, u32:1, u32:1);
    let s = set_reg(s, u32:2, u32:0xffff_ffff);
    let r = sv32::step(s, r_type(u32:0, u32:2, u32:1, u32:2, u32:3), u32:0);
    assert_eq(reg(r, u32:3), u32:0);
    let r = sv32::step(r.state, r_type(u32:0, u32:2, u32:1, u32:3, u32:4), u32:0);
    assert_eq(reg(r, u32:4), u32:1);
}

#[test]
fn lui_and_auipc() {
    let s = set_pc(init(), u32:0x1000);
    let r = sv32::step(s, u_type(s32:0x1234_5000, u32:1, u32:0x37), u32:0);
    assert_eq(reg(r, u32:1), u32:0x1234_5000);
    let r = sv32::step(r.state, u_type(s32:0x0000_2000, u32:2, u32:0x17), u32:0);
    // AUIPC adds the immediate to the current PC, which is 0x1004 after LUI.
    assert_eq(reg(r, u32:2), u32:0x3004);
}

// ---------------------------------------------------------------------------
// Control transfer tests
// ---------------------------------------------------------------------------

#[test]
fn branches_use_signed_and_unsigned_comparisons() {
    let s = init();
    let s = set_reg(s, u32:1, u32:0xffff_ffff);

    let taken = sv32::step(s, b_type(s32:8, u32:0, u32:1, u32:1), u32:0);
    assert_eq(taken.state.pc, u32:8);

    // BGE x1, x0 is false for x1 = -1, so the branch is not taken.
    let not_taken = sv32::step(s, b_type(s32:8, u32:0, u32:1, u32:5), u32:0);
    assert_eq(not_taken.state.pc, u32:4);
}

#[test]
fn jal_links_and_jumps() {
    let s = set_pc(init(), u32:0x2000);
    let r = sv32::step(s, j_type(s32:16, u32:1), u32:0);
    assert_eq(reg(r, u32:1), u32:0x2004);
    assert_eq(r.state.pc, u32:0x2010);
}

#[test]
fn jalr_clears_low_bit_and_links() {
    let s = set_pc(set_reg(init(), u32:1, u32:0x3001), u32:0x4000);
    let r = sv32::step(s, i_type(s32:0, u32:1, u32:0, u32:2, u32:0x67), u32:0);
    assert_eq(reg(r, u32:2), u32:0x4004);
    assert_eq(r.state.pc, u32:0x3000);
}

// ---------------------------------------------------------------------------
// Memory tests
// ---------------------------------------------------------------------------

#[test]
fn word_load_returns_memory_data() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let r = sv32::step(s, i_type(s32:12, u32:1, u32:2, u32:2, u32:0x03),
        u32:0xdead_beef);
    assert_eq(reg(r, u32:2), u32:0xdead_beef);
    assert_eq(r.dmem.addr, u32:0x100c);
    assert_eq(r.dmem.wstrb, u4:0);
}

#[test]
fn byte_load_sign_extends() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let r = sv32::step(s, i_type(s32:1, u32:1, u32:0, u32:2, u32:0x03),
        u32:0x0000_8000);
    assert_eq(reg(r, u32:2), u32:0xffff_ff80);
    let r = sv32::step(s, i_type(s32:1, u32:1, u32:4, u32:3, u32:0x03),
        u32:0x0000_8000);
    assert_eq(reg(r, u32:3), u32:0x80);
}

#[test]
fn halfword_load_at_offset_two() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let r = sv32::step(s, i_type(s32:2, u32:1, u32:5, u32:2, u32:0x03),
        u32:0xabcd_1234);
    assert_eq(reg(r, u32:2), u32:0xabcd);
}

#[test]
fn word_store_emits_full_strobe() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let s = set_reg(s, u32:2, u32:0xcafe_babe);
    let r = sv32::step(s, s_type(s32:4, u32:2, u32:1, u32:2), u32:0);
    assert_eq(r.dmem.addr, u32:0x1004);
    assert_eq(r.dmem.wdata, u32:0xcafe_babe);
    assert_eq(r.dmem.wstrb, u4:15);
    assert_eq(reg(r, u32:0), u32:0);
}

#[test]
fn byte_store_shifts_into_lane() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let s = set_reg(s, u32:2, u32:0x0000_00aa);
    let r = sv32::step(s, s_type(s32:1, u32:2, u32:1, u32:0), u32:0);
    assert_eq(r.dmem.wdata, u32:0x0000_aa00);
    assert_eq(r.dmem.wstrb, u4:2);
}

// ---------------------------------------------------------------------------
// Architectural invariants
// ---------------------------------------------------------------------------

#[test]
fn x0_is_hardwired_zero() {
    let r = sv32::step(init(), i_type(s32:5, u32:0, u32:0, u32:0, u32:0x13),
        u32:0);
    assert_eq(reg(r, u32:0), u32:0);
}

#[test]
fn ecall_halts_and_ebreak_halts() {
    let r = sv32::step(init(), u32:0x0000_0073, u32:0);
    assert_eq(r.halt, true);
    let r = sv32::step(init(), u32:0x0010_0073, u32:0);
    assert_eq(r.halt, true);
}

#[test]
fn fence_is_a_nop() {
    let s = set_pc(init(), u32:0x40);
    let r = sv32::step(s, u32:0x0000_000f, u32:0);
    assert_eq(r.state.pc, u32:0x44);
    assert_eq(r.halt, false);
}

#[test]
fn register_shifts_use_only_five_bits() {
    let counts = u32[6]:[0, 31, 32, 33, 0xffff_ffe1, 0xffff_ffff];
    let left = u32[6]:[0x8000_0001, 0x8000_0000, 0x8000_0001, 2, 2, 0x8000_0000];
    let right = u32[6]:[0x8000_0001, 1, 0x8000_0001, 0x4000_0000, 0x4000_0000, 1];
    let signed = u32[6]:[0x8000_0001, 0xffff_ffff, 0x8000_0001,
                         0xc000_0000, 0xc000_0000, 0xffff_ffff];
    for (i, ()): (u32, ()) in u32:0..u32:6 {
        let s = set_reg(set_reg(init(), u32:1, u32:0x8000_0001), u32:2, counts[i]);
        let l = sv32::step(s, r_type(u32:0, u32:2, u32:1, u32:1, u32:3), u32:0);
        let r = sv32::step(s, r_type(u32:0, u32:2, u32:1, u32:5, u32:3), u32:0);
        let a = sv32::step(s, r_type(u32:0x20, u32:2, u32:1, u32:5, u32:3), u32:0);
        assert_eq(reg(l, u32:3), left[i]);
        assert_eq(reg(r, u32:3), right[i]);
        assert_eq(reg(a, u32:3), signed[i]);
        assert_eq(l.halt || r.halt || a.halt, false);
    }(())
}

#[test]
fn halfword_stores_select_both_aligned_lanes() {
    let s = set_reg(set_reg(init(), u32:1, u32:0x1000), u32:2, u32:0xabcd);
    let low = sv32::step(s, s_type(s32:0, u32:2, u32:1, u32:1), u32:0);
    let high = sv32::step(s, s_type(s32:2, u32:2, u32:1, u32:1), u32:0);
    assert_eq(low.dmem.addr, u32:0x1000);
    assert_eq(high.dmem.addr, u32:0x1000);
    assert_eq(low.dmem.wstrb, u4:0b0011);
    assert_eq(high.dmem.wstrb, u4:0b1100);
    assert_eq(low.dmem.wdata, u32:0xabcd);
    assert_eq(high.dmem.wdata, u32:0xabcd_0000);
}

#[test]
fn unsupported_encodings_halt_without_effects() {
    let s = set_pc(set_reg(set_reg(init(), u32:1, u32:3),
                          u32:2, u32:7), u32:0x40);
    let instructions = u32[25]:[
        0x0220_81b3, // MUL (M extension)
        0x4020_91b3, // Unsupported OP funct7/funct3 combination
        0xfe20_81b3, // Unsupported OP funct7
        0x0200_9193, // Invalid SLLI upper immediate bits
        0x4000_9193, // Invalid SLLI with SRAI's funct7
        0x0200_d193, // Invalid SRLI upper immediate bits
        0x8010_d193, // Invalid shift from the original demo
        0x0000_3183, // Unsupported load funct3 = 3
        0x0000_6183, // Unsupported load funct3 = 6
        0x0000_7183, // Unsupported load funct3 = 7
        0x0020_3023, // Unsupported store funct3 = 3
        0x0020_4023,
        0x0020_5023,
        0x0020_6023,
        0x0020_7023,
        0x0020_a463, // Unsupported branch funct3 = 2
        0x0020_b463, // Unsupported branch funct3 = 3
        0x0000_91e7, // Invalid JALR funct3
        0x3020_0073, // MRET
        0x1050_0073, // WFI
        0x0000_4073, // Reserved SYSTEM funct3
        0x0000_00f3, // ECALL with nonzero rd
        0x0000_8073, // ECALL with nonzero rs1
        0x0000_100f, // FENCE.I (unsupported extension)
        0xffff_ffff, // Unknown major opcode
    ];
    for (instr, ()): (u32, ()) in instructions {
        let r = sv32::step(s, instr, u32:0xdead_beef);
        assert_eq(r.halt, true);
        assert_eq(r.state, s);
        assert_eq(r.dmem, sv32::DMemReq { addr: u32:0, wdata: u32:0, wstrb: u4:0 });
    }(())
}

#[test]
fn csr_encodings_remain_nops() {
    let s = set_pc(set_reg(init(), u32:3, u32:0xdead_beef), u32:0x40);
    let functions = u32[6]:[1, 2, 3, 5, 6, 7];
    for (f3, ()): (u32, ()) in functions {
        let r = sv32::step(s, i_type(s32:0xc00, u32:1, f3, u32:3, u32:0x73), u32:0);
        assert_eq(r.halt, false);
        assert_eq(r.state.regs, s.regs);
        assert_eq(r.state.pc, u32:0x44);
        assert_eq(r.dmem.wstrb, u4:0);
    }(())
}

#[test]
fn fence_ignores_reserved_operand_and_mode_fields() {
    let s = set_reg(init(), u32:3, u32:0xdead_beef);
    let r = sv32::step(s, u32:0xfff0_818f, u32:0);
    assert_eq(r.halt, false);
    assert_eq(r.state.regs, s.regs);
    assert_eq(r.state.pc, u32:4);
}

#[test]
fn ecall_and_ebreak_preserve_state() {
    let s = set_pc(set_reg(init(), u32:3, u32:0xdead_beef), u32:0x40);
    let ecall = sv32::step(s, u32:0x0000_0073, u32:0);
    let ebreak = sv32::step(s, u32:0x0010_0073, u32:0);
    assert_eq(ecall.state, s);
    assert_eq(ebreak.state, s);
    assert_eq(ecall.halt && ebreak.halt, true);
}
