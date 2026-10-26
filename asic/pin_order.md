# pin_order.cfg: por que cada grupo esta en ese lado

(El formato de LibreLane no admite comentarios dentro de pin_order.cfg, por eso
la explicacion esta aqui.)

Los terminales del macro se agrupan por funcion, para que en un chip completo
cada grupo quede frente a sus pads y las rutas del pad al macro sean cortas y no
se crucen.

| Lado | Pines | Razon |
|---|---|---|
| Oeste | clk_i, rst_ni | Juntos y hacia el centro del lado (`$4` deja 4 posiciones vacias antes): desde el pin de reloj nace el arbol de reloj (CTS) que alimenta todos los flip-flops |
| Norte | btn_i[3:0] | Entradas del jugador; pasan por el sincronizador de 2 FFs |
| Sur | led_o, seg1_o, seg2_o | Salidas visibles (LEDs y displays), juntas |
| Este | spi_sclk_i, spi_mosi_i, spi_cs_n_i, spi_miso_o | Interfaz SPI completa en un mismo lado, como un bus |

`@min_distance` fija la separacion minima entre pines (um) en ese lado.
