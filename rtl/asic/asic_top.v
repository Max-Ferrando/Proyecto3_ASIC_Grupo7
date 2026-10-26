// asic_top.v - [PROYECTO 3] Top-level del macro ASIC (GF180MCU, LibreLane).
//
// Sin elementos propios de la FPGA: no hay power-on reset con valor inicial,
// ni $readmemh, ni primitivas SB_*, ni inversion para un display especifico.
// Los puertos son terminales logicos del macro, no pads: en un chip completo
// cada uno se conectaria a una celda de I/O con proteccion ESD y driver capaz
// de manejar un LED o un display.
//
// Programa: lo fija la implementacion de pochoco_mem elegida en la lista de
// archivos (estrategia A: ROM + RAM de datos; estrategia B: memoria FF).
module asic_top (
  input  wire       clk_i,       // reloj del sistema (periodo T)
  input  wire       rst_ni,      // reset externo asincrono, activo en bajo

  output wire [3:0] led_o,       // LEDs del juego (1 = encendido)
  input  wire [3:0] btn_i,       // botones (1 = presionado), asincronos
  output wire [6:0] seg1_o,      // display izquierdo, segmentos g..a (1 = on)
  output wire [6:0] seg2_o,      // display derecho,   segmentos g..a (1 = on)

  input  wire       spi_sclk_i,
  input  wire       spi_mosi_i,
  input  wire       spi_cs_n_i,
  output wire       spi_miso_o
);

  wire rst_n_sync;

  pochoco_reset_sync u_rst_sync (
    .clk_i  (clk_i),
    .rst_ni (rst_ni),
    .rst_no (rst_n_sync)
  );

  pochoco_soc u_soc (
    .clk_i      (clk_i),
    .rst_ni     (rst_n_sync),
    .led_o      (led_o),
    .btn_i      (btn_i),
    .seg1_o     (seg1_o),
    .seg2_o     (seg2_o),
    .spi_sclk_i (spi_sclk_i),
    .spi_mosi_i (spi_mosi_i),
    .spi_cs_n_i (spi_cs_n_i),
    .spi_miso_o (spi_miso_o)
  );

endmodule
