#!/bin/bash
# sim.sh - Simulacion funcional del macro ASIC (seccion 3.7).
#
#   asic/scripts/sim.sh rtl A          # RTL, estrategia A (ROM + RAM)
#   asic/scripts/sim.sh rtl B          # RTL, estrategia B (memoria FF)
#   asic/scripts/sim.sh gl  A <netlist.v>   # netlist post-sintesis
#   asic/scripts/sim.sh stim           # (re)genera sim/asic/stim.txt en modo reactivo
#
# El netlist post-sintesis sale de:
#   librelane asic/sim_A/config.yaml --to Yosys.Synthesis
#   -> asic/sim_A/runs/<tag>/*-yosys-synthesis/asic_top.nl.v
# Los modelos de celdas se toman del PDK (variable PDK_ROOT, por defecto ~/.ciel).
# Todas las corridas usan el programa de simulacion (CLK_HZ=20000) y los mismos
# estimulos (sim/asic/stim.txt), aplicados en los mismos ciclos.
set -e
cd "$(dirname "$0")/../.."
MODE=$1; S=${2:-A}; NL=$3
OUT=sim/asic/out; mkdir -p $OUT
RTL="rtl/asic/asic_top.v rtl/asic/pochoco_reset_sync.v rtl/asic/espino_register_file_ff.v \
 rtl/common/pochoco_soc.v rtl/common/pochoco_periph.v rtl/common/pochoco_cycle_counter.v \
 rtl/common/pochoco_spi_slave.v rtl/common/espino_core/*.v"
if [ "$S" = A ]; then MEM="rtl/asic/pochoco_mem_rom.v sim/asic/gen/game_rom.v"; else MEM="rtl/asic/pochoco_mem_ff.v"; fi
DEFS="${DEFS:-}"

case "$MODE" in
  stim)
    iverilog -g2012 $DEFS -DGEN_STIM -I sim/asic/gen -o $OUT/gen.vvp sim/asic/tb_asic.v $RTL $MEM
    vvp -n $OUT/gen.vvp | grep -v "^VCD"
    echo "Estimulos: sim/asic/stim.txt" ;;
  rtl)
    iverilog -g2012 $DEFS -I sim/asic/gen -DTRACE_FILE=\"$OUT/trace_rtl_$S.txt\" \
      -o $OUT/rtl_$S.vvp sim/asic/tb_asic.v $RTL $MEM
    vvp -n $OUT/rtl_$S.vvp | tee $OUT/rtl_$S.log | grep -E "RESULTADO|ciclo"
    ;;
  gl)
    [ -f "$NL" ] || { echo "uso: sim.sh gl A|B <netlist post-sintesis>"; exit 1; }
    # Modelos Verilog de las celdas: se buscan en el PDK que instalo LibreLane
    # (~/.ciel/ciel/gf180mcu/versions/<hash>/gf180mcuD/...) o en PDK_ROOT.
    VDIR=$(find ${PDK_ROOT:-} $HOME/.ciel -type d -path "*gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog" 2>/dev/null | head -1)
    [ -d "$VDIR" ] || { echo "No encontre los modelos Verilog del PDK (gf180mcuD/.../verilog) en ~/.ciel"; exit 1; }
    echo "Modelos de celdas: $VDIR"
    if [ -f $VDIR/gf180mcu_fd_sc_mcu7t5v0.v ]; then
      MODELS="$VDIR/gf180mcu_fd_sc_mcu7t5v0.v"
      [ -f $VDIR/primitives.v ] && MODELS="$VDIR/primitives.v $MODELS"
    else
      MODELS=$(ls $VDIR/*.v)
    fi
    iverilog -g2012 -DFUNCTIONAL -DUNIT_DELAY=#0 -DGL -DTRACE_FILE=\"$OUT/trace_gl_$S.txt\" \
      -o $OUT/gl_$S.vvp sim/asic/tb_asic.v "$NL" $MODELS
    echo "Simulando el netlist (puede tardar varios minutos)..."
    vvp -n $OUT/gl_$S.vvp | tee $OUT/gl_$S.log | grep -E "RESULTADO|ciclo"
    echo
    if [ -f $OUT/trace_rtl_$S.txt ]; then
      if diff -q $OUT/trace_rtl_$S.txt $OUT/trace_gl_$S.txt >/dev/null; then
        echo "COMPARACION: las salidas (LEDs y displays) del netlist son IDENTICAS al RTL, ciclo a ciclo"
      else
        echo "COMPARACION: hay diferencias entre RTL y netlist:"; diff $OUT/trace_rtl_$S.txt $OUT/trace_gl_$S.txt | head
      fi
      diff <(grep "RESULTADO pul" $OUT/rtl_$S.log) <(grep "RESULTADO pul" $OUT/gl_$S.log) >/dev/null \
        && echo "COMPARACION: ciclos medidos por el programa IDENTICOS en RTL y netlist" \
        || echo "COMPARACION: los ciclos medidos DIFIEREN"
    else
      echo "(corra primero: asic/scripts/sim.sh rtl $S, para comparar)"
    fi ;;
  *) sed -n 2,14p "$0" ;;
esac
