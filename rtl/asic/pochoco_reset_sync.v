// pochoco_reset_sync.v - [PROYECTO 3] Sincronizador de reset para ASIC.
//
// En la FPGA el reset lo generaba un contador con valor inicial (por_cnt = 0),
// que solo existe porque el bitstream inicializa los FFs. En silicio el reset
// llega desde afuera (pin rst_ni del macro). Se usa el esquema clasico:
// activacion asincrona (el chip entra en reset aunque no haya reloj) y
// liberacion sincrona con 2 FFs, para que todos los FFs salgan de reset en el
// mismo flanco y no haya violaciones de recovery/removal.
module pochoco_reset_sync (
  input  wire clk_i,
  input  wire rst_ni,     // reset externo, asincrono, activo en bajo
  output wire rst_no      // reset sincronizado, activo en bajo
);
  reg [1:0] sync_q;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) sync_q <= 2'b00;
    else         sync_q <= {sync_q[0], 1'b1};
  end
  assign rst_no = sync_q[1];
endmodule
