// Copyright 2026 Universidad de los Andes.
// Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
// you may not use this file except in compliance with the License.
// SPDX-License-Identifier: SHL-0.51
//
// Course: Arquitectura de Computadores (2026)
// 
// Authors:
// - Nicolás Villegas <navillegas@miuandes.cl>

module pochoco_periph (
  input  wire        clk_i,
  input  wire        rst_ni,
  input  wire        sel_i,
  input  wire        req_i,
  input  wire        we_i,
  input  wire [7:0]  addr_i,
  input  wire [31:0] wdata_i,
  output reg  [31:0] rdata_o,
  output wire [3:0]  leds_o,
  input  wire [3:0]  btn_i,
  output wire [6:0]  seg1_o,
  output wire [6:0]  seg2_o
);

  wire [5:0] off    = addr_i[7:2];
  wire       access = sel_i & req_i;

  // LEDs and raw digit registers
  reg [3:0]  led_q;
  reg [7:0]  digit_q;
  
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      led_q   <= 4'b0;
      digit_q <= 8'b0;
    end else if (access & we_i) begin
      case (off)
        6'd0: digit_q <= wdata_i[7:0];
        6'd1: led_q   <= wdata_i[3:0];
        default: ;
      endcase
    end
  end

  assign leds_o = led_q;

  // --------------------------------------------------------------------
  // [PROYECTO 2] Contador de ciclos libre (offset 0x0C, solo lectura).
  // Se incrementa en 1 cada flanco de reloj (25 MHz en la Go Board):
  // 1 ciclo = 40 ns, 1 decima de segundo = 2.500.000 ciclos.
  // Da la vuelta cada 2^32 / 25e6 = 171,8 s; el software solo usa
  // diferencias (fin - inicio) en aritmetica sin signo, que son correctas
  // mientras el intervalo medido sea menor a ~171 s.
  // --------------------------------------------------------------------
  reg [31:0] cycle_q;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) cycle_q <= 32'b0;
    else         cycle_q <= cycle_q + 32'd1;
  end

  // [PROYECTO 2] Sincronizador de 2 flip-flops para los botones: son
  // entradas asincronas y sin esto pueden provocar metaestabilidad.
  reg [3:0] btn_meta_q, btn_sync_q;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      btn_meta_q <= 4'b0;
      btn_sync_q <= 4'b0;
    end else begin
      btn_meta_q <= btn_i;
      btn_sync_q <= btn_meta_q;
    end
  end

  // Hex to 7-segment decoder function
  function [6:0] hex2seg;
    input [3:0] hex;
    begin
      case (hex)
        4'h0: hex2seg = 7'b0111111; // 0
        4'h1: hex2seg = 7'b0000110; // 1
        4'h2: hex2seg = 7'b1011011; // 2
        4'h3: hex2seg = 7'b1001111; // 3
        4'h4: hex2seg = 7'b1100110; // 4
        4'h5: hex2seg = 7'b1101101; // 5
        4'h6: hex2seg = 7'b1111101; // 6
        4'h7: hex2seg = 7'b0000111; // 7
        4'h8: hex2seg = 7'b1111111; // 8
        4'h9: hex2seg = 7'b1101111; // 9
        4'hA: hex2seg = 7'b1110111; // A
        4'hB: hex2seg = 7'b1111100; // b
        4'hC: hex2seg = 7'b0111001; // C
        4'hD: hex2seg = 7'b1011110; // d
        4'hE: hex2seg = 7'b1111001; // E
        4'hF: hex2seg = 7'b1110001; // F
        default: hex2seg = 7'b0000000;
      endcase
    end
  endfunction

  assign seg1_o = hex2seg(digit_q[7:4]);
  assign seg2_o = hex2seg(digit_q[3:0]);

  // Registered read data
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) rdata_o <= 32'b0;
    else if (access & ~we_i) begin
      case (off)
        6'd2: rdata_o <= {28'b0, btn_sync_q}; // Buttons (sincronizados)
        6'd3: rdata_o <= cycle_q;             // [PROYECTO 2] Contador de ciclos
        default: rdata_o <= 32'b0;
      endcase
    end
  end

endmodule