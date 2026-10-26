// espino_register_file_ff.v - [PROYECTO 3] Banco de registros para ASIC.
//
// La version de FPGA (rtl/fpga/espino_register_file_ice40.v) instanciaba la
// primitiva SB_RAM40_4K del iCE40, que no existe en la biblioteca GF180MCU.
// Ademas usaba DOS bancos (u_bankA, u_bankB) con la misma informacion para
// tener dos puertos de lectura, porque cada BRAM tiene un solo puerto de
// lectura. Con flip-flops basta UN arreglo y dos multiplexores de lectura.
//
// Se conserva exactamente el comportamiento temporal del original:
//  * lectura registrada (el dato aparece un ciclo despues de la direccion),
//    porque espino_id_stage espera ese ciclo (ops_valid_q / rf_ready);
//  * lectura y escritura en el mismo ciclo a la misma direccion devuelve el
//    valor ANTERIOR (igual que la BRAM);
//  * x0 siempre vale 0 y nunca se escribe;
//  * los registros parten en 0, como la BRAM con INIT_0 = 0. En ASIC un FF no
//    tiene valor inicial, asi que se usa el reset asincrono.
module espino_register_file (
  input  wire        clk_i,
  input  wire        rst_ni,
  input  wire [3:0]  raddr_a_i,
  output reg  [31:0] rdata_a_o,
  input  wire [3:0]  raddr_b_i,
  output reg  [31:0] rdata_b_o,
  input  wire [3:0]  waddr_i,
  input  wire [31:0] wdata_i,
  input  wire        we_i
);
  // x1..x15 (RV32E). x0 no tiene almacenamiento.
  reg [31:0] regs [1:15];

  integer i;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      for (i = 1; i < 16; i = i + 1) regs[i] <= 32'b0;
    end else if (we_i && (waddr_i != 4'd0)) begin
      regs[waddr_i] <= wdata_i;
    end
  end

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rdata_a_o <= 32'b0;
      rdata_b_o <= 32'b0;
    end else begin
      rdata_a_o <= (raddr_a_i == 4'd0) ? 32'b0 : regs[raddr_a_i];
      rdata_b_o <= (raddr_b_i == 4'd0) ? 32'b0 : regs[raddr_b_i];
    end
  end
endmodule
