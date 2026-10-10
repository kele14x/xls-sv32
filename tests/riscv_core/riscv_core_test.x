// Unit tests for the RV32I core's step function.
//
// Instructions are built with small encoding helpers so the tests read like
// assembly. Each test calls `step` directly, which is the same function XLS
// turns into hardware.

import riscv_core;

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

fn init() -> riscv_core::State {
    riscv_core::State { regs: zero!<u32[32]>(), pc: u32:0 }
}

fn set_reg(state: riscv_core::State, index: u32, value: u32) -> riscv_core::State {
    riscv_core::State { regs: update(state.regs, index, value), pc: state.pc }
}

fn set_pc(state: riscv_core::State, pc: u32) -> riscv_core::State {
    riscv_core::State { regs: state.regs, pc: pc }
}

fn reg(result: riscv_core::StepResult, index: u32) -> u32 {
    riscv_core::reg_read(result.state.regs, index)
}

// ---------------------------------------------------------------------------
// ALU and immediate tests
// ---------------------------------------------------------------------------

#[test]
fn addi_add_sub() {
    let s = init();
    let s = set_reg(s, u32:1, u32:5);
    let r = riscv_core::step(s, i_type(s32:3, u32:1, u32:0, u32:2, u32:0x13), u32:0);
    assert_eq(reg(r, u32:2), u32:8);
    let r = riscv_core::step(r.state,
        r_type(u32:0, u32:2, u32:1, u32:0, u32:3), u32:0);
    assert_eq(reg(r, u32:3), u32:13);
    let r = riscv_core::step(r.state,
        r_type(u32:0x20, u32:1, u32:3, u32:0, u32:4), u32:0);
    assert_eq(reg(r, u32:4), u32:8);
    assert_eq(r.state.pc, u32:12);
}

#[test]
fn sign_extends_negative_immediates() {
    let s = set_reg(init(), u32:1, u32:10);
    let r = riscv_core::step(s, i_type(s32:-1, u32:1, u32:0, u32:2, u32:0x13), u32:0);
    assert_eq(reg(r, u32:2), u32:9);
}

#[test]
fn logic_and_shifts() {
    let s = set_reg(init(), u32:1, u32:0xf0);
    let r = riscv_core::step(s, i_type(s32:15, u32:1, u32:7, u32:2, u32:0x13), u32:0);
    assert_eq(reg(r, u32:2), u32:0);
    let r = riscv_core::step(r.state, i_type(s32:15, u32:1, u32:6, u32:3, u32:0x13), u32:0);
    assert_eq(reg(r, u32:3), u32:255);
    let r = riscv_core::step(r.state, i_type(s32:4, u32:1, u32:1, u32:4, u32:0x13), u32:0);
    assert_eq(reg(r, u32:4), u32:0xf00);
    let r = riscv_core::step(r.state, i_type(s32:4, u32:1, u32:5, u32:5, u32:0x13), u32:0);
    assert_eq(reg(r, u32:5), u32:0xf);
}

#[test]
fn arithmetic_shift_right_keeps_sign() {
    let s = set_reg(init(), u32:1, u32:0x8000_0000);
    let instr = i_type(s32:0x401, u32:1, u32:5, u32:2, u32:0x13);
    let r = riscv_core::step(s, instr, u32:0);
    assert_eq(reg(r, u32:2), u32:0xc000_0000);
}

#[test]
fn set_less_than_signed_and_unsigned() {
    let s = init();
    let s = set_reg(s, u32:1, u32:1);
    let s = set_reg(s, u32:2, u32:0xffff_ffff);
    let r = riscv_core::step(s, r_type(u32:0, u32:2, u32:1, u32:2, u32:3), u32:0);
    assert_eq(reg(r, u32:3), u32:0);
    let r = riscv_core::step(r.state, r_type(u32:0, u32:2, u32:1, u32:3, u32:4), u32:0);
    assert_eq(reg(r, u32:4), u32:1);
}

#[test]
fn lui_and_auipc() {
    let s = set_pc(init(), u32:0x1000);
    let r = riscv_core::step(s, u_type(s32:0x1234_5000, u32:1, u32:0x37), u32:0);
    assert_eq(reg(r, u32:1), u32:0x1234_5000);
    let r = riscv_core::step(r.state, u_type(s32:0x0000_2000, u32:2, u32:0x17), u32:0);
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

    let taken = riscv_core::step(s, b_type(s32:8, u32:0, u32:1, u32:1), u32:0);
    assert_eq(taken.state.pc, u32:8);

    // BGE x1, x0 is false for x1 = -1, so the branch is not taken.
    let not_taken = riscv_core::step(s, b_type(s32:8, u32:0, u32:1, u32:5), u32:0);
    assert_eq(not_taken.state.pc, u32:4);
}

#[test]
fn jal_links_and_jumps() {
    let s = set_pc(init(), u32:0x2000);
    let r = riscv_core::step(s, j_type(s32:16, u32:1), u32:0);
    assert_eq(reg(r, u32:1), u32:0x2004);
    assert_eq(r.state.pc, u32:0x2010);
}

#[test]
fn jalr_clears_low_bit_and_links() {
    let s = set_pc(set_reg(init(), u32:1, u32:0x3001), u32:0x4000);
    let r = riscv_core::step(s, i_type(s32:0, u32:1, u32:0, u32:2, u32:0x67), u32:0);
    assert_eq(reg(r, u32:2), u32:0x4004);
    assert_eq(r.state.pc, u32:0x3000);
}

// ---------------------------------------------------------------------------
// Memory tests
// ---------------------------------------------------------------------------

#[test]
fn word_load_returns_memory_data() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let r = riscv_core::step(s, i_type(s32:12, u32:1, u32:2, u32:2, u32:0x03),
        u32:0xdead_beef);
    assert_eq(reg(r, u32:2), u32:0xdead_beef);
    assert_eq(r.dmem.addr, u32:0x100c);
    assert_eq(r.dmem.wstrb, u4:0);
}

#[test]
fn byte_load_sign_extends() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let r = riscv_core::step(s, i_type(s32:1, u32:1, u32:0, u32:2, u32:0x03),
        u32:0x0000_8000);
    assert_eq(reg(r, u32:2), u32:0xffff_ff80);
    let r = riscv_core::step(s, i_type(s32:1, u32:1, u32:4, u32:3, u32:0x03),
        u32:0x0000_8000);
    assert_eq(reg(r, u32:3), u32:0x80);
}

#[test]
fn halfword_load_at_offset_two() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let r = riscv_core::step(s, i_type(s32:2, u32:1, u32:5, u32:2, u32:0x03),
        u32:0xabcd_1234);
    assert_eq(reg(r, u32:2), u32:0xabcd);
}

#[test]
fn word_store_emits_full_strobe() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let s = set_reg(s, u32:2, u32:0xcafe_babe);
    let r = riscv_core::step(s, s_type(s32:4, u32:2, u32:1, u32:2), u32:0);
    assert_eq(r.dmem.addr, u32:0x1004);
    assert_eq(r.dmem.wdata, u32:0xcafe_babe);
    assert_eq(r.dmem.wstrb, u4:15);
    assert_eq(reg(r, u32:0), u32:0);
}

#[test]
fn byte_store_shifts_into_lane() {
    let s = set_reg(init(), u32:1, u32:0x1000);
    let s = set_reg(s, u32:2, u32:0x0000_00aa);
    let r = riscv_core::step(s, s_type(s32:1, u32:2, u32:1, u32:0), u32:0);
    assert_eq(r.dmem.wdata, u32:0x0000_aa00);
    assert_eq(r.dmem.wstrb, u4:2);
}

// ---------------------------------------------------------------------------
// Architectural invariants
// ---------------------------------------------------------------------------

#[test]
fn x0_is_hardwired_zero() {
    let r = riscv_core::step(init(), i_type(s32:5, u32:0, u32:0, u32:0, u32:0x13),
        u32:0);
    assert_eq(reg(r, u32:0), u32:0);
}

#[test]
fn ecall_halts_and_ebreak_halts() {
    let r = riscv_core::step(init(), u32:0x0000_0073, u32:0);
    assert_eq(r.halt, true);
    let r = riscv_core::step(init(), u32:0x0010_0073, u32:0);
    assert_eq(r.halt, true);
}

#[test]
fn fence_is_a_nop() {
    let s = set_pc(init(), u32:0x40);
    let r = riscv_core::step(s, u32:0x0000_000f, u32:0);
    assert_eq(r.state.pc, u32:0x44);
    assert_eq(r.halt, false);
}
