create_clock -name CLOCK1_50 -period 20.000 [get_ports CLOCK1_50]
# The generated PLL and reset-release IP supply their generated-clock .sdc files.
derive_clock_uncertainty
# KEY0 drives asynchronous reset assertion; release is synchronized to 100 MHz.
set_false_path -from [get_ports KEY0_N]
# A human-visible LED has no external capture clock.
# Declare a zero external delay budget for I/O-constraint completeness;
# the false path below excludes off-chip capture timing for this indicator.
set_output_delay -clock CLOCK1_50 -max 0.000 [get_ports LED0_N]
set_output_delay -clock CLOCK1_50 -min 0.000 [get_ports LED0_N]
set_false_path -to [get_ports LED0_N]
