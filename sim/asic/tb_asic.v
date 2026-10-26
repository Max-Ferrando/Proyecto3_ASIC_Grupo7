// tb_asic.v - [PROYECTO 3] Testbench del macro ASIC (RTL y netlist post-sintesis).
//
// Programa de simulacion: game.s ensamblado con -D CLK_HZ=20000, es decir,
// 1 decima = 2000 ciclos y la fase de 3 s = 60.000 ciclos (en vez de 30 M a
// 10 MHz). Es el MISMO programa para RTL y netlist (sim/asic/gen/).
//
// Dos modos:
//  * -DGEN_STIM : modo reactivo. Mira los LEDs, decide cuando presionar y
//    ESCRIBE los estimulos en un archivo con el ciclo absoluto de cada
//    pulsacion (sim/asic/stim.txt). Solo se corre sobre RTL.
//  * (por defecto) modo reproduccion: LEE stim.txt y aplica cada pulsacion en
//    el mismo ciclo absoluto. Se corre igual sobre RTL y sobre el netlist.
//
// Salidas:
//  * TRACE_FILE: cada cambio de LEDs/display con su numero de ciclo.
//  * En consola: el valor de ciclos que el PROPIO PROGRAMA midio en cada
//    ronda (se lee en el puerto de escritura del banco de registros, que el
//    netlist conserva porque espino_register_file se sintetiza con
//    keep_hierarchy), las rondas correctas (registro s1) y los errores.
//
//  * Las salidas se muestrean en el flanco de bajada de cada ciclo.
//
// Defines: -DGL (netlist), -DGEN_STIM, -DSTIM_FILE="..", -DTRACE_FILE="..".
`timescale 1ns/1ps

`ifndef STIM_FILE
`define STIM_FILE "sim/asic/stim.txt"
`endif
`ifndef TRACE_FILE
`define TRACE_FILE "sim/asic/out/trace.txt"
`endif

module tb_asic;
  localparam integer TENTH  = 2000;   // CLK_HZ/10 del programa de simulacion
  localparam real    TCLK   = 100.0;  // ns (periodo objetivo T)

  reg        clk   = 1'b0;
  reg        rst_n = 1'b0;
  reg  [3:0] btn   = 4'b0;
  wire [3:0] led;
  wire [6:0] seg1, seg2;
  wire       miso;

  always #(TCLK / 2) clk = ~clk;

  integer cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  asic_top dut (
    .clk_i (clk), .rst_ni (rst_n),
    .led_o (led), .btn_i (btn), .seg1_o (seg1), .seg2_o (seg2),
    .spi_sclk_i (1'b0), .spi_mosi_i (1'b0), .spi_cs_n_i (1'b1),
    .spi_miso_o (miso)
  );

  // ----------------------------------------------------------------- display
  function [3:0] dec(input [6:0] s);   // segmentos g..a, 1 = encendido
    case (s)
      7'b0111111: dec = 4'h0; 7'b0000110: dec = 4'h1; 7'b1011011: dec = 4'h2;
      7'b1001111: dec = 4'h3; 7'b1100110: dec = 4'h4; 7'b1101101: dec = 4'h5;
      7'b1111101: dec = 4'h6; 7'b0000111: dec = 4'h7; 7'b1111111: dec = 4'h8;
      7'b1101111: dec = 4'h9; 7'b1111001: dec = 4'hE; default:    dec = 4'hF;
    endcase
  endfunction
  wire [7:0] disp = {dec(seg1), dec(seg2)};

  // --------------------------------------------- sondas del banco de registros
`ifdef GL
  wire        rf_we    = dut.\u_soc.u_core.u_rf .we_i ;
  wire [3:0]  rf_waddr = dut.\u_soc.u_core.u_rf .waddr_i ;
  wire [31:0] rf_wdata = dut.\u_soc.u_core.u_rf .wdata_i ;
`else
  wire        rf_we    = dut.u_soc.u_core.u_rf.we_i;
  wire [3:0]  rf_waddr = dut.u_soc.u_core.u_rf.waddr_i;
  wire [31:0] rf_wdata = dut.u_soc.u_core.u_rf.wdata_i;
`endif

  // a4 (x14) = ciclo de inicio; a1 (x11) = lectura del contador y luego
  // "sub a1, a1, a4". La escritura de a1 que vale (a1 anterior - a4) es el
  // resultado medido por el programa.
  reg [31:0] a1_q = 0, a4_q = 0;
  integer    n_meas = 0;
  integer    measured [0:15];
  reg        meas_ok  [0:15];
  integer    rounds = 0;
  always @(posedge clk) begin
    if (rst_n && rf_we) begin
      if (rf_waddr == 4'd14) a4_q <= rf_wdata;
      if (rf_waddr == 4'd11) begin
        if (a4_q != 0 && (a1_q - a4_q) == rf_wdata) begin
          measured[n_meas] = rf_wdata;
          meas_ok[n_meas]  = 1'b0;
          $display("[ciclo %0d] ciclos medidos por el programa: %0d", cyc, rf_wdata);
          n_meas = n_meas + 1;
        end
        a1_q <= rf_wdata;
      end
      if (rf_waddr == 4'd9) begin
        if (rf_wdata > rounds && n_meas > 0) meas_ok[n_meas - 1] = 1'b1;
        rounds = rf_wdata;
        $display("[ciclo %0d] rondas correctas (s1) = %0d", cyc, rf_wdata);
      end
    end
  end

  // ----------------------------------------------------- traza de las salidas
  integer tf;
  initial tf = $fopen(`TRACE_FILE, "w");
  // Se muestrea en el flanco de bajada: asi RTL y netlist se comparan en el
  // mismo instante del ciclo y no aparecen glitches de la logica combinacional.
  reg [11:0] out_q = 12'hFFF;
  always @(negedge clk) if (rst_n && {led, disp} !== out_q) begin
    $fdisplay(tf, "%0d led=%b disp=%h", cyc, led, disp);
    out_q <= {led, disp};
  end

`ifndef GL
  // Uso dinamico de memoria (solo RTL): mayor direccion de instruccion
  // pedida y cantidad de accesos del puerto de datos a la memoria.
  integer max_pc = 0, data_mem_acc = 0;
  always @(posedge clk) if (rst_n) begin
    if (dut.u_soc.u_mem.a_req_i && dut.u_soc.u_mem.a_addr_i > max_pc)
      max_pc = dut.u_soc.u_mem.a_addr_i;
    if (dut.u_soc.u_mem.b_req_i) data_mem_acc = data_mem_acc + 1;
  end
`endif

  task wait_cycles(input integer n); repeat (n) @(posedge clk); endtask
  task wait_until_cycle(input integer c); while (cyc < c) @(posedge clk); endtask

  function is_onehot(input [3:0] v);
    is_onehot = (v == 4'd1) || (v == 4'd2) || (v == 4'd4) || (v == 4'd8);
  endfunction

  integer errors = 0;
  integer last_cycle;

`ifdef GEN_STIM
  // ------------------------------------------------- modo reactivo (genera)
  integer sf, t_led;
  reg [3:0] tgt, wrong;
  task press(input [3:0] b, input integer hold);
    begin
      @(negedge clk);
      $fdisplay(sf, "%0d %h %0d", cyc + 1, b, hold);   // aplica en el siguiente flanco
      btn = b; repeat (hold) @(negedge clk); btn = 4'b0;
    end
  endtask
  task next_target;
    begin
      wait (led == 4'b1111);
      wait (is_onehot(led));
      tgt = led; t_led = cyc;
      $display("[ciclo %0d] LED objetivo = %b", cyc, tgt);
    end
  endtask

  initial begin
    sf = $fopen(`STIM_FILE, "w");
    wait_cycles(5); @(negedge clk); rst_n = 1'b1;
    wait_until_cycle(3000);
    press(4'b0100, 600);                       // inicia la partida

    next_target;                               // ronda 1: correcta
    wait_until_cycle(t_led + 7 * TENTH + 345);
    press(tgt, 600);

    next_target;                               // ronda 2: primero incorrecta
    wrong = (tgt == 4'b0001) ? 4'b0010 : 4'b0001;
    wait_until_cycle(t_led + 3 * TENTH);
    press(wrong, 600);
    next_target;                               // la ronda se reinicia
    wait_until_cycle(t_led + 4 * TENTH + 777);
    press(tgt, 600);

    wait_cycles(4000);
    $fdisplay(sf, "%0d 0 0", cyc);             // fin
    $fclose(sf);
    finish_run;
  end
`else
  // ------------------------------------------- modo reproduccion (lee archivo)
  integer sf, c_at, hold, r;
  reg [3:0] b;
  initial begin
    sf = $fopen(`STIM_FILE, "r");
    if (sf == 0) begin $display("No existe %s", `STIM_FILE); $finish; end
    wait_cycles(5); @(negedge clk); rst_n = 1'b1;
    r = $fscanf(sf, "%d %h %d\n", c_at, b, hold);
    while (r == 3 && hold > 0) begin
      while (cyc + 1 < c_at) @(negedge clk);
      btn = b; repeat (hold) @(negedge clk); btn = 4'b0;
      r = $fscanf(sf, "%d %h %d\n", c_at, b, hold);
    end
    wait_until_cycle(c_at);
    finish_run;
  end
`endif

  task finish_run;
    integer k;
    begin
      $display("------------------------------------------------------------");
      for (k = 0; k < n_meas; k = k + 1)
        $display("RESULTADO pulsacion_%0d %s ciclos_medidos=%0d decimas=%0d",
                 k + 1, meas_ok[k] ? "correcta  " : "INCORRECTA",
                 measured[k], (measured[k] + TENTH / 2) / TENTH);
      $display("RESULTADO rondas_correctas=%0d display_final=%h", rounds, disp);
`ifndef GL
      $display("RESULTADO uso_memoria: mayor_direccion_instruccion=0x%0h (%0d palabras)  accesos_datos_a_memoria=%0d",
               max_pc, max_pc / 4 + 1, data_mem_acc);
`endif
      $fclose(tf);
      $finish;
    end
  endtask

  initial begin
    #(64'd100 * 64'd2_000_000);
    $display("TIMEOUT"); $finish;
  end
endmodule
