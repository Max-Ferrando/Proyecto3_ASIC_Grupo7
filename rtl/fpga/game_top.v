// game_top.v - Top-level de FPGA (Go Board, iCE40 HX1K).
// [PROYECTO 3] Contiene todo lo que es propio de la placa:
//  * power-on reset con valor inicial (solo valido en FPGA: el bitstream
//    carga por_cnt = 0; en un ASIC un FF no tiene valor inicial definido),
//  * inversion de los segmentos (display de anodo comun de la Go Board).
// El programa se carga en la BRAM con $readmemh (rtl/fpga/pochoco_mem_bram.v).

module game_top (
  input  wire       i_Clk,            // 25 MHz en la Go Board

  output wire [3:0] o_LED,
  input  wire [3:0] i_Switch,

  output wire       o_Segment1_A, o_Segment1_B, o_Segment1_C, o_Segment1_D,
  output wire       o_Segment1_E, o_Segment1_F, o_Segment1_G,
  output wire       o_Segment2_A, o_Segment2_B, o_Segment2_C, o_Segment2_D,
  output wire       o_Segment2_E, o_Segment2_F, o_Segment2_G,

  input  wire       i_SPI_SCLK,
  input  wire       i_SPI_MOSI,
  input  wire       i_SPI_CS_n,
  output wire       o_SPI_MISO
);

  // Power-on reset (FPGA): el bitstream inicializa por_cnt en 0.
  reg  [3:0] por_cnt = 4'b0;
  always @(posedge i_Clk) begin
    if (por_cnt != 4'hF) por_cnt <= por_cnt + 4'd1;
  end
  wire rst_n = (por_cnt == 4'hF);

  wire [6:0] seg1, seg2;

  pochoco_soc u_soc (
    .clk_i      (i_Clk),
    .rst_ni     (rst_n),
    .led_o      (o_LED),
    .btn_i      (i_Switch),
    .seg1_o     (seg1),
    .seg2_o     (seg2),
    .spi_sclk_i (i_SPI_SCLK),
    .spi_mosi_i (i_SPI_MOSI),
    .spi_cs_n_i (i_SPI_CS_n),
    .spi_miso_o (o_SPI_MISO)
  );

  // Display de anodo comun: segmento activo en bajo
  assign {o_Segment1_G, o_Segment1_F, o_Segment1_E, o_Segment1_D,
          o_Segment1_C, o_Segment1_B, o_Segment1_A} = ~seg1;
  assign {o_Segment2_G, o_Segment2_F, o_Segment2_E, o_Segment2_D,
          o_Segment2_C, o_Segment2_B, o_Segment2_A} = ~seg2;

endmodule
