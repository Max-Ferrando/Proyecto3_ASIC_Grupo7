#!/usr/bin/env python3
"""area_by_module.py - Area por modulo ANTES de aplanar (seccion 3.3).

LibreLane aplana el diseno durante la sintesis (salvo los modulos con
keep_hierarchy). Para conocer el area de TODOS los modulos se re-sintetiza el
mismo RTL con Yosys, con la misma biblioteca del PDK, pero manteniendo toda la
jerarquia, y se imprime `stat` jerarquico. Es el metodo "estadisticas
jerarquicas previas al aplanamiento" del enunciado.

Uso (dentro de nix-shell, desde la raiz del repo):
  python3 asic/scripts/area_by_module.py asic/strategy_A/runs/final

Toma la lista de archivos y los include del config.yaml de la estrategia (la
carpeta padre de runs/), el periodo de reloj de la corrida y el liberty del
corner tipico del PDK instalado por LibreLane (~/.ciel). Imprime ademas las
cinco celdas mas usadas. Deja el reporte en <run>/area_by_module.rpt.
"""
import glob
import json
import os
import re
import subprocess
import sys

import yaml

run = os.path.normpath(sys.argv[1]) if len(sys.argv) > 1 else None
if not run or not os.path.isdir(run):
    sys.exit("uso: area_by_module.py <asic/strategy_X/runs/tag>")

strategy_dir = os.path.dirname(os.path.dirname(run))        # asic/strategy_X
cfg_path = os.path.join(strategy_dir, "config.yaml")
cfg = yaml.safe_load(open(cfg_path))


def resolve(p):
    return os.path.normpath(os.path.join(strategy_dir, p[len("dir::"):])) if p.startswith("dir::") else p


files = [resolve(f) for f in cfg["VERILOG_FILES"]]
incs = [resolve(d) for d in (cfg.get("VERILOG_INCLUDE_DIRS") or [])]
defines = cfg.get("VERILOG_DEFINES") or []

resolved = {}
try:
    resolved = json.load(open(os.path.join(run, "resolved.json")))
except (OSError, ValueError):
    pass
period = float(resolved.get("CLOCK_PERIOD", cfg.get("CLOCK_PERIOD", 100)))

# Liberty del corner tipico
lib = None
for corner, paths in (resolved.get("LIB") or {}).items():
    if "tt_025C_5v00" in corner:
        lib = (paths if isinstance(paths, list) else [paths])[0]
if not lib:
    roots = [os.environ.get("PDK_ROOT", ""), os.path.expanduser("~/.ciel")]
    for r in roots:
        hits = glob.glob(os.path.join(r, "**", "gf180mcuD", "libs.ref", "gf180mcu_fd_sc_mcu7t5v0",
                                      "lib", "*tt_025C_5v00*.lib"), recursive=True)
        if hits:
            lib = sorted(hits)[-1]
            break
if not lib:
    sys.exit("No encontre el liberty tt_025C_5v00 del PDK (revise ~/.ciel o PDK_ROOT)")

top = cfg["DESIGN_NAME"]
rpt = os.path.join(run, "area_by_module.rpt")
script = "\n".join([
    "read_verilog -sv " + " ".join(f"-I{d}" for d in incs) + " "
    + " ".join(f"-D{d}" for d in defines) + " " + " ".join(files),
    f"hierarchy -check -top {top}",
    "setattr -mod -set keep_hierarchy 1 *",
    f"synth -top {top}",
    f"dfflibmap -liberty {lib}",
    f"abc -D {int(period * 1000)} -liberty {lib}",
    "opt_clean -purge",
    f"tee -o {rpt} stat -top {top} -liberty {lib}",
    "",
])
ys = os.path.join(run, "area_by_module.ys")
open(ys, "w").write(script)
print(f"Sintetizando con jerarquia ({len(files)} archivos, T = {period} ns)...")
subprocess.check_call(["yosys", "-q", "-s", ys])

txt = open(rpt).read()
start = txt.find("design hierarchy")
block = txt[start:] if start >= 0 else txt

# Tabla de area por modulo (arbol de jerarquia con area incluyendo submodulos)
print("\nArea por modulo (incluye submodulos):")
rows = re.findall(r"^\s+(\d+)\s+([\d.E+]+)\s+(\S.*)$", block, re.M)
total = None
tree = []
for count, area, name in rows:
    if name.startswith("gf180") or name in ("cells", "wires", "wire bits", "public wires",
                                             "public wire bits", "ports", "port bits",
                                             "submodules"):
        continue
    if "gf180" in name:
        continue
    if tree and name.strip() == tree[0][0]:
        break
    if any(t[0] == name.strip() and t[1] == int(count) for t in tree) or int(count) <= 1 and tree:
        continue
    tree.append((name.strip(), int(count), float(area)))
    if total is None:
        total = float(area)
for name, count, area in tree:
    pct = 100 * area / total if total else 0
    print(f"  {name:55s} {count:7d} celdas {area:12,.0f} um2  {pct:5.1f} %")

# Cinco celdas mas usadas en todo el diseno
cells = re.findall(r"^\s+(\d+)\s+[\d.E+]+\s+(gf180mcu_fd_sc_mcu7t5v0__\w+)", block, re.M)
agg = {}
# el total del diseno es el mayor conteo de cada celda entre los bloques
for count, cell in cells:
    agg[cell] = max(agg.get(cell, 0), int(count))
print("\nCinco celdas mas usadas:")
for cell, n in sorted(agg.items(), key=lambda kv: -kv[1])[:5]:
    print(f"  {n:6d}  {cell.replace('gf180mcu_fd_sc_mcu7t5v0__', '')}")
print(f"\nReporte completo: {rpt}")
