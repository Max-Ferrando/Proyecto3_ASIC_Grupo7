# Notas para el informe del Proyecto 3

Lo que ya esta resuelto en el codigo y lo que hay que medir en las corridas de
LibreLane. Los numeros marcados como **estimacion local** salen de una sintesis
con Yosys + la biblioteca GF180 (corner tipico, sin placement ni buffering). Sirven
para saber que esperar; el informe debe usar los numeros de las corridas propias.

## 3.1 Del RTL de FPGA al RTL de ASIC

| Construccion del Proyecto 2 | Donde estaba | Por que no sirve en ASIC | Reemplazo |
|---|---|---|---|
| Primitiva `SB_RAM40_4K` en el banco de registros | `espino_register_file.v` | Es un bloque fisico del iCE40; no existe en GF180. Verilator: *Cannot find file containing module: 'SB_RAM40_4K'* | `rtl/asic/espino_register_file_ff.v`: 15 registros de FFs, lectura registrada (mismo timing), un solo arreglo con 2 puertos de lectura |
| Dos bancos duplicados (u_bankA/u_bankB) | mismo archivo | Solo existian porque cada BRAM tiene un puerto de lectura | Con FFs basta un arreglo y dos multiplexores |
| `$readmemh` + inferencia de BRAM | `pochoco_ram.v` | En silicio no hay archivo que se cargue al encender. Yosys: *Can not open file ... for $readmemh*. Si el archivo existe, la memoria de 512 palabras se vuelve ~16.400 FFs (2,4 mm² de celdas, estimacion local) y el contenido inicial se pierde porque los FFs del PDK no tienen valor inicial | Estrategia A (ROM combinacional) o B (valores de reset), ver 3.2 |
| Power-on reset con valor inicial `reg [3:0] por_cnt = 0` | `pochoco_soc.v` | El valor inicial lo carga el bitstream; un FF de silicio enciende en un valor desconocido. Yosys solo anota *Set init value: \por_cnt = 4'0000* y la biblioteca no lo puede implementar | Pin `rst_ni` externo + `pochoco_reset_sync` (activacion asincrona, liberacion sincrona con 2 FFs) |
| Suposicion de reloj de 25 MHz | `game.s` (`CLK_HZ`) | El macro funciona a 10 MHz (T = 100 ns) | Se ensambla con `-D CLK_HZ=10000000` (ver 3.4) |
| Display activo en bajo | `pochoco_soc.v` | Es propiedad de la Go Board, no del juego | Salidas en logica positiva; la inversion quedo en `rtl/fpga/game_top.v` |

Las construcciones que no generan mensaje (el valor inicial de `por_cnt` y la
polaridad del display) son igual un problema: el flujo las acepta, pero el chip
partiria en un estado aleatorio o mostraria el display invertido.

## 3.2 Memoria y programa

* Instrucciones usadas: **153 palabras** (612 bytes) a 10 MHz. Metodo: el
  assembler cuenta las palabras emitidas (`rvasm.py --report`), y la simulacion
  RTL registra la mayor direccion pedida por el fetch (0x258 = 151 palabras con
  el programa de simulacion, que tiene 150 + 1 lectura anticipada).
* Datos usados: **0 palabras**. Metodo estatico: los 24 `lw`/`sw` usan como base
  `s0 = 0x8000_0000` (perifericos). Metodo dinamico: la simulacion cuenta 0
  accesos del puerto de datos a la memoria. Se reservan 8 palabras en ambas
  estrategias para poder correr programas con pila o variables.
* La ROM tiene capacidad para 256 palabras y la RAM 8: dentro del maximo
  recomendado (256 + 64).

| Estimacion local (T = 100 ns) | A: ROM + RAM | B: memoria FF |
|---|---|---|
| Area de celdas | 162.146 µm² | 881.309 µm² |
| Flip-flops | 1.070 | 5.967 |
| Area secuencial | 47,5 % | 51,3 % |

B es ~5,4 veces mas grande: cada bit del programa pasa a ser un FF con set/reset
(en A es un termino de una funcion combinacional), y ademas necesita dos
multiplexores de lectura de 161 entradas.

## 3.3 Sintesis (estimacion local, estrategia A)

* Celdas mas usadas: `dffrnq_1` (811: banco de registros 480 + lecturas
  registradas 64 + PC, registros de pipeline, contador 32...), `nand2_1` y
  `aoi22_1` (multiplexores de lectura 15:1 de 32 bits x 2 puertos), `mux2_1`
  (722: retencion del valor en los 480 FFs del banco cuando no se escriben),
  `oai21_1`.
* Modulo mas grande: **banco de registros, ~69.000 µm² (~43 %)**.
* Contador de ciclos: **~3.700 µm² (~2,3 %)**.
* Metodo: `SYNTH_KEEP_HIERARCHY_MODULES` conserva `espino_register_file`,
  `espino_alu` y `pochoco_cycle_counter` en el netlist final (su area sale en
  `stat.rpt`), y `asic/scripts/area_by_module.py` re-sintetiza con toda la
  jerarquia para el resto de los modulos.

## 3.4 Timing

* Optimizacion implementada: `ESPINO_REG_DECODE` (config `strategy_A_opt`).
  El banco de registros tiene lectura registrada, asi que cada instruccion pasa
  un ciclo de espera en ID. El decoder se calcula en ese ciclo y sus salidas se
  registran en el mismo flanco que la lectura del banco: el decoder sale de la
  ruta instruccion -> decoder -> mux de operandos -> ALU sin agregar ciclos.
  Verificado: el programa mide exactamente los mismos ciclos (14.349 y 8.778).
* Estimacion local pre-layout, corner lento: slack de setup de 42,3 ns a
  50,7 ns (+8,4 ns) con +2,8 % de area (+69 FFs). Hay que confirmarlo con la
  ruta critica real de la corrida (`crit_path.py`).
* Constantes de `game.s` para T = 100 ns (10 MHz). Solo cambia `CLK_HZ`; el
  resto se deriva:

| Constante | Expresion | 25 MHz (FPGA) | 10 MHz (ASIC) |
|---|---|---|---|
| CLK_HZ | | 25.000.000 | 10.000.000 |
| TENTH | CLK_HZ/10 | 2.500.000 | 1.000.000 |
| HALF_TENTH | TENTH/2 | 1.250.000 | 500.000 |
| ALL_ON_TIME (3 s) | 30·TENTH | 75.000.000 | 30.000.000 |
| MAX_CYCLES (9,9 s) | 99·TENTH | 247.500.000 | 99.000.000 |
| DEBOUNCE (20 ms) | TENTH/5 | 500.000 | 200.000 |
| Divisor del promedio | 10·TENTH | 25.000.000 | 10.000.000 |

  Comprobacion: suma maxima de 10 rondas = 990.000.000 < 2³² (4.294.967.295);
  el contador da la vuelta cada 2³²/10⁷ = 429,5 s. Regenerar: `make asic-gen`.

## 3.5 Costo

Costo = area del die (mm²) x US$23.000. Ejemplo: un die de 0,65 x 0,65 mm
(0,42 mm²) costaria ~US$9.700. `metrics.py` lo calcula en la columna
`cost_USD_23k_per_mm2`. La decision de mayor impacto es la estrategia de memoria
(B multiplica el area ~5,4 veces); despues, FP_CORE_UTIL.

## 3.7 Simulacion post-sintesis (ya verificada localmente)

Programa de simulacion: `CLK_HZ=20000` (1 decima = 2.000 ciclos, 3 s = 60.000
ciclos), igual en RTL y netlist. Estimulos en `sim/asic/stim.txt` (ciclo absoluto
de cada pulsacion).

| Pulsacion | RTL | Netlist post-sintesis |
|---|---|---|
| 1, correcta | 14.349 ciclos -> 07 | 14.349 ciclos -> 07 |
| 2, incorrecta | EE, la ronda se reinicia, s1 sigue en 1 | igual |
| 3, correcta | 8.778 ciclos -> 04 | 8.778 ciclos -> 04 |

Las trazas de LEDs y displays son identicas ciclo a ciclo.
