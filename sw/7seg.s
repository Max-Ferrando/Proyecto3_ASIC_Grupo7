# Copyright 2026 Universidad de los Andes.
# Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: SHL-0.51
#
# Course: Arquitectura de Computadores (2026)
#
# Authors:
# - Nicolás Villegas <navillegas@miuandes.cl>

# 7seg.s — counts 0-9 on the pochoco_soc 7-segment peripheral (register at
# offset 0 of the peripheral base), applying a +6 BCD-style adjustment so the
# raw binary counter skips hex digits A-F and wraps at 10. Target: RV32E.

.section .text
.global _start

_start:
    lui  x2, 0x80000        # x2 = 0x80000000  (peripheral base / 7seg reg)
    addi x1, x0, 0            # x1 = digit_value = 0

loop:
    sw   x1, 0(x2)             # display digit_value

    lui  x3, 0x200              # x3 = delay counter reload value
delay:
    addi x3, x3, -1
    bne  x3, x0, delay

    addi x1, x1, 1               # digit_value++
    andi x4, x1, 15                # x4 = digit_value & 0xF
    addi x5, x0, 10                 # x5 = 10
    bne  x4, x5, skip
    addi x1, x1, 6                   # skip hex digits A-F

skip:
    addi x5, x0, 160                  # wrap threshold
    bne  x1, x5, loop
    addi x1, x0, 0                     # reset digit_value
    jal  x0, loop
