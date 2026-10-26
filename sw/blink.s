# Copyright 2026 Universidad de los Andes.
# Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: SHL-0.51
#
# Course: Arquitectura de Computadores (2026)
#
# Authors:
# - Nicolás Villegas <navillegas@miuandes.cl>

# blink.s — toggles the low 4 LED bits on the pochoco_soc GPIO peripheral,
# using a busy-wait delay loop. Target: RV32E (16 registers), pochoco_soc
# peripheral base at 0x8000_0000, LED register at offset +4.

.section .text
.global _start

_start:
    lui  x2, 0x80000      # x2 = 0x80000000  (peripheral base)
    addi x2, x2, 4         # x2 = 0x80000004  (LED register)
    addi x1, x0, 0          # x1 = led_val = 0

loop:
    sw   x1, 0(x2)          # write led_val to LED register

    lui  x3, 0x200          # x3 = delay counter reload value
delay:
    addi x3, x3, -1
    bne  x3, x0, delay

    xori x1, x1, 15         # toggle low 4 bits of led_val
    jal  x0, loop
