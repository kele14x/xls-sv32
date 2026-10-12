"""Build a 13-instruction RV32I blinky without a cross compiler.

The blink counter lives in DMEM, so blinking exercises instruction fetch,
loads, stores, arithmetic, branches, jumps, and LED MMIO.
"""

DEFAULT_DELAY = 24_999_996  # (100 MHz * 0.5 seconds - 8 loop overhead cycles) / 2


def immediate(value, rs1, funct3, rd, opcode=0x13):
    return ((value & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def program(delay_iterations=DEFAULT_DELAY):
    """Return [(instruction, assembly)] for a half-period of 2*delay + 8 cycles."""
    if not 1 <= delay_iterations <= 0xFFFFFFFF:
        raise ValueError("delay iterations must be between 1 and 0xffffffff")
    high = ((delay_iterations + 0x800) >> 12) & 0xFFFFF
    low = (delay_iterations & 0xFFF) - (0x1000 if delay_iterations & 0x800 else 0)
    return [
        (0x100000B7, "lui x1, 0x10000       # LED MMIO address"),
        (0x00001137, "lui x2, 0x1           # DMEM base"),
        (0x00012023, "sw x0, 0(x2)          # initialize counter"),
        (0x00012183, "lw x3, 0(x2)          # loop: reload counter"),
        (0x00118193, "addi x3, x3, 1"),
        (0x00312023, "sw x3, 0(x2)"),
        (0x0011F213, "andi x4, x3, 1"),
        (0x0040A023, "sw x4, 0(x1)          # drive LED"),
        ((high << 12) | 0x2B7, f"lui x5, 0x{high:x}"),
        (immediate(low, 5, 0, 5), f"addi x5, x5, {low}"),
        (0xFFF28293, "addi x5, x5, -1       # delay:"),
        (0xFE029EE3, "bne x5, x0, -4        # delay"),
        (0xFDDFF06F, "jal x0, -36           # loop"),
    ]
