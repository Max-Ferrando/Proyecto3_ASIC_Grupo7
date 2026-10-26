#!/usr/bin/env python3
"""metrics.py - Resume las corridas de LibreLane en una tabla (CSV + Markdown).

Uso (desde la raiz del repositorio):
    python3 asic/scripts/metrics.py asic/strategy_A/runs/*        # tabla en pantalla
    python3 asic/scripts/metrics.py asic/strategy_A/runs/* -o resultados/A.csv

Para cada corrida lee:
  * runs/<tag>/resolved.json            -> CLOCK_PERIOD, FP_CORE_UTIL, DIE_AREA
  * runs/<tag>/final/metrics.json       -> area, timing por corner, DRC, LVS, antena
  * el log de ruteo global              -> overflow (metrica de congestion)
  * el netlist final                    -> numero de flip-flops

Corners reportados:
  tipico : nom_tt_025C_5v00   (proceso tipico, 25 C, 5,0 V)
  lento  : max_ss_125C_4v50   (proceso lento, 125 C, 4,5 V, parasitos maximos)
  peor   : el peor valor entre TODOS los corners de STA del PDK
Una corrida "cierra" si setup y hold tienen WS >= 0 y TNS = 0 en todos los corners,
DRC = 0, LVS = 0 y no quedan violaciones de antena.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys

TYP = "nom_tt_025C_5v00"
SLOW = "max_ss_125C_4v50"


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def corner_values(m, metric):
    """Devuelve {corner: valor} para una metrica por corner."""
    out = {}
    prefix = metric + "__corner:"
    for k, v in m.items():
        if k.startswith(prefix):
            out[k[len(prefix):]] = v
    return out


def worst(values, fn=min):
    vals = [v for v in values if isinstance(v, (int, float))]
    return fn(vals) if vals else None


def bbox_area(bbox):
    """'x0 y0 x1 y1' (um) -> area en um^2."""
    try:
        x0, y0, x1, y1 = [float(t) for t in str(bbox).split()]
        return (x1 - x0) * (y1 - y0), x1 - x0, y1 - y0
    except ValueError:
        return None, None, None


def grt_overflow(run):
    """Busca el overflow total en el log del ruteo global (congestion)."""
    logs = sorted(glob.glob(os.path.join(run, "*-openroad-globalrouting", "*.log")))
    total = None
    for lg in logs:
        try:
            txt = open(lg, errors="ignore").read()
        except OSError:
            continue
        # Tabla "Final congestion report": la fila Total trae el overflow al final
        for line in txt.splitlines():
            if line.strip().startswith("Total"):
                nums = re.findall(r"(\d+)\s*$", line.strip())
                if nums:
                    total = int(nums[0])
    return total


def count_ffs(run):
    nl = glob.glob(os.path.join(run, "final", "nl", "*.nl.v"))
    if not nl:
        return None
    n = 0
    with open(nl[0], errors="ignore") as f:
        for line in f:
            if re.match(r"\s*gf180mcu_\w+__(dff|sdff|latq|icg)\w*\s", line):
                n += 1
    return n


def summarize(run):
    cfg = load_json(os.path.join(run, "resolved.json"))
    m = load_json(os.path.join(run, "final", "metrics.json"))
    if not m:
        return None
    r = {"run": os.path.basename(os.path.normpath(run))}
    r["CLOCK_PERIOD_ns"] = cfg.get("CLOCK_PERIOD")
    r["FP_CORE_UTIL_%"] = cfg.get("FP_CORE_UTIL") if cfg.get("FP_SIZING", "relative") == "relative" else None
    r["DIE_AREA"] = cfg.get("DIE_AREA") if cfg.get("FP_SIZING") == "absolute" else None

    die, w, h = bbox_area(m.get("design__die__bbox", ""))
    core, _, _ = bbox_area(m.get("design__core__bbox", ""))
    r["die_um2"] = round(die, 1) if die else m.get("design__die__area")
    r["die_w_um"] = round(w, 1) if w else None
    r["die_h_um"] = round(h, 1) if h else None
    r["core_um2"] = round(core, 1) if core else m.get("design__core__area")
    r["cell_area_um2"] = m.get("design__instance__area__stdcell", m.get("design__instance__area"))
    r["util_%"] = m.get("design__instance__utilization__stdcell", m.get("design__instance__utilization"))
    if isinstance(r["util_%"], float) and r["util_%"] <= 1:
        r["util_%"] = round(100 * r["util_%"], 2)
    r["cells"] = m.get("design__instance__count__stdcell", m.get("design__instance__count"))
    r["flip_flops"] = m.get("design__instance__count__class:sequential_cell") or count_ffs(run)

    for kind in ("setup", "hold"):
        ws = corner_values(m, f"timing__{kind}__ws")
        tns = corner_values(m, f"timing__{kind}__tns")
        r[f"{kind}_ws_tt"] = ws.get(TYP)
        r[f"{kind}_tns_tt"] = tns.get(TYP)
        r[f"{kind}_ws_ss"] = ws.get(SLOW)
        r[f"{kind}_tns_ss"] = tns.get(SLOW)
        r[f"{kind}_ws_worst"] = worst(ws.values()) if ws else m.get(f"timing__{kind}__ws")
        r[f"{kind}_tns_worst"] = worst(tns.values()) if tns else m.get(f"timing__{kind}__tns")

    r["route_drc"] = m.get("route__drc_errors")
    r["magic_drc"] = m.get("magic__drc_error__count")
    r["klayout_drc"] = m.get("klayout__drc_error__count")
    r["lvs_errors"] = m.get("design__lvs_error__count")
    r["antenna_nets"] = m.get("antenna__violating__nets")
    r["antenna_pins"] = m.get("antenna__violating__pins")
    r["grt_overflow"] = grt_overflow(run)

    # Frecuencia maxima alcanzable con este periodo (si cierra): f = 1/T.
    # Estimacion del periodo minimo con el peor slack: T - WS_setup_peor.
    T = r["CLOCK_PERIOD_ns"]
    wss = r["setup_ws_worst"]
    if isinstance(T, (int, float)) and isinstance(wss, (int, float)):
        r["T_min_est_ns"] = round(T - wss, 2)
        r["fmax_est_MHz"] = round(1000.0 / (T - wss), 2) if T - wss > 0 else None

    ok_timing = all(
        isinstance(r[k], (int, float))
        for k in ("setup_ws_worst", "hold_ws_worst", "setup_tns_worst", "hold_tns_worst")
    ) and r["setup_ws_worst"] >= 0 and r["hold_ws_worst"] >= 0 \
        and r["setup_tns_worst"] == 0 and r["hold_tns_worst"] == 0
    ok_signoff = all((r[k] or 0) == 0 for k in ("route_drc", "magic_drc", "klayout_drc", "lvs_errors", "antenna_nets"))
    r["timing_ok"] = ok_timing
    r["signoff_ok"] = ok_signoff
    r["cost_USD_23k_per_mm2"] = round(r["die_um2"] / 1e6 * 23000, 0) if isinstance(r["die_um2"], (int, float)) else None
    return r


def fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 1000 else f"{v:,.0f}"
    if isinstance(v, bool):
        return "SI" if v else "NO"
    return "-" if v is None else str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="directorios runs/<tag>")
    ap.add_argument("-o", "--csv", help="guardar tabla CSV")
    ap.add_argument("--cols", help="columnas a mostrar (separadas por coma)")
    args = ap.parse_args()

    rows = [r for r in (summarize(p) for p in args.runs if os.path.isdir(p)) if r]
    if not rows:
        print("No se encontraron corridas con final/metrics.json", file=sys.stderr)
        return 1
    cols = list(rows[0].keys())
    if args.cols:
        cols = [c.strip() for c in args.cols.split(",")]

    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(fmt(r.get(c)) for c in cols) + " |")

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            wr.writeheader()
            wr.writerows(rows)
        print(f"\nCSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
