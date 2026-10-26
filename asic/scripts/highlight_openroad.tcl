# highlight_openroad.tcl - Resalta en la GUI de OpenROAD el banco de registros,
# la ALU y el contador de ciclos (seccion 3.6).
#
# 1) Abrir el layout final en la GUI:
#      librelane --last-run --flow OpenInOpenROAD asic/strategy_A/config.yaml
# 2) En la consola Tcl de la GUI (abajo):
#      source asic/scripts/highlight_openroad.tcl
#    Grupos de color: 0 = banco de registros, 1 = ALU, 2 = contador de ciclos.
# 3) Se guarda la captura en layout_resaltado.png (carpeta desde donde se abrio).

set groups {
  {0 "u_soc.u_core.u_rf/"          "Banco de registros"}
  {1 "u_soc.u_core.u_id.u_alu/"    "ALU"}
  {2 "u_soc.u_periph.u_cycle_cnt/" "Contador de ciclos"}
}
gui::clear_highlights -1
set block [ord::get_db_block]
foreach g $groups {
  lassign $g color prefix label
  set n 0
  foreach inst [$block getInsts] {
    set name [string map {"\\" ""} [$inst getName]]
    if {[string first $prefix $name] >= 0} {
      gui::highlight_inst [$inst getName] $color
      incr n
    }
  }
  puts "$label ($prefix): $n celdas resaltadas en el grupo $color"
}
gui::fit
gui::save_image layout_resaltado.png
puts "Captura guardada en layout_resaltado.png"
