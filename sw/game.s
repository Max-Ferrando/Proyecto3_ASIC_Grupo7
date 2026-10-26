# =============================================================================
# game.s - Juego de reflejos para el Pochoco SoC / Espino Core (RV32E)
# Proyecto 2 - Arquitectura de Computadores 2026-2
#
# Generar game.hex:   python3 tools/rvasm.py sw/game.s -o sw/game.hex
#
# Mapa de memoria usado (base de perifericos 0x8000_0000):
#   +0x00  display 7 segmentos (byte: nibble alto = digito izq., bajo = der.)
#   +0x04  LEDs (bits 3..0)
#   +0x08  botones (bits 3..0, sincronizados, 1 = presionado)
#   +0x0C  contador de ciclos de 32 bits (agregado en pochoco_periph.v)
#
# Restricciones del core: solo x0..x15, sin MUL/DIV y los shifts se ejecutan
# como ADD. Por eso: x*16 se hace con 4 sumas x+x, las divisiones con restas
# sucesivas y los bits se extraen con mascaras (and) en vez de shifts.
#
# Uso de registros "globales" (no los toca ninguna subrutina):
#   s0 = base de perifericos        s1 = rondas correctas acumuladas
#   tp = suma de ciclos de las rondas correctas
#   gp = estado del generador pseudoaleatorio
#   a5 = mascara del LED objetivo    a4 = ciclo de inicio de la medicion
#   a2 = contador auxiliar del programa principal
# Las subrutinas pueden modificar: t0, t1, t2, a0, a1, a3.
# =============================================================================

# ----------------------------- Constantes ------------------------------------
# Solo CLK_HZ depende de la placa; todo lo demas se deriva de ella.
# (En simulacion se sobreescribe con: rvasm.py -D CLK_HZ=20000)
.equ CLK_HZ,      25000000              # reloj de la Go Board: 25 MHz
.equ TENTH,       CLK_HZ / 10           # ciclos por decima de segundo (2.500.000)
.equ HALF_TENTH,  TENTH / 2             # para redondear al entero mas cercano
.equ ALL_ON_TIME, 30 * TENTH            # fase inicial: 3,0 s con los 4 LEDs
.equ NUM_ROUNDS,  10                    # respuestas correctas por partida
.equ MAX_TENTHS,  99                    # el display solo muestra 2 digitos
.equ MAX_CYCLES,  MAX_TENTHS * TENTH    # saturacion por ronda (9,9 s)
.equ DEBOUNCE,    TENTH / 5             # 20 ms sin botones = liberado
.equ BLINK_TIME,  TENTH * 3 / 2         # 150 ms por parpadeo de error
.equ ERR_BLINKS,  3                     # parpadeos al equivocarse
.equ IDLE_STEP,   2 * TENTH             # paso de la animacion de espera
.equ ERR_CODE,    0xEE                  # "EE" en el display = error
.equ LCG_INC,     12345                 # incremento (impar) del LCG

.equ PERIPH,      0x80000000
.equ SEG_OFF,     0x00
.equ LED_OFF,     0x04
.equ BTN_OFF,     0x08
.equ CYC_OFF,     0x0C

.text
.global _start

# ============================ Programa principal =============================
_start:
    li   s0, PERIPH                 # s0 = 0x8000_0000
    li   gp, 0x1234                 # semilla inicial (luego se mezcla con tiempos humanos)

# --- Pantalla de espera: LEDs en "carrusel" hasta que se presione un boton ---
# Sirve para sembrar el generador: el ciclo exacto en que la persona
# presiona es impredecible, asi cada partida tiene una secuencia distinta.
new_game:
    sw   zero, SEG_OFF(s0)          # display "00"
    li   a2, 1                      # LED actual del carrusel
idle_loop:
    sw   a2, LED_OFF(s0)
    li   a0, IDLE_STEP
    jal  ra, wait_or_press          # a0 = botones (0 si se cumplio el tiempo)
    bnez a0, idle_pressed
    add  a2, a2, a2                 # siguiente LED (x2, sin usar shifts)
    li   t0, 16
    bne  a2, t0, idle_loop
    li   a2, 1
    j    idle_loop
idle_pressed:
    lw   t0, CYC_OFF(s0)
    xor  gp, gp, t0                 # semilla <- semilla XOR contador de ciclos
    jal  ra, wait_release
    li   s1, 0                      # rondas correctas = 0
    li   tp, 0                      # suma de ciclos = 0

# --- Inicio de ronda (tambien se vuelve aqui tras un error) ------------------
round_start:
    li   t0, 15
    sw   t0, LED_OFF(s0)            # 1) los cuatro LEDs encendidos
    li   a0, ALL_ON_TIME
    jal  ra, delay                  #    durante 3,0 s medidos con el contador
    jal  ra, wait_release           #    (si alguien mantiene un boton, se espera)

    jal  ra, rand_led               # 2) a5 = LED objetivo (1, 2, 4 u 8)
    sw   a5, LED_OFF(s0)            #    solo el LED objetivo encendido
    lw   a4, CYC_OFF(s0)            # 3) inicio de la medicion (instruccion siguiente)

wait_press:                         # 4) esperar una pulsacion
    lw   a1, CYC_OFF(s0)            #    se lee el contador ANTES de los botones:
    lw   a0, BTN_OFF(s0)            #    si a0 != 0, a1 es el instante de la pulsacion
    beqz a0, wait_press

    sub  a1, a1, a4                 # a1 = ciclos transcurridos (sin signo)
    add  gp, gp, a1                 # mezcla el tiempo de reaccion en la semilla
    bne  a0, a5, wrong_button       # boton distinto (o varios) = error

    # --- respuesta correcta ---
    li   t0, MAX_CYCLES
    bltu a1, t0, no_sat
    mv   a1, t0                     # satura en 9,9 s para no desbordar la suma
no_sat:
    add  tp, tp, a1                 # acumula para el promedio
    li   t0, HALF_TENTH
    add  a0, a1, t0                 # a0 = ciclos + medio paso (redondeo)
    li   a1, TENTH
    jal  ra, udiv                   # a0 = decimas = (ciclos + TENTH/2) / TENTH
    jal  ra, to_bcd                 # a0 = dos digitos decimales
    sw   a0, SEG_OFF(s0)            # 5) mostrar tiempo en decimas
    jal  ra, wait_release

    addi s1, s1, 1                  # 6) una respuesta correcta mas
    li   t0, NUM_ROUNDS
    blt  s1, t0, round_start

    # --- 7) promedio de las 10 rondas ---
    # promedio[decimas] = (suma_ciclos / NUM_ROUNDS) / TENTH
    #                   = suma_ciclos / (NUM_ROUNDS * TENTH), redondeado
    li   t0, NUM_ROUNDS * TENTH / 2
    add  a0, tp, t0
    li   a1, NUM_ROUNDS * TENTH
    jal  ra, udiv
    jal  ra, to_bcd
    sw   a0, SEG_OFF(s0)

    # Pantalla final: LEDs alternan 0101/1010 hasta presionar -> nueva partida
    li   a2, 5
end_loop:
    sw   a2, LED_OFF(s0)
    li   a0, IDLE_STEP
    jal  ra, wait_or_press
    bnez a0, end_pressed
    xori a2, a2, 15                 # 0101 <-> 1010
    j    end_loop
end_pressed:
    lw   t0, CYC_OFF(s0)
    xor  gp, gp, t0
    jal  ra, wait_release
    j    new_game

# --- 8) Boton incorrecto: "EE" + parpadeo, y se repite la ronda actual -------
# s1 y tp NO se modifican: las rondas correctas acumuladas se conservan.
wrong_button:
    li   t0, ERR_CODE
    sw   t0, SEG_OFF(s0)
    jal  ra, wait_release
    li   a2, ERR_BLINKS
err_loop:
    li   t0, 15
    sw   t0, LED_OFF(s0)
    li   a0, BLINK_TIME
    jal  ra, delay
    sw   zero, LED_OFF(s0)
    li   a0, BLINK_TIME
    jal  ra, delay
    addi a2, a2, -1
    bnez a2, err_loop
    j    round_start

# ================================ Subrutinas =================================

# delay: espera a0 ciclos usando el contador de hardware.
# Usa t0, t1. Exacto sin importar cuantos ciclos tome cada instruccion.
delay:
    lw   t0, CYC_OFF(s0)            # t0 = inicio
delay_loop:
    lw   t1, CYC_OFF(s0)
    sub  t1, t1, t0                 # transcurrido = ahora - inicio
    bltu t1, a0, delay_loop
    ret

# wait_or_press: espera hasta a0 ciclos o hasta que se presione un boton.
# Retorna a0 = estado de botones (0 si se agoto el tiempo). Usa t0, t1, t2.
wait_or_press:
    lw   t0, CYC_OFF(s0)
wop_loop:
    lw   t1, BTN_OFF(s0)
    bnez t1, wop_hit
    lw   t2, CYC_OFF(s0)
    sub  t2, t2, t0
    bltu t2, a0, wop_loop
    li   a0, 0
    ret
wop_hit:
    mv   a0, t1
    ret

# wait_release: antirrebote por software. Retorna cuando todos los botones
# llevan DEBOUNCE ciclos seguidos sin presionar. Usa t0, t1, t2, a3.
wait_release:
    li   a3, DEBOUNCE
wr_restart:
    lw   t0, CYC_OFF(s0)            # reinicia la ventana de tiempo
wr_loop:
    lw   t1, BTN_OFF(s0)
    bnez t1, wr_restart             # algun boton sigue presionado (o rebotando)
    lw   t2, CYC_OFF(s0)
    sub  t2, t2, t0
    bltu t2, a3, wr_loop
    ret

# rand_led: avanza el LCG gp = 5*gp + LCG_INC + contador y devuelve en a5 un
# LED objetivo (1, 2, 4 u 8) segun los bits 17 y 16 de gp.
# Se usan bits altos porque en un LCG modulo 2^32 los bits bajos tienen
# periodo muy corto. Sin shifts: los bits se prueban con mascaras.
# Usa t0, t1.
rand_led:
    add  t0, gp, gp                 # 2*gp
    add  t0, t0, t0                 # 4*gp
    add  gp, t0, gp                 # 5*gp
    li   t0, LCG_INC
    add  gp, gp, t0
    lw   t0, CYC_OFF(s0)
    add  gp, gp, t0                 # + entropia del contador de ciclos
    li   a5, 1
    lui  t1, 0x10                   # t1 = 0x0001_0000 (bit 16)
    and  t0, gp, t1
    beqz t0, rl_bit17
    add  a5, a5, a5                 # bit16 = 1 -> x2
rl_bit17:
    add  t1, t1, t1                 # t1 = 0x0002_0000 (bit 17)
    and  t0, gp, t1
    beqz t0, rl_done
    add  a5, a5, a5                 # bit17 = 1 -> x4
    add  a5, a5, a5
rl_done:
    ret

# udiv: division entera sin signo por restas sucesivas.
# Entrada a0 = dividendo, a1 = divisor (> 0). Salida a0 = cociente.
# Aqui el cociente es a lo mas 99, asi que son como maximo 99 iteraciones.
# Usa t0.
udiv:
    li   t0, 0
udiv_loop:
    bltu a0, a1, udiv_done
    sub  a0, a0, a1
    addi t0, t0, 1
    j    udiv_loop
udiv_done:
    mv   a0, t0
    ret

# to_bcd: convierte a0 (0..99, se satura en 99) a dos digitos decimales
# para el display: a0 = decenas*16 + unidades. Usa t0, t1.
to_bcd:
    li   t0, MAX_TENTHS
    bgeu t0, a0, bcd_ok
    mv   a0, t0
bcd_ok:
    li   t1, 0                      # decenas
    li   t0, 10
bcd_loop:
    bltu a0, t0, bcd_pack
    addi a0, a0, -10
    addi t1, t1, 1
    j    bcd_loop
bcd_pack:
    add  t1, t1, t1                 # decenas * 2
    add  t1, t1, t1                 # decenas * 4
    add  t1, t1, t1                 # decenas * 8
    add  t1, t1, t1                 # decenas * 16  (equivale a << 4)
    add  a0, t1, a0
    ret
