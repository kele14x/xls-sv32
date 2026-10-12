"""Directed RTL programs with expectations independent of the interpreter."""

from dataclasses import dataclass, field

from sv32_ref import demo_program, i_type, r_type, s_type, u_type


@dataclass
class Program:
    name: str
    instructions: list[int]
    data: list[int]
    data_words: int = 256
    registers: dict[int, int] = field(default_factory=dict)
    memory: dict[int, int] = field(default_factory=dict)
    halt_pc: int | None = None


def programs():
    imem, data, size = demo_program()
    yield Program("demo", imem, data, size)

    # Store at the reset vector tests external write strobes during reset.
    yield Program("reset-store", [s_type(0, 0, 0, 2),
                                  i_type(0, 0, 2, 1, 0x03), 0x73],
                  [0xCAFEBABE], registers={1: 0}, memory={0: 0}, halt_pc=8)

    # Upper-halfword store must preserve the lower bytes, then vice versa.
    yield Program("halfword-lanes", [
        u_type(0xB000, 2, 0x37), i_type(-0x433, 2, 0, 2, 0x13),  # x2 = ABCD
        s_type(2, 2, 0, 1), i_type(0, 0, 2, 3, 0x03),
        i_type(2, 0, 5, 4, 0x03), i_type(0x567, 0, 0, 2, 0x13),
        s_type(0, 2, 0, 1), i_type(0, 0, 2, 5, 0x03),
        i_type(0, 0, 5, 6, 0x03), 0x73,
    ], [0x11223344], registers={3: 0xABCD3344, 4: 0xABCD,
                               5: 0xABCD0567, 6: 0x567},
       memory={0: 0xABCD0567}, halt_pc=36)

    counts = [0, 31, 32, 33, 0xFFFFFFE1, 0xFFFFFFFF]
    left = [0x80000001, 0x80000000, 0x80000001, 2, 2, 0x80000000]
    right = [0x80000001, 1, 0x80000001, 0x40000000, 0x40000000, 1]
    signed = [0x80000001, 0xFFFFFFFF, 0x80000001, 0xC0000000, 0xC0000000, 0xFFFFFFFF]
    for count, lvalue, rvalue, avalue in zip(counts, left, right, signed):
        yield Program(f"shift-{count:08x}", [
            u_type(0x80000000, 1, 0x37), i_type(1, 1, 0, 1, 0x13),
            i_type(count, 0, 0, 2, 0x13),
            r_type(0, 2, 1, 1, 3), r_type(0, 2, 1, 5, 4),
            r_type(0x20, 2, 1, 5, 5), 0x73,
        ], [0x11223344], registers={3: lvalue, 4: rvalue, 5: avalue}, halt_pc=24)

    invalid = {
        "mul": 0x022081B3, "op-funct7": 0xFE2081B3,
        "op-funct3": 0x402091B3,
        "slli-upper": 0x02009193, "slli-arithmetic": 0x40009193,
        "srli-upper": 0x0200D193, "demo-shift": 0x8010D193,
        "load-3": 0x00003183, "load-6": 0x00006183, "load-7": 0x00007183,
        "store-3": 0x00203023, "store-4": 0x00204023, "store-5": 0x00205023,
        "store-6": 0x00206023, "store-7": 0x00207023,
        "branch-2": 0x0020A463, "branch-3": 0x0020B463,
        "jalr-funct3": 0x000091E7, "mret": 0x30200073, "wfi": 0x10500073,
        "system-4": 0x00004073, "ecall-rd": 0x000000F3,
        "ecall-rs1": 0x00008073, "fence-i": 0x0000100F,
        "unknown": 0xFFFFFFFF,
    }
    for name, instruction in invalid.items():
        yield Program(f"illegal-{name}", [
            i_type(3, 0, 0, 1, 0x13), i_type(7, 0, 0, 2, 0x13),
            i_type(0x123, 0, 0, 3, 0x13), instruction,
            s_type(0, 0, 0, 2), 0x73,
        ], [0xCAFEBABE], registers={1: 3, 2: 7, 3: 0x123},
           memory={0: 0xCAFEBABE}, halt_pc=12)

    yield Program("csr-fence-nops", [
        i_type(0x123, 0, 0, 3, 0x13),
        *[i_type(0xC00, 1, f3, 3, 0x73) for f3 in (1, 2, 3, 5, 6, 7)],
        0xFFF0818F, 0x00100073,
    ], [0xCAFEBABE], registers={3: 0x123}, memory={0: 0xCAFEBABE}, halt_pc=32)
