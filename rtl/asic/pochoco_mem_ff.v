// pochoco_mem_ff.v - [PROYECTO 3] Estrategia B de memoria para ASIC:
//   memoria UNIFICADA (instrucciones + datos) implementada con flip-flops,
//   dimensionada segun el uso real del juego.
//
//   palabras 0 .. GAME_INSTR_WORDS-1             : programa
//   palabras GAME_INSTR_WORDS .. +GAME_DATA_WORDS : datos
//
// En silicio no hay un archivo que se cargue al encender, asi que el
// contenido inicial de cada palabra es el VALOR DE RESET de sus flip-flops
// (GAME_INIT, generado por el assembler). Un bit de programa en 1 se
// implementa con un FF con "set" y un bit en 0 con un FF con "reset". Al
// liberar el reset la memoria contiene el programa, y como es RAM el puerto
// de datos puede leerla y escribirla completa (Von Neumann, como en la FPGA).
//
// Ambos puertos de lectura son registrados, igual que la BRAM de la FPGA.
// Direcciones fuera de rango leen 0 y las escrituras se ignoran.
`include "game_mem.vh"   // generado por: rvasm.py --mem-vh

module pochoco_mem (
  input  wire        clk_i,
  input  wire        rst_ni,

  input  wire        a_req_i,
  input  wire [31:0] a_addr_i,
  output reg  [31:0] a_rdata_o,

  input  wire        b_req_i,
  input  wire        b_we_i,
  input  wire [3:0]  b_be_i,
  input  wire [31:0] b_addr_i,
  input  wire [31:0] b_wdata_i,
  output reg  [31:0] b_rdata_o
);

  localparam InstrWords = `GAME_INSTR_WORDS;
  localparam NumWords   = `GAME_INSTR_WORDS + `GAME_DATA_WORDS;
  localparam AW         = $clog2(NumWords);
  localparam [32*InstrWords-1:0] Init = `GAME_INIT;

  wire [29:0] a_word = a_addr_i[31:2];
  wire [29:0] b_word = b_addr_i[31:2];
  wire        a_ok   = (a_word < NumWords);
  wire        b_ok   = (b_word < NumWords);

  wire [32*NumWords-1:0] flat;

  genvar w;
  generate
    for (w = 0; w < NumWords; w = w + 1) begin : g_word
      // Valor de reset (constante): palabra del programa o 0 (zona de datos).
      // El indice se limita a InstrWords-1 para no seleccionar fuera de Init.
      localparam integer Idx = (w < InstrWords) ? w : 0;
      localparam [31:0] RstVal = (w < InstrWords) ? Init[32*Idx +: 32] : 32'b0;
      wire sel = b_req_i & b_we_i & (b_word == w);
      reg [31:0] q;
      always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) q <= RstVal;
        else if (sel) begin
          if (b_be_i[0]) q[7:0]   <= b_wdata_i[7:0];
          if (b_be_i[1]) q[15:8]  <= b_wdata_i[15:8];
          if (b_be_i[2]) q[23:16] <= b_wdata_i[23:16];
          if (b_be_i[3]) q[31:24] <= b_wdata_i[31:24];
        end
      end
      assign flat[32*w +: 32] = q;
    end
  endgenerate

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      a_rdata_o <= 32'b0;
      b_rdata_o <= 32'b0;
    end else begin
      if (a_req_i) a_rdata_o <= a_ok ? flat[32*a_word[AW-1:0] +: 32] : 32'b0;
      if (b_req_i) b_rdata_o <= b_ok ? flat[32*b_word[AW-1:0] +: 32] : 32'b0;
    end
  end

endmodule
