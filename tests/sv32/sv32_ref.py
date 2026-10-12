"""RV32I reference model, instruction encoders, and demo programs.

The interpreter implements RV32I with the project's memory and halt policy:
little-endian byte-addressed data memory with word-granular reads and byte
strobes, wrap-around word indexing, and halt on ECALL/EBREAK or unsupported
encodings. CSR instructions and FENCE are NOPs.
"""

MASK32 = 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Instruction encoding
# ---------------------------------------------------------------------------

def r_type(funct7, rs2, rs1, funct3, rd, opcode=0x33):
    return ((funct7 << 25) | (rs2 << 20) | (rs1 << 15) |
            (funct3 << 12) | (rd << 7) | opcode) & MASK32


def i_type(imm, rs1, funct3, rd, opcode):
    return ((imm & 0xFFF) << 20 | (rs1 << 15) | (funct3 << 12) |
            (rd << 7) | opcode) & MASK32


def s_type(imm, rs2, rs1, funct3):
    value = imm & 0xFFF
    return ((((value >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) |
            (funct3 << 12) | ((value & 0x1F) << 7) | 0x23) & MASK32


def b_type(imm, rs2, rs1, funct3):
    value = imm & 0x1FFF
    return ((((value >> 12) & 1) << 31) | (((value >> 5) & 0x3F) << 25) |
            (rs2 << 20) | (rs1 << 15) | (funct3 << 12) |
            (((value >> 1) & 0xF) << 8) | (((value >> 11) & 1) << 7) |
            0x63) & MASK32


def u_type(imm, rd, opcode):
    return ((imm & 0xFFFFF000) | (rd << 7) | opcode) & MASK32


def j_type(imm, rd):
    value = imm & 0x1FFFFF
    return ((((value >> 20) & 1) << 31) | (((value >> 1) & 0x3FF) << 21) |
            (((value >> 11) & 1) << 20) | (((value >> 12) & 0xFF) << 12) |
            (rd << 7) | 0x6F) & MASK32


def sign_extend(value, bits):
    """Return the signed Python integer for a two's-complement field."""
    value &= (1 << bits) - 1
    if value & (1 << (bits - 1)):
        value -= 1 << bits
    return value


# ---------------------------------------------------------------------------
# A tiny two-pass assembler supporting the instructions used by the tests
# ---------------------------------------------------------------------------

class Assembler:
    def __init__(self):
        self.program = []
        self.labels = {}

    def label(self, name):
        self.labels[name] = len(self.program) * 4
        return self

    def raw(self, word):
        self.program.append(("raw", word & MASK32))
        return self

    def branch(self, mnemonic, rs1, rs2, target):
        self.program.append((mnemonic, rs1, rs2, target))
        return self

    def jal(self, rd, target):
        self.program.append(("jal", rd, target))
        return self

    def assemble(self):
        branch_funct3 = {"beq": 0, "bne": 1, "blt": 4, "bge": 5,
                         "bltu": 6, "bgeu": 7}
        words = []
        for index, item in enumerate(self.program):
            pc = index * 4
            kind = item[0]
            if kind == "raw":
                words.append(item[1])
            elif kind == "jal":
                words.append(j_type(self.labels[item[2]] - pc, item[1]))
            else:
                _, rs1, rs2, target = item
                offset = self.labels[target] - pc
                words.append(b_type(offset, rs2, rs1, branch_funct3[kind]))
        return words


# ---------------------------------------------------------------------------
# Reference interpreter
# ---------------------------------------------------------------------------

def run(imem, dmem_init, dmem_words=256, max_cycles=100000):
    """Execute until halt and return (regs, pc, dmem, cycles, halted)."""
    imem_words = 1
    while imem_words < len(imem):
        imem_words <<= 1
    imem = list(imem) + [0] * (imem_words - len(imem))
    imem_mask = imem_words - 1
    regs = [0] * 32
    pc = 0
    dmem = list(dmem_init) + [0] * (dmem_words - len(dmem_init))
    mask_words = dmem_words - 1

    def load_word(address):
        return dmem[(address >> 2) & mask_words]

    def store_word(address, value):
        dmem[(address >> 2) & mask_words] = value & MASK32

    cycles = 0
    halted = False
    while cycles < max_cycles and not halted:
        instr = imem[(pc >> 2) & imem_mask]
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F
        a = regs[rs1]
        b = regs[rs2]
        next_pc = (pc + 4) & MASK32
        write_value = None
        write_dest = rd

        invalid = (
            (opcode == 0x33 and (funct7, funct3) not in
             {(0, f) for f in range(8)} | {(0x20, 0), (0x20, 5)}) or
            (opcode == 0x13 and
             ((funct3 == 1 and funct7 != 0) or
              (funct3 == 5 and funct7 not in (0, 0x20)))) or
            (opcode == 0x03 and funct3 not in (0, 1, 2, 4, 5)) or
            (opcode == 0x23 and funct3 not in (0, 1, 2)) or
            (opcode == 0x63 and funct3 not in (0, 1, 4, 5, 6, 7)) or
            (opcode in (0x67, 0x0F) and funct3 != 0) or
            (opcode == 0x73 and instr not in (0x00000073, 0x00100073) and
             funct3 not in (1, 2, 3, 5, 6, 7))
        )
        if invalid:
            halted = True
        elif opcode == 0x33:  # OP
            if funct7 == 0x20:
                if funct3 == 0:
                    result = (a - b) & MASK32
                elif funct3 == 5:
                    result = (sign_extend(a, 32) >> (b & 31)) & MASK32
                else:
                    result = 0
            else:
                result = {
                    0: (a + b) & MASK32,
                    1: (a << (b & 31)) & MASK32,
                    2: 1 if sign_extend(a, 32) < sign_extend(b, 32) else 0,
                    3: 1 if a < b else 0,
                    4: a ^ b,
                    5: a >> (b & 31),
                    6: a | b,
                    7: a & b,
                }[funct3]
            write_value = result & MASK32
        elif opcode == 0x13:  # OP-IMM
            imm = sign_extend(instr >> 20, 12)
            if funct3 == 0:
                result = (a + imm) & MASK32
            elif funct3 == 2:
                result = 1 if sign_extend(a, 32) < sign_extend(imm, 32) else 0
            elif funct3 == 3:
                result = 1 if a < (imm & MASK32) else 0
            elif funct3 == 4:
                result = a ^ imm
            elif funct3 == 6:
                result = a | imm
            elif funct3 == 7:
                result = a & imm
            elif funct3 == 1:
                result = (a << (imm & 31)) & MASK32
            elif funct3 == 5:
                shamt = imm & 31
                result = sign_extend(a, 32) >> shamt if funct7 == 0x20 else a >> shamt
            else:
                result = 0
            write_value = result & MASK32
        elif opcode == 0x03:  # LOAD
            imm = sign_extend(instr >> 20, 12)
            address = (a + imm) & MASK32
            word = load_word(address)
            offset = address & 3
            if funct3 == 0:
                result = sign_extend((word >> (offset * 8)) & 0xFF, 8)
            elif funct3 == 1:
                result = sign_extend((word >> ((address & 2) * 8)) & 0xFFFF, 16)
            elif funct3 == 2:
                result = word
            elif funct3 == 4:
                result = (word >> (offset * 8)) & 0xFF
            elif funct3 == 5:
                result = (word >> ((address & 2) * 8)) & 0xFFFF
            else:
                result = 0
            write_value = result & MASK32
        elif opcode == 0x23:  # STORE
            imm = sign_extend(((instr >> 25) << 5) | ((instr >> 7) & 0x1F), 12)
            address = (a + imm) & MASK32
            word = load_word(address)
            if funct3 == 0:
                shift = (address & 3) * 8
                mask = 0xFF << shift
                value = (b & 0xFF) << shift
            elif funct3 == 1:
                shift = (address & 2) * 8
                mask = 0xFFFF << shift
                value = (b & 0xFFFF) << shift
            else:
                mask = MASK32
                value = b
            store_word(address, (word & ~mask) | (value & mask))
            write_value = None
        elif opcode == 0x63:  # BRANCH
            imm = sign_extend(((instr >> 31) << 12) | (((instr >> 7) & 1) << 11) |
                              (((instr >> 25) & 0x3F) << 5) | (((instr >> 8) & 0xF) << 1), 13)
            taken = {
                0: a == b,
                1: a != b,
                4: sign_extend(a, 32) < sign_extend(b, 32),
                5: sign_extend(a, 32) >= sign_extend(b, 32),
                6: a < b,
                7: a >= b,
            }.get(funct3, False)
            if taken:
                next_pc = (pc + imm) & MASK32
        elif opcode == 0x6F:  # JAL
            imm = sign_extend(((instr >> 31) << 20) | (((instr >> 12) & 0xFF) << 12) |
                              (((instr >> 20) & 1) << 11) | (((instr >> 21) & 0x3FF) << 1), 21)
            write_value = (pc + 4) & MASK32
            next_pc = (pc + imm) & MASK32
        elif opcode == 0x67:  # JALR
            imm = sign_extend(instr >> 20, 12)
            write_value = (pc + 4) & MASK32
            next_pc = (a + imm) & 0xFFFFFFFE
        elif opcode == 0x37:  # LUI
            write_value = instr & 0xFFFFF000
        elif opcode == 0x17:  # AUIPC
            write_value = (pc + (instr & 0xFFFFF000)) & MASK32
        elif opcode == 0x73:  # SYSTEM
            if funct3 == 0 and ((instr >> 20) & 0xFFF) in (0, 1):
                halted = True
        elif opcode == 0x0F:  # FENCE
            pass
        else:
            halted = True

        if write_value is not None and write_dest != 0:
            regs[write_dest] = write_value & MASK32
        if not halted:
            pc = next_pc
        cycles += 1

    return regs, pc, dmem, cycles, halted


# ---------------------------------------------------------------------------
# Demo program used by scripts/test-sv32.py
# ---------------------------------------------------------------------------

def demo_program():
    """Return (imem_words, dmem_init_words, dmem_words)."""
    asm = Assembler()
    asm.raw(i_type(0, 0, 0, 1, 0x13))       # addi x1, x0, 0      sum = 0
    asm.raw(i_type(1, 0, 0, 2, 0x13))       # addi x2, x0, 1      i = 1
    asm.raw(i_type(11, 0, 0, 3, 0x13))      # addi x3, x0, 11     limit = 11
    asm.label("loop")
    asm.raw(r_type(0, 2, 1, 0, 1))          # add  x1, x1, x2
    asm.raw(i_type(1, 2, 0, 2, 0x13))       # addi x2, x2, 1
    asm.branch("bne", 2, 3, "loop")         # bne  x2, x3, loop
    asm.raw(s_type(4, 1, 0, 2))             # sw   x1, 4(x0)
    asm.raw(i_type(4, 0, 2, 4, 0x03))       # lw   x4, 4(x0)
    asm.raw(i_type(0x7F, 0, 0, 5, 0x13))    # addi x5, x0, 0x7f
    asm.raw(s_type(8, 5, 0, 0))             # sb   x5, 8(x0)
    asm.raw(i_type(8, 0, 4, 6, 0x03))       # lbu  x6, 8(x0)
    asm.raw(u_type(0x12345000, 7, 0x37))    # lui  x7, 0x12345
    asm.raw(u_type(0x00001000, 11, 0x17))   # auipc x11, 0x1
    asm.raw(i_type(0x401, 0, 5, 12, 0x13))  # srai x12, x0, 1
    asm.raw(j_type(12, 8))                  # jal  x8, func
    asm.raw(i_type(1, 0, 0, 9, 0x13))       # addi x9, x0, 1
    asm.raw(0x00000073)                     # ecall
    asm.label("func")
    asm.raw(i_type(7, 0, 0, 10, 0x13))      # addi x10, x0, 7
    asm.raw(i_type(0, 8, 0, 0, 0x67))       # jalr x0, 0(x8)
    imem = asm.assemble()
    # Preload one data word so a load-before-store path is exercised too.
    dmem_init = [0x00000000, 0xCAFEBABE, 0x11223344, 0x55667788]
    return imem, dmem_init, 256


if __name__ == "__main__":
    words, data, size = demo_program()
    regs, pc, memory, cycles, halted = run(words, data, size)
    print(f"halted={halted} cycles={cycles} pc=0x{pc:08x}")
    for index, value in enumerate(regs):
        if value:
            print(f"x{index} = 0x{value:08x}")
