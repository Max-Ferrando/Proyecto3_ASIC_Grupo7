// tb_game.v - Testbench del juego completo (SoC + game.s) con Icarus Verilog.
//
// El programa se ensambla con un reloj "ficticio" mas lento para que la
// simulacion sea corta:  rvasm.py -D CLK_HZ=20000  ->  TENTH = 2000 ciclos.
// El testbench juega una partida: 10 rondas correctas (una de ellas saturada
// en 9,9 s), una pulsacion incorrecta en la ronda 3, y verifica el display.
//
// Correr:  make sim

`timescale 1ns/1ps

module tb_game;
  localparam integer TENTH = 2000;   // debe coincidir con CLK_HZ/10 del -D

  reg        clk = 1'b0;
  reg  [3:0] sw  = 4'b0;
  wire [3:0] led;
  wire       miso;
  wire [13:0] seg;

  always #20 clk = ~clk;             // 25 MHz

  game_top dut (   // programa: -DPOCHOCO_MEMFILE (ver Makefile)
    .i_Clk(clk), .o_LED(led), .i_Switch(sw),
    .o_Segment1_A(seg[0]),  .o_Segment1_B(seg[1]),  .o_Segment1_C(seg[2]),
    .o_Segment1_D(seg[3]),  .o_Segment1_E(seg[4]),  .o_Segment1_F(seg[5]),
    .o_Segment1_G(seg[6]),
    .o_Segment2_A(seg[7]),  .o_Segment2_B(seg[8]),  .o_Segment2_C(seg[9]),
    .o_Segment2_D(seg[10]), .o_Segment2_E(seg[11]), .o_Segment2_F(seg[12]),
    .o_Segment2_G(seg[13]),
    .i_SPI_SCLK(1'b0), .i_SPI_MOSI(1'b0), .i_SPI_CS_n(1'b1), .o_SPI_MISO(miso)
  );

  wire [7:0] display = dut.u_soc.u_periph.digit_q;

  integer errors = 0;
  integer t0;

  function is_onehot(input [3:0] v);
    is_onehot = (v == 4'd1) || (v == 4'd2) || (v == 4'd4) || (v == 4'd8);
  endfunction

  function [7:0] bcd(input integer v);
    bcd = ((v / 10) << 4) | (v % 10);
  endfunction

  task press(input [3:0] b, input integer hold);
    begin
      sw = b;
      repeat (hold) @(posedge clk);
      sw = 4'b0;
    end
  endtask

  // Espera la fase de 4 LEDs y luego el LED objetivo; devuelve el objetivo.
  task wait_target(output [3:0] tgt);
    integer t_all;
    begin
      wait (led == 4'b1111);
      t_all = $time;
      wait (is_onehot(led));
      tgt = led;
      t0  = $time;
      // la fase de 4 LEDs debe durar al menos 30 decimas (40 ns por ciclo)
      if ((t0 - t_all) / 40 < 30 * TENTH) begin
        $display("  FALLA fase de 4 LEDs: %0d ciclos", (t0 - t_all) / 40);
        errors = errors + 1;
      end else
        $display("  ok    fase de 4 LEDs: %0d ciclos (>= %0d)", (t0 - t_all) / 40, 30 * TENTH);
    end
  endtask

  task check(input [7:0] expected, input [127:0] what);
    begin
      if (display !== expected) begin
        $display("  FALLA %0s: display=%h esperado=%h", what, display, expected);
        errors = errors + 1;
      end else
        $display("  ok    %0s: display=%h", what, display);
    end
  endtask

  integer reaction [0:9];
  integer r, sum, expected_avg, clipped;
  reg [3:0] tgt, wrong;

  initial begin
    reaction[0] = 3;  reaction[1] = 5;  reaction[2] = 12; reaction[3] = 7;
    reaction[4] = 120; // > 9,9 s: debe saturar en 99
    reaction[5] = 4;  reaction[6] = 9;  reaction[7] = 15; reaction[8] = 6;
    reaction[9] = 11;

    // Pantalla de espera: presionar cualquier boton para empezar
    repeat (7777) @(posedge clk);
    press(4'b0100, 3000);

    sum = 0;
    for (r = 0; r < 10; r = r + 1) begin
      wait_target(tgt);
      $display("Ronda %0d: LED objetivo = %b", r + 1, tgt);

      if (r == 2) begin
        // Pulsacion incorrecta: debe mostrar EE y repetir la ronda
        wrong = (tgt == 4'b0001) ? 4'b0010 : 4'b0001;
        repeat (4 * TENTH) @(posedge clk);
        press(wrong, 3000);
        repeat (100) @(posedge clk);
        check(8'hEE, "boton incorrecto");
        wait_target(tgt);
        $display("Ronda %0d (reintento): LED objetivo = %b", r + 1, tgt);
      end

      repeat (reaction[r] * TENTH) @(posedge clk);
      press(tgt, 3000);
      repeat (100) @(posedge clk);
      clipped = (reaction[r] > 99) ? 99 : reaction[r];
      sum = sum + clipped;
      check(bcd(clipped), "tiempo de ronda");
    end

    // Promedio (redondeado a la decima mas cercana)
    wait (led == 4'b0101 || led == 4'b1010);
    expected_avg = (sum * 10 + 50) / 100;   // round(sum / 10)
    check(bcd(expected_avg), "promedio");

    if (errors == 0) $display("\nRESULTADO: TODAS LAS PRUEBAS PASARON");
    else             $display("\nRESULTADO: %0d FALLAS", errors);
    $finish;
  end

  // Timeout de seguridad
  initial begin
    #(64'd40 * 64'd6_000_000);
    $display("TIMEOUT");
    $finish;
  end
endmodule
