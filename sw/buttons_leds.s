# Copyright 2026 Universidad de los Andes.
# Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: SHL-0.51
#
# Course: Arquitectura de Computadores (2026)
#
# Authors:
# - Nicolás Villegas <navillegas@miuandes.cl>

# buttons_leds.s — mirrors the button input register onto the LED output
# register. Target: RV32E. Peripheral base 0x8000_0000, buttons at offset
# +8, LEDs at offset +4.

.section .text
.global _start

_start:
    lui  x2, 0x80000     # x2 = 0x80000000  (peripheral base)
    addi x2, x2, 8         # x2 = 0x80000008  (buttons register)
    lui  x3, 0x80000         # x3 = 0x80000000  (peripheral base)
    addi x3, x3, 4              # x3 = 0x80000004  (LED register)

loop:
    lw   x1, 0(x2)                # read buttons
    sw   x1, 0(x3)                  # mirror to LEDs
    jal  x0, loop
