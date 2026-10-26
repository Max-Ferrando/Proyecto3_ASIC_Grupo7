#!/bin/bash
# versions.sh - Versiones exactas para el README (correr dentro de nix-shell).
echo "LibreLane : $(librelane --version 2>/dev/null)"
echo "Yosys     : $(yosys -V 2>/dev/null)"
echo "OpenROAD  : $(openroad -version 2>/dev/null | tail -1)"
echo "Magic     : $(magic --version 2>/dev/null)"
echo "Netgen    : $(netgen -batch 2>/dev/null </dev/null | head -1)"
echo "KLayout   : $(klayout -v 2>/dev/null)"
echo "Verilator : $(verilator --version 2>/dev/null)"
echo "PDK (ciel):"; ciel ls --pdk-family gf180mcu 2>/dev/null || echo "  (correr dentro de nix-shell)"
echo "Biblioteca de celdas: gf180mcu_fd_sc_mcu7t5v0"
