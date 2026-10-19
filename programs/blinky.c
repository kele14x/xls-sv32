/* Bare-metal RV32I blinky for the 100 MHz SV32 SoC. */
#ifndef DELAY_ITERATIONS
#define DELAY_ITERATIONS 24999996u
#endif

/* crt0 clears this .bss variable on every reset, including warm resets. */
volatile unsigned int blink_count;

static __attribute__((noinline)) void delay(unsigned int iterations)
{
    while (iterations != 0u) {
        /* Keep the delay loop while allowing its counter to stay in a register. */
        __asm__ volatile ("" ::: "memory");
        --iterations;
    }
}

int main(void)
{
    volatile unsigned int *const led = (volatile unsigned int *)0x10000000u;
    for (;;) {
        ++blink_count;
        *led = blink_count & 1u;
        delay(DELAY_ITERATIONS);
    }
}
