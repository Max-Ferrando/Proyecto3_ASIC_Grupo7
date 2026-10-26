# Proyecto 2 (FPGA) + Proyecto 3 (ASIC) - Pochoco SoC / juego de reflejos
#
# ---------------- FPGA (Go Board, iCE40 HX1K) ----------------
#   make hex          sw/game.s -> sw/game.hex (25 MHz)
#   make              hex + sintesis + P&R + bitstream + programar
#   make bin          igual, sin programar
#   make test         pruebas del assembler
#
# ---------------- ASIC (GF180MCU, LibreLane) ----------------
#   make asic-gen     regenera la ROM/init del juego para el ASIC (10 MHz)
#                     y para la simulacion (CLK_HZ=20000)
#   make asic-A       corrida final, estrategia A (ROM + RAM)
#   make asic-B       corrida, estrategia B (memoria unificada FF)
#   make asic-A-opt   estrategia A + decoder registrado (optimizacion 3.4)
#   make asic-sim     simulacion RTL de ambas estrategias
#   make asic-synth-sim  sintesis (solo Yosys) con el programa de simulacion
#
# En Windows (Git Bash) usar PYTHON=python.

PYTHON    ?= python3
ASM       := $(PYTHON) tools/rvasm.py
LIBRELANE ?= librelane --pdk gf180mcuD

# Frecuencia de reloj del macro ASIC: periodo T = 100 ns -> 10 MHz
ASIC_CLK_HZ ?= 10000000
SIM_CLK_HZ  ?= 20000
DATA_WORDS  ?= 8

# ---------------------------------------------------------------- FPGA
TOP  := game_top
PCF  := goboard.pcf
FREQ := 25
SRC_FPGA := $(wildcard rtl/fpga/*.v rtl/common/*.v rtl/common/espino_core/*.v)

.PHONY: all prog bin hex sim test clean asic-gen asic-A asic-B asic-A-opt asic-sim asic-synth-sim

all: prog

hex: sw/game.hex
sw/game.hex: sw/game.s tools/rvasm.py
	$(ASM) sw/game.s -o sw/game.hex -l sw/game.lst

$(TOP).json: $(SRC_FPGA) sw/game.hex
	yosys -p "read_verilog $(SRC_FPGA); synth_ice40 -top $(TOP) -json $(TOP).json; stat"
$(TOP).asc: $(TOP).json $(PCF)
	nextpnr-ice40 --hx1k --package vq100 --freq $(FREQ) --json $(TOP).json --pcf $(PCF) --asc $(TOP).asc
$(TOP).bin: $(TOP).asc
	icepack $(TOP).asc $(TOP).bin
bin: $(TOP).bin
prog: $(TOP).bin
	iceprog $(TOP).bin

CELLS := $(shell yosys-config --datdir 2>/dev/null)/ice40/cells_sim.v
sim:
	$(ASM) sw/game.s -D CLK_HZ=20000 -o sim/game_sim.hex
	iverilog -g2012 -DPOCHOCO_MEMFILE=\"sim/game_sim.hex\" -o sim/tb_game.vvp sim/tb_game.v $(SRC_FPGA) $(CELLS)
	vvp -n sim/tb_game.vvp

test:
	$(PYTHON) tools/test_rvasm.py

# ---------------------------------------------------------------- ASIC
asic-gen:
	$(ASM) sw/game.s -D CLK_HZ=$(ASIC_CLK_HZ) -o sw/game_asic.hex -l sw/game_asic.lst \
	  --rom-v rtl/asic/gen/game_rom.v --mem-vh rtl/asic/gen/game_mem.vh \
	  --data-words $(DATA_WORDS) --report
	$(ASM) sw/game.s -D CLK_HZ=$(SIM_CLK_HZ) -o sim/asic/gen/game_sim.hex \
	  --rom-v sim/asic/gen/game_rom.v --mem-vh sim/asic/gen/game_mem.vh --data-words $(DATA_WORDS)

asic-A: asic-gen
	$(LIBRELANE) --run-tag final asic/strategy_A/config.yaml
asic-B: asic-gen
	$(LIBRELANE) --run-tag final asic/strategy_B/config.yaml
asic-A-opt: asic-gen
	$(LIBRELANE) --run-tag final asic/strategy_A_opt/config.yaml

asic-sim: asic-gen
	@[ -f sim/asic/stim.txt ] || asic/scripts/sim.sh stim
	asic/scripts/sim.sh rtl A
	asic/scripts/sim.sh rtl B

asic-synth-sim: asic-gen
	$(LIBRELANE) --run-tag synth asic/sim_A/config.yaml --to Yosys.Synthesis
	$(LIBRELANE) --run-tag synth asic/sim_B/config.yaml --to Yosys.Synthesis

clean:
	rm -f $(TOP).json $(TOP).asc $(TOP).bin sim/*.vvp sim/*.vcd sim/game_sim.hex
	rm -rf sim/asic/out
