// pochoco_cycle_counter.v - [PROYECTO 2/3] Contador de ciclos libre de 32 bits.
//
// En el Proyecto 2 era un registro dentro de pochoco_periph. En el Proyecto 3
// se separo en su propio modulo (instancia u_cycle_cnt) para poder medir su
// area en el reporte jerarquico de sintesis y ubicar sus celdas en el layout.
// Suma 1 en cada flanco de reloj. El software solo usa diferencias sin signo
// (fin - inicio), que siguen siendo correctas aunque el contador de la vuelta.
module pochoco_cycle_counter (
  input  wire        clk_i,
  input  wire        rst_ni,
  output reg  [31:0] count_o
);
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) count_o <= 32'b0;
    else         count_o <= count_o + 32'd1;
  end
endmodule
