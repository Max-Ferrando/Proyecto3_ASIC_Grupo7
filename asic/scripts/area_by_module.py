#!/usr/bin/env python3
"""area_by_module.py - Area por modulo ANTES de aplanar (seccion 3.3).

LibreLane aplana el diseno durante la sintesis (salvo los modulos con
keep_hierarchy). Para conocer el area de TODOS los modulos se re-sintetiza el
mismo RTL con Yosys, con la misma biblioteca del PDK, pero manteniendo toda la
jerarquia, y se imprime `stat` jerarquico. Es el metodo "estadisticas
jerarquicas previas al aplanamiento" del enunciado.

Uso (dentro del entorno de LibreLane, desde la raiz del repo):
  python3 asic/scripts/area_by_module.py asic/strategy_A/runs/<tag>

Toma de <run>/resolved.json la lista de archivos, los include, el periodo y el
liberty del corner tipico, asi que usa exactamente lo mismo que la corrida.
Deja el reporte en <run>/area_by_module.rpt.
"""
import json
import os
import subprocess
import sys

run = sys.argv[1] if len(sys.argv) > 1 else None
if not run or not os.path.isfile(os.path.join(run, "resolved.json")):
    sys.exit("uso: area_by_module.py <runs/tag>  (necesita resolved.json)")
cfg = json.load(open(os.path.join(run, "resolved.json")))

libs = []
for corner, paths in (cfg.get("LIB") or {}).items():
    if "tt_025C_5v00" in corner:
        libs = paths if isinstance(paths, list) else [paths]
if not libs:
    sys.exit("No encontre el liberty tt_025C_5v00 en resolved.json")
lib = libs[0]
files = " ".join(cfg["VERILOG_FILES"])
incs = " ".join(f"-I{d}" for d in (cfg.get("VERILOG_INCLUDE_DIRS") or []))
period_ps = int(float(cfg["CLOCK_PERIOD"]) * 1000)
rpt = os.path.join(run, "area_by_module.rpt")
script = f"""
read_verilog -sv {incs} {files}
hierarchy -check -top {cfg['DESIGN_NAME']}
setattr -mod -set keep_hierarchy 1 *
synth -top {cfg['DESIGN_NAME']}
dfflibmap -liberty {lib}
abc -D {period_ps} -liberty {lib}
opt_clean -purge
tee -o {rpt} stat -top {cfg['DESIGN_NAME']} -liberty {lib}
"""
ys = os.path.join(run, "area_by_module.ys")
open(ys, "w").write(script)
subprocess.check_call(["yosys", "-q", "-s", ys])
txt = open(rpt).read()
start = txt.find("design hierarchy")
print(txt[start:] if start >= 0 else txt)
print(f"\nReporte completo: {rpt}")
