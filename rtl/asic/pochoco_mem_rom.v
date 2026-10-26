// pochoco_mem_rom.v - [PROYECTO 3] Estrategia A de memoria para ASIC:
//   ROM combinacional de instrucciones (generada por el assembler)
//   + RAM de datos reducida implementada con flip-flops.
//
// Arquitectura Harvard: el puerto A (instrucciones) lee la ROM y el puerto B
// (datos) lee/escribe solo la RAM de datos.
//
//   0x0000_0000 .. 0x0000_03FF  ROM  (hasta 256 palabras, puerto A)
//   0x0000_0400 .. 0x0000_04FF  RAM  (GAME_DATA_WORDS palabras, puerto B)
//
// La ROM es solo logica combinacional (un case por direccion): no tiene
// flip-flops. Cada bit de cada palabra es una constante, y la sintesis la
// reduce a compuertas. Lo que si se registra es la SALIDA del puerto A,
// porque el core espera el dato un ciclo despues de la direccion (igual que
// la BRAM de la FPGA). Asi el comportamiento ciclo a ciclo no cambia.
//
// Limitacion (documentada): el puerto de datos no puede leer la ROM (no hay
// constantes .word leidas con lw). game.s no lo necesita.
`include "game_mem.vh"   // generado por: rvasm.py --mem-vh

module pochoco_mem (
  input  wire        clk_i,
  input  wire        rst_ni,

  // Puerto A: instrucciones
  input  wire        a_req_i,
  input  wire [31:0] a_addr_i,
  output reg  [31:0] a_rdata_o,

  // Puerto B: datos
  input  wire        b_req_i,
  input  wire        b_we_i,
  input  wire [3:0]  b_be_i,
  input  wire [31:0] b_addr_i,
  input  wire [31:0] b_wdata_i,
  output reg  [31:0] b_rdata_o
);

  localparam DataWords = `GAME_DATA_WORDS;
  localparam DataBase  = 32'h0000_0400;
  localparam DAW       = (DataWords > 1) ? $clog2(DataWords) : 1;

  // ---------------- Instrucciones: ROM combinacional -----------------------
  wire [31:0] rom_data;
  pochoco_game_rom u_rom (
    .addr_i (a_addr_i[9:2]),
    .data_o (rom_data)
  );

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)      a_rdata_o <= 32'b0;
    else if (a_req_i) a_rdata_o <= rom_data;
  end

  // ---------------- Datos: RAM de flip-flops -------------------------------
  wire          in_ram = (b_addr_i[31:2] >= DataBase[31:2]) &&
                         (b_addr_i[31:2] <  DataBase[31:2] + DataWords);
  wire [DAW-1:0] b_word = b_addr_i[DAW+1:2];

  reg [31:0] ram [0:DataWords-1];

  always @(posedge clk_i) begin
    if (b_req_i && b_we_i && in_ram) begin
      if (b_be_i[0]) ram[b_word][7:0]   <= b_wdata_i[7:0];
      if (b_be_i[1]) ram[b_word][15:8]  <= b_wdata_i[15:8];
      if (b_be_i[2]) ram[b_word][23:16] <= b_wdata_i[23:16];
      if (b_be_i[3]) ram[b_word][31:24] <= b_wdata_i[31:24];
    end
  end

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)      b_rdata_o <= 32'b0;
    else if (b_req_i) b_rdata_o <= in_ram ? ram[b_word] : 32'b0;
  end

endmodule
