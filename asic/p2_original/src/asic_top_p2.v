// Envoltorio minimo: el RTL del Proyecto 2 SIN cambios, para ver que
// construcciones de FPGA detecta el flujo ASIC.
module asic_top (
  input wire clk_i, output wire [3:0] led_o, input wire [3:0] btn_i,
  output wire [13:0] seg_o, input wire spi_sclk_i, spi_mosi_i, spi_cs_n_i,
  output wire spi_miso_o);
  pochoco_soc #(.MemFile("sw/game.hex")) u_pochoco (
    .i_Clk(clk_i), .o_LED(led_o), .i_Switch(btn_i),
    .o_Segment1_A(seg_o[0]), .o_Segment1_B(seg_o[1]), .o_Segment1_C(seg_o[2]),
    .o_Segment1_D(seg_o[3]), .o_Segment1_E(seg_o[4]), .o_Segment1_F(seg_o[5]),
    .o_Segment1_G(seg_o[6]), .o_Segment2_A(seg_o[7]), .o_Segment2_B(seg_o[8]),
    .o_Segment2_C(seg_o[9]), .o_Segment2_D(seg_o[10]), .o_Segment2_E(seg_o[11]),
    .o_Segment2_F(seg_o[12]), .o_Segment2_G(seg_o[13]),
    .i_SPI_SCLK(spi_sclk_i), .i_SPI_MOSI(spi_mosi_i), .i_SPI_CS_n(spi_cs_n_i),
    .o_SPI_MISO(spi_miso_o));
endmodule
