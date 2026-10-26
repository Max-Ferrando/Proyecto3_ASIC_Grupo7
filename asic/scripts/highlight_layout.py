#!/usr/bin/env python3
"""highlight_layout.py - Marca en el layout final donde quedaron el banco de
registros, la ALU y el contador de ciclos (seccion 3.6).

Trazabilidad: en la sintesis esos tres modulos se conservan con
keep_hierarchy (SYNTH_KEEP_HIERARCHY_MODULES), asi que cada celda suya
mantiene el prefijo de su instancia en el DEF final:
    u_soc.u_core.u_rf/...          banco de registros
    u_soc.u_core.u_id.u_alu/...    ALU
    u_soc.u_periph.u_cycle_cnt/... contador de ciclos
El script lee las posiciones de esas celdas del DEF final, dibuja cada celda
en una capa de marca de color, agrega el rectangulo que las encierra y un
texto, y guarda:
    <out>.png      captura del layout anotado (KLayout)
    <out>.gds      el GDS final + las capas de marca (para abrir en KLayout)
    <out>.txt      cuantas celdas y que area ocupa cada grupo

Uso (desde la raiz del repo; con KLayout de LibreLane o `pip install klayout`):
    python3 asic/scripts/highlight_layout.py asic/strategy_A/runs/<tag>
    # o bien:
    klayout -zz -r asic/scripts/highlight_layout.py -rd run=asic/strategy_A/runs/<tag>
"""
import glob
import os
import re
import sys

try:                                   # python normal con `pip install klayout`
    import klayout.db as db
    import klayout.lay as lay
except ImportError:                    # dentro de KLayout (klayout -zz -r ...)
    import pya as db
    import pya as lay
# klayout -rd run=...  define la variable global "run"
RUN = globals().get("run") or (sys.argv[1] if len(sys.argv) > 1 else None)

GROUPS = [
    # (nombre, regex sobre el nombre de instancia, capa de marca, color)
    ("Banco de registros (u_rf)", r"u_soc\.u_core\.u_rf/", 1001, 0xFF3030),
    ("ALU (u_alu)",               r"u_soc\.u_core\.u_id\.u_alu/", 1002, 0x2060FF),
    ("Contador de ciclos (u_cycle_cnt)", r"u_soc\.u_periph\.u_cycle_cnt/", 1003, 0x10B010),
]


def parse_def(path):
    """Devuelve (dbu_por_micron, dieArea(x0,y0,x1,y1), [(nombre, celda, x, y, orient)])."""
    txt = open(path, errors="ignore").read()
    units = int(re.search(r"UNITS\s+DISTANCE\s+MICRONS\s+(\d+)", txt).group(1))
    m = re.search(r"DIEAREA\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)", txt)
    die = tuple(int(v) for v in m.groups())
    comps = []
    sec = txt[txt.find("COMPONENTS"):txt.find("END COMPONENTS")]
    for stmt in sec.split(";"):
        mm = re.search(r"-\s+(\S+)\s+(\S+).*?\+\s+(?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\w+)",
                       stmt, re.S)
        if mm:
            name = mm.group(1).replace("\\", "")
            comps.append((name, mm.group(2), int(mm.group(3)), int(mm.group(4)), mm.group(5)))
    return units, die, comps


def main(run):
    defs = glob.glob(os.path.join(run, "final", "def", "*.def"))
    gdss = glob.glob(os.path.join(run, "final", "gds", "*.gds"))
    if not defs:
        sys.exit(f"No encontre final/def/*.def en {run}")
    units, die, comps = parse_def(defs[0])

    ly = db.Layout()
    if gdss:
        ly.read(gdss[0])
        top = ly.top_cell()
    else:
        ly.dbu = 1.0 / units
        top = ly.create_cell("asic_top")
    scale = (1.0 / units) / ly.dbu          # unidades DEF -> unidades del layout

    def cell_size(cellname):
        ci = ly.cell_by_name(cellname) if ly.has_cell(cellname) else None
        if ci is not None:
            b = ly.cell(ci).bbox()
            return b.width(), b.height()
        return int(2 * units * scale), int(4 * units * scale)  # aproximado si no hay GDS

    report = [f"DEF: {defs[0]}", f"Die: {(die[2]-die[0])/units:.1f} x {(die[3]-die[1])/units:.1f} um", ""]
    for gname, rx, layer, color in GROUPS:
        li = ly.layer(layer, 0)
        lt = ly.layer(layer, 1)
        reg = db.Region()
        n, area = 0, 0.0
        for name, cell, x, y, orient in comps:
            if not re.search(rx, name):
                continue
            w, h = cell_size(cell)
            if orient in ("E", "W", "FE", "FW"):
                w, h = h, w
            box = db.Box(int(x * scale), int(y * scale), int(x * scale) + w, int(y * scale) + h)
            top.shapes(li).insert(box)
            reg.insert(box)
            n += 1
            area += box.area() * ly.dbu * ly.dbu
        if n:
            hull = reg.bbox()
            top.shapes(lt).insert(db.Path([hull.p1, db.Point(hull.right, hull.bottom), hull.p2,
                                           db.Point(hull.left, hull.top), hull.p1],
                                          int(1.0 / ly.dbu)))
            t = db.Text(gname, db.Trans(db.Point(hull.left, hull.top + int(3 / ly.dbu))))
            t.size = int(max(8.0, (die[2] - die[0]) / units / 45) / ly.dbu)   # texto legible
            top.shapes(lt).insert(t)
            report.append(f"{gname}: {n} celdas, {area:,.0f} um2, rectangulo "
                          f"({hull.left*ly.dbu:.0f},{hull.bottom*ly.dbu:.0f})-"
                          f"({hull.right*ly.dbu:.0f},{hull.top*ly.dbu:.0f}) um")
        else:
            report.append(f"{gname}: 0 celdas encontradas (revise el nombre en el DEF)")

    out = os.path.join(run, "layout_anotado")
    ly.write(out + ".gds")
    open(out + ".txt", "w").write("\n".join(report) + "\n")
    print("\n".join(report))

    # Captura: capas del layout en gris tenue, marcas en color
    view = lay.LayoutView()
    view.set_config("background-color", "#ffffff")
    view.set_config("grid-visible", "false")
    view.set_config("apply-text-trans", "true")
    view.set_config("text-font", "1")
    view.load_layout(out + ".gds", True)
    view.max_hier()
    it = view.begin_layers()
    while not it.at_end():
        lp = it.current()
        ln = lp.source_layer
        match = [g for g in GROUPS if g[2] == ln]
        if match:
            c = match[0][3]
            lp.fill_color = c
            lp.frame_color = c
            lp.dither_pattern = 2 if lp.source_datatype == 0 else 1
            lp.width = 1 if lp.source_datatype == 0 else 3
            lp.visible = True
        else:
            lp.fill_color = 0xD8D8D8
            lp.frame_color = 0xC0C0C0
            lp.dither_pattern = 1
            lp.visible = ln in (34, 36) or ln < 10   # metal1/metal2 y capas de base, tenues
        view.set_layer_properties(it, lp)
        it.next()
    view.zoom_fit()
    view.save_image(out + ".png", 1600, 1600)
    print(f"\nCaptura: {out}.png\nGDS anotado: {out}.gds\nResumen: {out}.txt")


if RUN:
    main(RUN)
else:
    sys.exit(__doc__)
