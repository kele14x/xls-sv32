"""A self-checking CPU program for RAM lane preservation and LED address decode."""

from sv32_ref import Assembler, i_type, s_type, u_type


def program():
    asm = Assembler()

    def literal(rd, value):
        asm.raw(u_type((value + 0x800) & 0xFFFFF000, rd, 0x37))
        asm.raw(i_type(value, rd, 0, rd, 0x13))

    def equal(rs1, rs2, label):
        asm.branch("beq", rs1, rs2, label)
        asm.raw(0x00100073)  # early EBREAK indicates a failed check
        asm.label(label)

    literal(1, 0x10000000)
    literal(2, 0x1000)
    literal(3, 0x11223344)
    asm.raw(s_type(0, 3, 2, 2))
    literal(3, 0xABCD)
    asm.raw(s_type(2, 3, 2, 1))
    asm.raw(i_type(0, 2, 2, 4, 0x03))
    literal(5, 0xABCD3344)
    equal(4, 5, "ram_ok")
    asm.raw(i_type(1, 0, 0, 3, 0x13))
    asm.raw(s_type(0, 3, 1, 0))  # byte lane 0 turns LED on
    asm.raw(s_type(1, 0, 1, 0))  # byte lane 1 must not clear it
    asm.raw(i_type(0, 1, 2, 4, 0x03))
    asm.raw(i_type(1, 0, 0, 5, 0x13))
    equal(4, 5, "led_ok")
    literal(6, 0x10002000)
    asm.raw(s_type(0, 0, 6, 2))  # unmapped write must not alias RAM
    asm.raw(i_type(0, 2, 2, 4, 0x03))
    literal(5, 0xABCD3344)
    equal(4, 5, "decode_ok")
    asm.raw(i_type(0, 6, 2, 4, 0x03))  # unmapped read returns zero
    equal(4, 0, "unmapped_ok")
    halt_pc = len(asm.program) * 4
    asm.raw(0x00000073)
    return asm.assemble(), halt_pc
