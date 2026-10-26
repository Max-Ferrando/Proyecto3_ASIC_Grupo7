// Copyright 2026 Universidad de los Andes.
// Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
// SPDX-License-Identifier: SHL-0.51
//
// Course: Arquitectura de Computadores (2026)
// Authors:
// - Nicolás Villegas <navillegas@miuandes.cl>
//
// [PROYECTO 3] SoC independiente de la tecnologia.
//  * El reset entra como puerto (rst_ni, ya sincronizado). El power-on reset
//    con valor inicial (reg por_cnt = 0) era propio de la FPGA y se movio a
//    rtl/fpga/game_top.v.
//  * La memoria se instancia por nombre (pochoco_mem). La implementacion la
//    elige la lista de archivos:
//      FPGA     : rtl/fpga/pochoco_mem_bram.v  (BRAM + $readmemh)
//      ASIC (A) : rtl/asic/pochoco_mem_rom.v   (ROM combinacional + RAM datos)
//      ASIC (B) : rtl/asic/pochoco_mem_ff.v    (memoria unificada con FFs)
//  * Los displays salen en logica positiva (1 = segmento encendido). La
//    inversion para el display de anodo comun de la Go Board es de la placa y
//    se hace en game_top.v.

module pochoco_soc (
  input  wire       clk_i,
  input  wire       rst_ni,

  output wire [3:0] led_o,
  input  wire [3:0] btn_i,
  output wire [6:0] seg1_o,
  output wire [6:0] seg2_o,

  input  wire       spi_sclk_i,
  input  wire       spi_mosi_i,
  input  wire       spi_cs_n_i,
  output wire       spi_miso_o
);

  // Core-memory wiring
  wire        instr_req;
  wire [31:0] instr_addr, instr_rdata;

  wire        data_req, data_we;
  wire [3:0]  data_be;
  wire [31:0] data_addr, data_wdata, data_rdata;

  espino_core #(.BootAddr(32'h0000_0000)) u_core (
    .clk_i         (clk_i),
    .rst_ni        (rst_ni),
    .instr_req_o   (instr_req),
    .instr_addr_o  (instr_addr),
    .instr_rdata_i (instr_rdata),
    .data_req_o    (data_req),
    .data_we_o     (data_we),
    .data_be_o     (data_be),
    .data_addr_o   (data_addr),
    .data_wdata_o  (data_wdata),
    .data_rdata_i  (data_rdata)
  );

  wire is_mmio, spi_sel, per_sel;
  assign is_mmio = data_addr[31];
  assign per_sel = is_mmio & ~data_addr[16];
  assign spi_sel = is_mmio &  data_addr[16];

  wire mem_b_req, per_req, spi_req;
  assign mem_b_req = data_req & ~is_mmio;
  assign per_req   = data_req &  per_sel;
  assign spi_req   = data_req &  spi_sel;

  wire [31:0] mem_b_rdata, per_rdata, spi_rdata;

  reg rd_is_per, rd_is_spi;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rd_is_per <= 1'b0;
      rd_is_spi <= 1'b0;
    end else if (data_req & ~data_we) begin
      rd_is_per <= per_sel;
      rd_is_spi <= spi_sel;
    end
  end
  assign data_rdata = rd_is_per ? per_rdata :
                      rd_is_spi ? spi_rdata : mem_b_rdata;

  pochoco_mem u_mem (
    .clk_i     (clk_i),
    .rst_ni    (rst_ni),
    .a_req_i   (instr_req),
    .a_addr_i  (instr_addr),
    .a_rdata_o (instr_rdata),
    .b_req_i   (mem_b_req),
    .b_we_i    (data_we),
    .b_be_i    (data_be),
    .b_addr_i  (data_addr),
    .b_wdata_i (data_wdata),
    .b_rdata_o (mem_b_rdata)
  );

  pochoco_periph u_periph (
    .clk_i     (clk_i),
    .rst_ni    (rst_ni),
    .sel_i     (per_sel),
    .req_i     (per_req),
    .we_i      (data_we),
    .addr_i    (data_addr[7:0]),
    .wdata_i   (data_wdata),
    .rdata_o   (per_rdata),
    .leds_o    (led_o),
    .btn_i     (btn_i),
    .seg1_o    (seg1_o),
    .seg2_o    (seg2_o)
  );

  pochoco_spi_slave u_spi (
    .clk_i      (clk_i),
    .rst_ni     (rst_ni),
    .sel_i      (spi_sel),
    .req_i      (spi_req),
    .we_i       (data_we),
    .addr_i     (data_addr[7:0]),
    .wdata_i    (data_wdata),
    .rdata_o    (spi_rdata),
    .spi_sclk_i (spi_sclk_i),
    .spi_mosi_i (spi_mosi_i),
    .spi_cs_n_i (spi_cs_n_i),
    .spi_miso_o (spi_miso_o)
  );

endmodule
