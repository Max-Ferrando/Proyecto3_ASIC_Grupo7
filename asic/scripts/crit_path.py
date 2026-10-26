#!/usr/bin/env python3
"""crit_path.py - Resume la ruta critica de setup de una corrida (seccion 3.4).

  python3 asic/scripts/crit_path.py asic/strategy_A/runs/<tag> [corner]

corner por defecto: max_ss_125C_4v50 (el mas lento). Lee el max.rpt del STA
post-PnR (OpenSTA, report_checks -path_delay max) y muestra:
  * celda de inicio y de fin, con su modulo,
  * cada etapa de la ruta con su celda, su red y el modulo al que pertenece.
El modulo se deduce del nombre jerarquico de la instancia (modulos con
keep_hierarchy: u_rf, u_alu, u_cycle_cnt) o del nombre de la red, que Yosys
conserva al aplanar (por ejemplo u_soc.u_core.u_if.pc_q).
"""
import glob
import os
import re
import sys

MODULES = [
    ("u_soc.instr_rdata", "pochoco_mem: registro de instruccion (salida de fetch)"),
    ("u_soc.u_core.u_if.pc_q", "espino_if_stage: PC (fetch)"),
    ("u_soc.u_core.u_rf", "espino_register_file (banco de registros)"),
    ("u_soc.u_core.u_id.u_alu", "espino_alu (ALU)"),
    ("u_soc.u_core.u_id.u_decoder", "espino_decoder"),
    ("u_soc.u_core.u_id", "espino_id_stage (decode/ejecucion)"),
    ("u_soc.u_core.u_if", "espino_if_stage (fetch)"),
    ("u_soc.u_core.u_lsu", "espino_load_store_unit (memoria)"),
    ("u_soc.u_core.u_ctrl", "espino_controller"),
    ("u_soc.u_mem.u_rom", "pochoco_game_rom (ROM)"),
    ("u_soc.u_mem", "pochoco_mem"),
    ("u_soc.u_periph.u_cycle_cnt", "pochoco_cycle_counter"),
    ("u_soc.u_periph", "pochoco_periph"),
    ("u_soc.u_spi", "pochoco_spi_slave"),
    ("u_rst_sync", "pochoco_reset_sync"),
    ("u_soc", "pochoco_soc (interconexion)"),
]


def module_of(*names):
    for n in names:
        n = (n or "").replace("\\", "")
        for pre, mod in MODULES:
            if pre in n:
                return mod
    return "?"


def q_nets(run):
    """instancia -> red conectada a su Q, leyendo el netlist final."""
    out = {}
    for nl in glob.glob(os.path.join(run, "final", "nl", "*.nl.v"))[:1]:
        cur = None
        for line in open(nl, errors="ignore"):
            m = re.match(r"\s*(gf180mcu_\w+)\s+(\S+)\s*\(", line)
            if m:
                cur = m.group(2).replace("\\", "")
                continue
            m = re.search(r"\.Q\((.+?)\)", line)
            if m and cur:
                out[cur] = m.group(1).replace("\\", "").strip()
    return out


run = sys.argv[1]
corner = sys.argv[2] if len(sys.argv) > 2 else "max_ss_125C_4v50"
cands = sorted(glob.glob(os.path.join(run, "*-openroad-stapostpnr", corner, "max.rpt")))
if not cands:
    sys.exit(f"No encontre */{corner}/max.rpt en {run}")
txt = open(cands[-1]).read()
first = txt.split("Startpoint:")[1]
first = "Startpoint:" + first.split("slack")[0] + "slack" + first.split("slack")[1].split("\n")[0]
sp = re.search(r"Startpoint: (\S+)", first).group(1)
ep = re.search(r"Endpoint: (\S+)", first).group(1)
print(f"Archivo : {cands[-1]}")
print(f"Inicio  : {sp}")
print(f"Fin     : {ep}")
rows = []
pending_cell = None
for line in first.splitlines():
    m = re.search(r"([\d.-]+)\s+([\d.-]+)\s+[\^v]\s+(\S+)/(\S+) \((\S+)\)", line)
    if m:
        pending_cell = (m.group(3), m.group(4), m.group(5), m.group(2))
        continue
    m2 = re.search(r"\s(\S+) \(net\)", line)
    if m2 and pending_cell:
        inst, pin, cell, t = pending_cell
        rows.append((t, inst, pin, cell.replace("gf180mcu_fd_sc_mcu7t5v0__", ""), m2.group(1)))
        pending_cell = None
print(f"\n{'t (ns)':>8}  {'instancia/pin':40} {'celda':12} {'red':45} modulo")
for t, inst, pin, cell, net in rows:
    print(f"{t:>8}  {(inst + '/' + pin)[:40]:40} {cell:12} {net[:45]:45} {module_of(inst, net)}")
slack = re.search(r"([-\d.]+)\s+slack", first)
print(f"\nslack = {slack.group(1) if slack else '?'} ns")
qn = q_nets(run)
sp_q = qn.get(sp.replace("\\", ""), rows[0][4] if rows else "")
ep_q = qn.get(ep.replace("\\", ""), "")
print(f"Inicio en: {module_of(sp, sp_q)}   (Q = {sp_q})")
print(f"Fin en   : {module_of(ep, ep_q)}   (Q = {ep_q or 'no encontrado en el netlist'})")
