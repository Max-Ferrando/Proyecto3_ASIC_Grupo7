#!/usr/bin/env python3
"""sweep.py - Barre una variable de LibreLane y resume los resultados.

Ejemplos (desde la raiz del repositorio, dentro del entorno de LibreLane):

  # 3.4 Timing: barrido del periodo de reloj (ns)
  python3 asic/scripts/sweep.py asic/strategy_A/config.yaml CLOCK_PERIOD 100 50 35 25 20

  # 3.5 Floorplan: barrido de utilizacion (%)
  python3 asic/scripts/sweep.py asic/strategy_A/config.yaml FP_CORE_UTIL 30 40 50 60 70

  # 3.5 Floorplan: barrido de dimensiones absolutas del die (um)
  python3 asic/scripts/sweep.py asic/strategy_A/config.yaml DIE_AREA "0 0 600 600" "0 0 500 500" "0 0 450 450"

Cada punto se corre como `librelane --run-tag <VAR>_<valor> -c VAR=valor config`.
Si una corrida falla (por ejemplo, el diseno no cabe) se anota y se sigue con
la siguiente. Al final se escribe <dir_config>/sweep_<VAR>.csv.

Opciones:
  --librelane "librelane --dockerized"   para usar la imagen de Docker
  --solo-resumen                          no corre nada, solo resume
  --extra KEY=VAL                         override adicional para todas las corridas
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics  # noqa: E402


def to_json_value(var, v):
    if var == "DIE_AREA":
        nums = [float(x) for x in v.replace(",", " ").split()]
        return json.dumps(nums)
    try:
        float(v)
        return v
    except ValueError:
        return json.dumps(v)


def tag_of(var, v):
    return f"{var}_{v}".replace(" ", "_").replace(".", "p")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("var")
    ap.add_argument("values", nargs="+")
    ap.add_argument("--librelane", default="librelane --pdk gf180mcuD")
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--solo-resumen", action="store_true")
    args = ap.parse_args()

    cfg_dir = os.path.dirname(os.path.abspath(args.config))
    status = {}
    for v in args.values:
        tag = tag_of(args.var, v)
        if args.solo_resumen:
            continue
        overrides = [f"{args.var}={to_json_value(args.var, v)}"]
        if args.var == "DIE_AREA":
            overrides.append('FP_SIZING="absolute"')
        overrides += args.extra
        cmd = shlex.split(args.librelane) + ["--run-tag", tag, "--overwrite"]
        for o in overrides:
            cmd += ["-c", o]
        cmd.append(args.config)
        print(">>>", " ".join(shlex.quote(c) for c in cmd), flush=True)
        t0 = time.time()
        rc = subprocess.call(cmd)
        status[tag] = (rc, round((time.time() - t0) / 60, 1))
        print(f"<<< {tag}: {'OK' if rc == 0 else 'FALLO (codigo %d)' % rc} en {status[tag][1]} min\n")

    runs = [os.path.join(cfg_dir, "runs", tag_of(args.var, v)) for v in args.values]
    rows = []
    for r in runs:
        s = metrics.summarize(r) if os.path.isdir(r) else None
        if s is None:
            s = {"run": os.path.basename(r), "nota": "sin final/metrics.json (la corrida no termino)"}
        rows.append(s)
    out = os.path.join(cfg_dir, f"sweep_{args.var}.csv")
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    import csv
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    cols = ["run", "CLOCK_PERIOD_ns", "FP_CORE_UTIL_%", "die_um2", "cell_area_um2", "util_%",
            "setup_ws_tt", "setup_tns_tt", "setup_ws_ss", "setup_tns_ss",
            "hold_ws_tt", "hold_tns_tt", "hold_ws_ss", "hold_tns_ss",
            "route_drc", "grt_overflow", "antenna_nets", "timing_ok", "signoff_ok", "nota"]
    cols = [c for c in cols if c in keys]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(metrics.fmt(r.get(c)) for c in cols) + " |")
    print(f"\nTabla completa: {out}")
    for tag, (rc, mins) in status.items():
        print(f"  {tag}: codigo {rc}, {mins} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
