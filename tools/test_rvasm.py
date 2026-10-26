#!/usr/bin/env python3
"""Pruebas del assembler rvasm.py.  Correr:  python3 tools/test_rvasm.py

1) Ensambla los ejemplos del repo (blink, 7seg, buttons_leds) y compara con
   los .hex oficiales, que fueron generados con el toolchain GNU de RISC-V.
2) Compara codificaciones individuales con valores de referencia
   (verificados con el desensamblador de la especificacion RISC-V).
3) Verifica etiquetas hacia adelante/atras, pseudo-instrucciones y -D.
4) Verifica que los errores se detecten con el numero de linea correcto.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from rvasm import Assembler, AsmError, write_rom_v, write_mem_vh, analyze_memory  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402


def asm(src, **kw):
    return Assembler(**kw).assemble(src)[0]


class TestReferencia(unittest.TestCase):
    def test_ejemplos_del_repo(self):
        for name in ("blink", "7seg", "buttons_leds"):
            with open(os.path.join(ROOT, "sw", f"{name}.s")) as f:
                words = asm(f.read())
            with open(os.path.join(ROOT, "sw", f"{name}.hex")) as f:
                ref = [int(l, 16) for l in f if l.strip()]
            self.assertEqual(words, ref, f"{name}.s no coincide con {name}.hex")


class TestCodificacion(unittest.TestCase):
    CASOS = {
        # instruccion                 codigo esperado
        "add x1, x2, x3":             0x003100B3,
        "sub x1, x2, x3":             0x403100B3,
        "and a0, a1, a2":             0x00C5F533,
        "or  a0, a1, a2":             0x00C5E533,
        "xor a0, a1, a2":             0x00C5C533,
        "slt t0, t1, t2":             0x007322B3,
        "sltu t0, t1, t2":            0x007332B3,
        "addi a0, a0, -1":            0xFFF50513,
        "andi t0, t1, 15":            0x00F37293,
        "xori x1, x1, 15":            0x00F0C093,
        "slti a0, a1, 5":             0x0055A513,
        "lui x2, 0x80000":            0x80000137,
        "auipc t0, 1":                0x00001297,
        "lw x1, 12(x2)":              0x00C12083,
        "lbu a0, 3(s0)":              0x00344503,
        "sw x1, -4(x2)":              0xFE112E23,
        "sb a0, 1(s0)":               0x00A400A3,
        "jalr x0, 0(x1)":             0x00008067,
        "ret":                        0x00008067,
        "nop":                        0x00000013,
        "mv a0, a1":                  0x00058513,
        "not t0, t1":                 0xFFF34293,
        "neg a0, a1":                 0x40B00533,
        "slli a0, a0, 4":             0x00451513,
        "srai a0, a0, 3":             0x40355513,
    }

    def test_casos(self):
        for src, ref in self.CASOS.items():
            with self.subTest(src=src):
                self.assertEqual(asm(src), [ref])


class TestEtiquetasYPseudo(unittest.TestCase):
    def test_branch_adelante_y_atras(self):
        w = asm("top:\n beq x1, x2, fin\n nop\nfin:\n bne x0, x0, top\n")
        self.assertEqual(w[0], 0x00208463)     # beq x1,x2,+8
        self.assertEqual(w[2], 0xFE001CE3)     # bne x0,x0,-8

    def test_jal_y_j(self):
        w = asm("a:\n j b\n nop\nb:\n jal ra, a\n")
        self.assertEqual(w[0], 0x0080006F)     # jal x0,+8
        self.assertEqual(w[2], 0xFF9FF0EF)     # jal ra,-8

    def test_li_corto_y_largo(self):
        self.assertEqual(asm("li a0, 100"), [0x06400513])
        self.assertEqual(asm("li s0, 0x80000000"), [0x80000437])           # solo lui
        # 0x12345FFF: la parte baja es negativa, lui debe compensar (+1)
        self.assertEqual(asm("li a0, 0x12345FFF"), [0x12346537, 0xFFF50513])
        self.assertEqual(asm("li a0, -1"), [0xFFF00513])

    def test_equ_expresiones_y_define(self):
        src = ".equ CLK, 25000000\n.equ T, CLK/10\nli a0, T*3\n"
        w1 = asm(src)
        self.assertEqual(w1, asm("li a0, 7500000"))
        w2 = asm(src, defines={"CLK": 20000})        # -D CLK=20000 tiene prioridad
        self.assertEqual(w2, asm("li a0, 6000"))

    def test_etiqueta_y_instruccion_misma_linea(self):
        self.assertEqual(asm("x: nop # comentario"), [0x00000013])

    def test_word(self):
        self.assertEqual(asm(".word 0xDEADBEEF, 5"), [0xDEADBEEF, 5])


class TestErrores(unittest.TestCase):
    def falla(self, src, texto, linea=None):
        with self.assertRaises(AsmError) as cm:
            asm(src)
        msg = str(cm.exception)
        self.assertIn(texto, msg)
        if linea:
            self.assertIn(f":{linea}:", msg)

    def test_registro_rv32e(self):
        self.falla("add x16, x1, x2", "RV32E", 1)
        self.falla("nop\nadd s2, a0, a1", "RV32E", 2)

    def test_inmediato_fuera_de_rango(self):
        self.falla("addi a0, a0, 2048", "fuera de rango")
        self.falla("lui a0, 0x100000", "fuera de rango")

    def test_etiqueta_indefinida_y_duplicada(self):
        self.falla("beq x0, x0, nada", "no definido")
        self.falla("a:\na:\n nop", "duplicad")

    def test_mnemonico_y_operandos(self):
        self.falla("foo a0, a1", "desconocida")
        self.falla("add a0, a1", "espera 3")
        self.falla("lw a0, a1", "offset(reg)")

    def test_branch_fuera_de_alcance(self):
        src = "b:\n" + "nop\n" * 1100 + "beq x0, x0, b\n"
        self.falla(src, "fuera de rango")

    def test_tamano_ram(self):
        with self.assertRaises(AsmError):
            Assembler(max_words=2).assemble("nop\nnop\nnop\n")


class TestGeneracionASIC(unittest.TestCase):
    """[Proyecto 3] ROM en Verilog e init de la memoria FF."""
    SRC = "li s0, 0x80000000\nli a0, 5\nsw a0, 4(s0)\nloop: j loop\n"

    def setUp(self):
        self.asm = Assembler()
        self.words, self.listing = self.asm.assemble(self.SRC)

    def test_rom_contiene_cada_palabra(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rom.v")
            write_rom_v(p, self.words, 256, "t.s", self.listing, {})
            txt = open(p).read()
        rom = {int(a): int(w, 16) for a, w in re.findall(r"8'd(\d+): data_o = 32'h([0-9a-f]{8})", txt)}
        self.assertEqual([rom[i] for i in range(len(self.words))], self.words)
        self.assertIn("default: data_o = 32'h00000000", txt)

    def test_init_palabra0_en_bits_bajos(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "mem.vh")
            write_mem_vh(p, self.words, 8, "t.s", {})
            txt = open(p).read()
        self.assertIn(f"`define GAME_INSTR_WORDS {len(self.words)}", txt)
        self.assertIn("`define GAME_DATA_WORDS 8", txt)
        val = int(re.search(r"GAME_INIT \d+'h([0-9a-f]+)", txt).group(1), 16)
        for i, w in enumerate(self.words):
            self.assertEqual((val >> (32 * i)) & 0xFFFFFFFF, w)

    def test_analisis_de_accesos(self):
        r = analyze_memory(self.asm, self.SRC)
        self.assertEqual(r["accesses"], 1)
        self.assertEqual(r["periph"], 1)
        self.assertEqual(r["ram_words"], [])
        r2 = analyze_memory(Assembler(), "li t0, 0x400\nsw a0, 8(t0)\nlw a1, 8(t0)\n")
        self.assertEqual(r2["ram_words"], [0x102])


if __name__ == "__main__":
    unittest.main(verbosity=2)
