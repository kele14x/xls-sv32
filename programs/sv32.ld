OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    IMEM (rx) : ORIGIN = 0x00000000, LENGTH = 1K
    DMEM (rw) : ORIGIN = 0x00001000, LENGTH = 1K
}

__stack_top = ORIGIN(DMEM) + LENGTH(DMEM);
__stack_bottom = __stack_top - 256;

SECTIONS
{
    .text :
    {
        KEEP(*(.text.start))
        *(.text .text.*)
        . = ALIGN(4);
    } > IMEM

    /* The Harvard instruction ROM cannot be read through the data port.
       Reject initializers/constants that would need a separate RAM image. */
    .unsupported_data :
    {
        *(.data .data.* .sdata .sdata.*)
        *(.rodata .rodata.* .srodata .srodata.*)
        *(.init_array .init_array.* .fini_array .fini_array.*)
    } > DMEM

    .bss (NOLOAD) :
    {
        . = ALIGN(4);
        __bss_start = .;
        *(.bss .bss.* .sbss .sbss.*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > DMEM

    /DISCARD/ : { *(.comment .note.GNU-stack .eh_frame .eh_frame.*) }
}

ASSERT(_start == ORIGIN(IMEM), "Reset entry must be at address zero")
ASSERT(SIZEOF(.unsupported_data) == 0,
       "Initialized data/rodata require RAM-image support on this Harvard SoC")
ASSERT(__bss_end <= __stack_bottom, "BSS overlaps the reserved 256-byte stack")
