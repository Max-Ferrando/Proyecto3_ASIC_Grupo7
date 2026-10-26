#!/usr/bin/env python3
"""
rvasm.py - Assembler RV32E minimo para el Espino Core (Pochoco SoC).

Uso:
    python3 tools/rvasm.py sw/game.s -o sw/game.hex [-l sw/game.lst] [-D NOMBRE=valor ...]

Salida: una palabra de 32 bits en hexadecimal (8 digitos) por linea,
compatible con $readmemh. No invoca ningun assembler externo.

Funciona en dos pasadas:
  1) recorre el fuente, registra etiquetas y constantes (.equ) y calcula
     la direccion de cada instruccion (cada pseudo-instruccion sabe cuantas
     palabras ocupa);
  2) codifica cada instruccion con todas las etiquetas ya conocidas.
"""

import argparse
import ast
import operator
import re
import sys

# ---------------------------------------------------------------------------
# Registros (RV32E: solo x0..x15)
# ---------------------------------------------------------------------------
ABI = {
    "zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
    "t0": 5, "t1": 6, "t2": 7, "s0": 8, "fp": 8, "s1": 9,
    "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15,
}
RV32I_ONLY = {"a6", "a7", "t3", "t4", "t5", "t6"} | {f"s{i}" for i in range(2, 12)}

# ---------------------------------------------------------------------------
# Tablas de codificacion
# ---------------------------------------------------------------------------
R_TYPE = {  # nombre: (funct7, funct3)
    "add": (0x00, 0), "sub": (0x20, 0), "sll": (0x00, 1), "slt": (0x00, 2),
    "sltu": (0x00, 3), "xor": (0x00, 4), "srl": (0x00, 5), "sra": (0x20, 5),
    "or": (0x00, 6), "and": (0x00, 7),
}
I_ALU = {"addi": 0, "slti": 2, "sltiu": 3, "xori": 4, "ori": 6, "andi": 7}
I_SHIFT = {"slli": (0x00, 1), "srli": (0x00, 5), "srai": (0x20, 5)}
LOADS = {"lb": 0, "lh": 1, "lw": 2, "lbu": 4, "lhu": 5}
STORES = {"sb": 0, "sh": 1, "sw": 2}
BRANCHES = {"beq": 0, "bne": 1, "blt": 4, "bge": 5, "bltu": 6, "bgeu": 7}
SHIFT_OPS = {"sll", "srl", "sra", "slli", "srli", "srai"}

OP_LUI, OP_AUIPC, OP_JAL, OP_JALR = 0x37, 0x17, 0x6F, 0x67
OP_BRANCH, OP_LOAD, OP_STORE, OP_OPIMM, OP_OP = 0x63, 0x03, 0x23, 0x13, 0x33


class AsmError(Exception):
    pass


# ---------------------------------------------------------------------------
# Evaluador seguro de expresiones: enteros, simbolos y + - * / % & | ^ ~ << >>
# ---------------------------------------------------------------------------
_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv, ast.Div: operator.floordiv,
    ast.Mod: operator.mod, ast.BitAnd: operator.and_, ast.BitOr: operator.or_,
    ast.BitXor: operator.xor, ast.LShift: operator.lshift, ast.RShift: operator.rshift,
}
_UNOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert}


def hi20(v):
    """Parte alta para lui, compensando el signo de la parte baja de addi."""
    return ((v + 0x800) >> 12) & 0xFFFFF


def lo12(v):
    """Parte baja con signo (-2048..2047) para addi."""
    v &= 0xFFF
    return v - 0x1000 if v & 0x800 else v


def evaluate(expr, symbols):
    """Evalua una expresion. Lanza KeyError si usa un simbolo desconocido."""
    text = expr.strip()
    text = re.sub(r"%hi\(", "_hi(", text)
    text = re.sub(r"%lo\(", "_lo(", text)
    text = text.replace("/", "//").replace("////", "//")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise AsmError(f"expresion invalida: '{expr}'")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in symbols:
                raise KeyError(node.id)
            return symbols[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
            return _UNOPS[type(node.op)](ev(node.operand))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("_hi", "_lo") and len(node.args) == 1):
            v = ev(node.args[0])
            return hi20(v) if node.func.id == "_hi" else lo12(v)
        raise AsmError(f"expresion no soportada: '{expr}'")

    return ev(tree)


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------
class Assembler:
    def __init__(self, defines=None, max_words=None):
        self.defines = dict(defines or {})   # -D en linea de comandos: tienen prioridad
        self.max_words = max_words
        self.symbols = {}
        self.labels = set()
        self.warnings = []

    # ---- utilidades -------------------------------------------------------
    def reg(self, tok):
        t = tok.strip().lower()
        if t in ABI:
            return ABI[t]
        m = re.fullmatch(r"x(\d+)", t)
        if m:
            n = int(m.group(1))
            if n <= 15:
                return n
            raise AsmError(f"registro '{tok}' no existe en RV32E (solo x0..x15)")
        if t in RV32I_ONLY:
            raise AsmError(f"registro '{tok}' no existe en RV32E (solo x0..x15)")
        raise AsmError(f"registro invalido: '{tok}'")

    def val(self, expr):
        try:
            return evaluate(expr, self.symbols)
        except KeyError as e:
            raise AsmError(f"simbolo no definido: '{e.args[0]}'")

    @staticmethod
    def check_range(v, bits, signed, what):
        lo = -(1 << (bits - 1)) if signed else 0
        hi = (1 << (bits - 1)) - 1 if signed else (1 << bits) - 1
        if not lo <= v <= hi:
            raise AsmError(f"{what} fuera de rango: {v} (permitido {lo}..{hi})")

    @staticmethod
    def split_operands(s):
        return [p.strip() for p in s.split(",")] if s.strip() else []

    def mem_operand(self, tok):
        m = re.fullmatch(r"(.*)\(\s*([A-Za-z0-9]+)\s*\)", tok.strip())
        if not m:
            raise AsmError(f"operando de memoria invalido: '{tok}' (se espera offset(reg))")
        off = m.group(1).strip() or "0"
        return self.val(off), self.reg(m.group(2))

    # ---- codificadores por formato ---------------------------------------
    @staticmethod
    def enc_r(f7, rs2, rs1, f3, rd, op):
        return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

    def enc_i(self, imm, rs1, f3, rd, op):
        self.check_range(imm, 12, True, "inmediato de 12 bits")
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

    def enc_s(self, imm, rs2, rs1, f3, op):
        self.check_range(imm, 12, True, "offset de store")
        imm &= 0xFFF
        return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op

    def enc_b(self, off, rs2, rs1, f3):
        if off % 2:
            raise AsmError(f"destino de branch desalineado (offset {off})")
        self.check_range(off, 13, True, "salto condicional (offset en bytes)")
        o = off & 0x1FFF
        return (((o >> 12) & 1) << 31) | (((o >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) \
            | (f3 << 12) | (((o >> 1) & 0xF) << 8) | (((o >> 11) & 1) << 7) | OP_BRANCH

    def enc_u(self, imm20, rd, op):
        self.check_range(imm20, 20, False, "inmediato de 20 bits (lui/auipc)")
        return (imm20 << 12) | (rd << 7) | op

    def enc_j(self, off, rd):
        if off % 2:
            raise AsmError(f"destino de jal desalineado (offset {off})")
        self.check_range(off, 21, True, "salto jal (offset en bytes)")
        o = off & 0x1FFFFF
        return (((o >> 20) & 1) << 31) | (((o >> 1) & 0x3FF) << 21) | (((o >> 11) & 1) << 20) \
            | (((o >> 12) & 0xFF) << 12) | (rd << 7) | OP_JAL

    # ---- tamano (pasada 1) -------------------------------------------------
    def size_of(self, mn, ops):
        """Cantidad de palabras que ocupa una instruccion/pseudo-instruccion."""
        if mn == "li":
            if len(ops) != 2:
                raise AsmError("li espera: li rd, valor")
            try:
                v = evaluate(ops[1], self.symbols)
            except KeyError:
                return 2          # simbolo aun desconocido: se reserva el caso largo
            v = self.to_signed32(v)
            if -2048 <= v <= 2047 or lo12(v) == 0:
                return 1          # cabe en addi, o basta con lui (12 bits bajos = 0)
            return 2
        if mn == "la":
            return 2
        return 1

    @staticmethod
    def to_signed32(v):
        if not -(1 << 31) <= v <= (1 << 32) - 1:
            raise AsmError(f"valor no cabe en 32 bits: {v}")
        v &= 0xFFFFFFFF
        return v - (1 << 32) if v & 0x80000000 else v

    # ---- codificacion (pasada 2) ------------------------------------------
    def encode(self, mn, ops, pc, size):
        def need(n, fmt):
            if len(ops) != n:
                raise AsmError(f"'{mn}' espera {n} operandos: {mn} {fmt}")

        def target(expr):
            return self.val(expr) - pc

        if mn in SHIFT_OPS:
            self.warnings.append(
                f"'{mn}': el ALU del Espino Core original ejecuta los shifts como ADD")

        # -- instrucciones base --
        if mn in R_TYPE:
            need(3, "rd, rs1, rs2")
            f7, f3 = R_TYPE[mn]
            return [self.enc_r(f7, self.reg(ops[2]), self.reg(ops[1]), f3, self.reg(ops[0]), OP_OP)]
        if mn in I_ALU:
            need(3, "rd, rs1, imm")
            return [self.enc_i(self.val(ops[2]), self.reg(ops[1]), I_ALU[mn], self.reg(ops[0]), OP_OPIMM)]
        if mn in I_SHIFT:
            need(3, "rd, rs1, shamt")
            f7, f3 = I_SHIFT[mn]
            sh = self.val(ops[2])
            self.check_range(sh, 5, False, "shamt")
            return [(f7 << 25) | (sh << 20) | (self.reg(ops[1]) << 15) | (f3 << 12)
                    | (self.reg(ops[0]) << 7) | OP_OPIMM]
        if mn in LOADS:
            need(2, "rd, offset(rs1)")
            off, rs1 = self.mem_operand(ops[1])
            return [self.enc_i(off, rs1, LOADS[mn], self.reg(ops[0]), OP_LOAD)]
        if mn in STORES:
            need(2, "rs2, offset(rs1)")
            off, rs1 = self.mem_operand(ops[1])
            return [self.enc_s(off, self.reg(ops[0]), rs1, STORES[mn], OP_STORE)]
        if mn in BRANCHES:
            need(3, "rs1, rs2, etiqueta")
            return [self.enc_b(target(ops[2]), self.reg(ops[1]), self.reg(ops[0]), BRANCHES[mn])]
        if mn in ("lui", "auipc"):
            need(2, "rd, imm20")
            return [self.enc_u(self.val(ops[1]), self.reg(ops[0]), OP_LUI if mn == "lui" else OP_AUIPC)]
        if mn == "jal":
            if len(ops) == 1:                       # jal etiqueta  ->  jal ra, etiqueta
                return [self.enc_j(target(ops[0]), 1)]
            need(2, "rd, etiqueta")
            return [self.enc_j(target(ops[1]), self.reg(ops[0]))]
        if mn == "jalr":
            if len(ops) == 1:                       # jalr rs  ->  jalr ra, 0(rs)
                return [self.enc_i(0, self.reg(ops[0]), 0, 1, OP_JALR)]
            if len(ops) == 2:                       # jalr rd, off(rs1)
                off, rs1 = self.mem_operand(ops[1])
                return [self.enc_i(off, rs1, 0, self.reg(ops[0]), OP_JALR)]
            need(3, "rd, rs1, imm")
            return [self.enc_i(self.val(ops[2]), self.reg(ops[1]), 0, self.reg(ops[0]), OP_JALR)]

        # -- pseudo-instrucciones --
        if mn == "nop":
            need(0, "")
            return [self.enc_i(0, 0, 0, 0, OP_OPIMM)]
        if mn == "li":
            rd = self.reg(ops[0])
            v = self.to_signed32(self.val(ops[1]))
            if size == 1 and -2048 <= v <= 2047:
                return [self.enc_i(v, 0, 0, rd, OP_OPIMM)]        # addi rd, x0, v
            if size == 1:
                return [self.enc_u(hi20(v), rd, OP_LUI)]           # lui rd, v>>12
            words = [self.enc_u(hi20(v), rd, OP_LUI)]
            words.append(self.enc_i(lo12(v), rd, 0, rd, OP_OPIMM))
            return words
        if mn == "la":
            need(2, "rd, etiqueta")
            rd, v = self.reg(ops[0]), self.val(ops[1])
            return [self.enc_u(hi20(v), rd, OP_LUI), self.enc_i(lo12(v), rd, 0, rd, OP_OPIMM)]
        if mn == "mv":
            need(2, "rd, rs")
            return [self.enc_i(0, self.reg(ops[1]), 0, self.reg(ops[0]), OP_OPIMM)]
        if mn == "not":
            need(2, "rd, rs")
            return [self.enc_i(-1, self.reg(ops[1]), 4, self.reg(ops[0]), OP_OPIMM)]
        if mn == "neg":
            need(2, "rd, rs")
            return [self.enc_r(0x20, self.reg(ops[1]), 0, 0, self.reg(ops[0]), OP_OP)]
        if mn == "seqz":
            need(2, "rd, rs")
            return [self.enc_i(1, self.reg(ops[1]), 3, self.reg(ops[0]), OP_OPIMM)]
        if mn == "snez":
            need(2, "rd, rs")
            return [self.enc_r(0, self.reg(ops[1]), 0, 3, self.reg(ops[0]), OP_OP)]
        if mn == "j":
            need(1, "etiqueta")
            return [self.enc_j(target(ops[0]), 0)]
        if mn == "call":
            need(1, "etiqueta")
            return [self.enc_j(target(ops[0]), 1)]
        if mn == "jr":
            need(1, "rs")
            return [self.enc_i(0, self.reg(ops[0]), 0, 0, OP_JALR)]
        if mn == "ret":
            need(0, "")
            return [self.enc_i(0, 1, 0, 0, OP_JALR)]
        zero_br = {"beqz": ("beq", False), "bnez": ("bne", False), "bltz": ("blt", False),
                   "bgez": ("bge", False), "blez": ("bge", True), "bgtz": ("blt", True)}
        if mn in zero_br:
            need(2, "rs, etiqueta")
            base, swap = zero_br[mn]
            rs = self.reg(ops[0])
            rs1, rs2 = (0, rs) if swap else (rs, 0)
            return [self.enc_b(target(ops[1]), rs2, rs1, BRANCHES[base])]
        swap_br = {"bgt": "blt", "ble": "bge", "bgtu": "bltu", "bleu": "bgeu"}
        if mn in swap_br:
            need(3, "rs1, rs2, etiqueta")
            return [self.enc_b(target(ops[2]), self.reg(ops[0]), self.reg(ops[1]), BRANCHES[swap_br[mn]])]

        raise AsmError(f"instruccion desconocida: '{mn}'")

    # ---- lectura del fuente ------------------------------------------------
    @staticmethod
    def strip_comment(line):
        for mark in ("#", ";", "//"):
            i = line.find(mark)
            if i >= 0:
                line = line[:i]
        return line.strip()

    def parse(self, source):
        """Devuelve lista de (nro_linea, texto, etiquetas, mnemonico, operandos)."""
        items = []
        for n, raw in enumerate(source.splitlines(), 1):
            line = self.strip_comment(raw)
            labels = []
            while True:
                m = re.match(r"([A-Za-z_.$][\w.$]*)\s*:(.*)", line)
                if not m:
                    break
                labels.append(m.group(1))
                line = m.group(2).strip()
            mn, ops = None, []
            if line:
                parts = line.split(None, 1)
                mn = parts[0].lower()
                ops = self.split_operands(parts[1]) if len(parts) > 1 else []
            items.append((n, raw.rstrip(), labels, mn, ops))
        return items

    def define_label(self, name, pc, n):
        if name in self.symbols:
            raise AsmError(f"etiqueta/simbolo duplicado: '{name}'")
        if name.lower() in ABI or re.fullmatch(r"x\d+", name.lower()):
            raise AsmError(f"'{name}' es un nombre de registro, no puede ser etiqueta")
        self.symbols[name] = pc
        self.labels.add(name)

    def directive(self, mn, ops, pass_no):
        """Procesa directivas. Retorna palabras a emitir (solo .word)."""
        if mn in (".equ", ".set"):
            if len(ops) != 2:
                raise AsmError(f"{mn} espera: {mn} NOMBRE, expresion")
            name = ops[0]
            if not re.fullmatch(r"[A-Za-z_][\w]*", name):
                raise AsmError(f"nombre de constante invalido: '{name}'")
            if name in self.defines:            # -D en la linea de comandos gana
                self.symbols[name] = self.defines[name]
            else:
                if pass_no == 1 and name in self.symbols:
                    raise AsmError(f"constante duplicada: '{name}'")
                self.symbols[name] = self.val(ops[1])
            return []
        if mn == ".word":
            if not ops:
                raise AsmError(".word necesita al menos un valor")
            if pass_no == 1:
                return [0] * len(ops)
            out = []
            for o in ops:
                v = self.val(o)
                self.check_range(v, 32, False, ".word") if v >= 0 else self.check_range(v, 32, True, ".word")
                out.append(v & 0xFFFFFFFF)
            return out
        if mn in (".text", ".section", ".global", ".globl", ".data", ".align", ".p2align"):
            return []                            # aceptadas e ignoradas (todo va en RAM desde 0x0)
        raise AsmError(f"directiva desconocida: '{mn}'")

    def assemble(self, source, filename="<fuente>"):
        items = self.parse(source)
        errors = []

        # ------------------ pasada 1: direcciones y simbolos -----------------
        self.symbols = dict(self.defines)
        sizes = {}
        pc = 0
        for n, raw, labels, mn, ops in items:
            try:
                for lb in labels:
                    self.define_label(lb, pc, n)
                if mn is None:
                    continue
                if mn.startswith("."):
                    pc += 4 * len(self.directive(mn, ops, 1))
                else:
                    sizes[n] = self.size_of(mn, ops)
                    pc += 4 * sizes[n]
            except AsmError as e:
                errors.append(f"{filename}:{n}: error: {e}\n    {raw.strip()}")
        if errors:
            raise AsmError("\n".join(errors))

        # ------------------ pasada 2: codificacion ---------------------------
        words, listing = [], []
        pc = 0
        for n, raw, labels, mn, ops in items:
            if mn is None:
                listing.append((None, [], raw))
                continue
            try:
                if mn.startswith("."):
                    w = self.directive(mn, ops, 2)
                else:
                    w = self.encode(mn, ops, pc, sizes[n])
                    if len(w) != sizes[n]:
                        raise AsmError("error interno: tamano distinto entre pasadas")
            except AsmError as e:
                errors.append(f"{filename}:{n}: error: {e}\n    {raw.strip()}")
                w = [0] * (sizes.get(n, 0))
            listing.append((pc if w else None, w, raw))
            words.extend(w)
            pc += 4 * len(w)
        if errors:
            raise AsmError("\n".join(errors))
        if self.max_words is not None and len(words) > self.max_words:
            raise AsmError(f"el programa ocupa {len(words)} palabras y la RAM tiene {self.max_words}")
        return words, listing


def format_listing(listing):
    out = []
    for addr, words, raw in listing:
        if addr is None:
            out.append(f"{'':8}  {'':8}  {raw}")
            continue
        for i, w in enumerate(words):
            src = raw if i == 0 else ""
            out.append(f"{addr + 4 * i:08x}  {w:08x}  {src}")
    return "\n".join(out) + "\n"



# ---------------------------------------------------------------------------
# [PROYECTO 3] Generacion de memoria para ASIC y analisis de uso
# ---------------------------------------------------------------------------
WRITES_RD = (set(R_TYPE) | set(I_ALU) | set(I_SHIFT) | set(LOADS)
             | {"lui", "auipc", "li", "la", "mv", "not", "neg", "seqz", "snez"})


def analyze_memory(asm, source):
    """Analisis estatico de los accesos a memoria de datos.

    Para cada lw/sw obtiene el registro base. Si ese registro solo recibe
    un valor constante en todo el programa (un unico li/lui), se conoce la
    direccion exacta y se clasifica como periferico (>= 0x8000_0000) o RAM.
    Retorna un dict con el resumen.
    """
    items = asm.parse(source)
    writes = {}                       # reg -> lista de (mnemonico, operandos)
    accesses = []                     # (linea, mnemonico, base, offset)
    for n, raw, labels, mn, ops in items:
        if mn is None or mn.startswith("."):
            continue
        if mn in WRITES_RD and ops:
            writes.setdefault(asm.reg(ops[0]), []).append((mn, ops))
        if mn in ("jal", "jalr", "call"):
            rd = 1 if (mn == "call" or len(ops) == 1) else asm.reg(ops[0])
            writes.setdefault(rd, []).append((mn, ops))
        if mn in LOADS or mn in STORES:
            off, base = asm.mem_operand(ops[1])
            accesses.append((n, mn, base, off))

    def const_value(r):
        if r == 0:
            return 0
        ws = writes.get(r, [])
        vals = set()
        for mn, ops in ws:
            if mn == "li":
                vals.add(asm.to_signed32(asm.val(ops[1])) & 0xFFFFFFFF)
            elif mn == "lui":
                vals.add((asm.val(ops[1]) << 12) & 0xFFFFFFFF)
            else:
                return None
        return vals.pop() if len(vals) == 1 else None

    periph, ram_words, unknown = 0, set(), 0
    for n, mn, base, off in accesses:
        b = const_value(base)
        if b is None:
            unknown += 1
            continue
        addr = (b + off) & 0xFFFFFFFF
        if addr & 0x80000000:
            periph += 1
        else:
            ram_words.add(addr >> 2)
    return {"accesses": len(accesses), "periph": periph,
            "ram_words": sorted(ram_words), "unknown": unknown}


def write_mem_vh(path, words, data_words, src_name, defines):
    n = len(words)
    init = "".join(f"{w:08x}" for w in reversed(words))   # palabra 0 al final
    with open(path, "w") as f:
        f.write(f"// GENERADO por tools/rvasm.py a partir de {src_name}. NO EDITAR.\n")
        if defines:
            f.write("// Constantes redefinidas: "
                    + ", ".join(f"{k}={v}" for k, v in defines.items()) + "\n")
        f.write(f"// Programa: {n} palabras. Datos reservados: {data_words} palabras.\n")
        f.write(f"`define GAME_INSTR_WORDS {n}\n")
        f.write(f"`define GAME_DATA_WORDS {data_words}\n")
        f.write(f"// Contenido inicial (palabra 0 en los bits 31:0)\n")
        f.write(f"`define GAME_INIT {32 * n}'h{init}\n")


def write_rom_v(path, words, rom_words, src_name, listing, defines):
    aw = max(1, (rom_words - 1).bit_length())
    src_of = {}
    for addr, ws, raw in listing:
        if addr is not None and ws:
            src_of[addr // 4] = raw.split("#")[0].strip()
    with open(path, "w") as f:
        f.write(f"// GENERADO por tools/rvasm.py a partir de {src_name}. NO EDITAR.\n")
        if defines:
            f.write("// Constantes redefinidas: "
                    + ", ".join(f"{k}={v}" for k, v in defines.items()) + "\n")
        f.write(f"// ROM combinacional: {len(words)} de {rom_words} palabras usadas.\n")
        f.write("// Las direcciones sin programa devuelven 0 (instruccion ilegal).\n")
        f.write("module pochoco_game_rom (\n")
        f.write(f"  input  wire [{aw - 1}:0] addr_i,   // direccion de palabra\n")
        f.write("  output reg  [31:0] data_o\n);\n")
        f.write("  always @* begin\n    case (addr_i)\n")
        for i, w in enumerate(words):
            note = src_of.get(i, "")
            f.write(f"      {aw}'d{i}: data_o = 32'h{w:08x};"
                    + (f"  // {note}" if note else "") + "\n")
        f.write("      default: data_o = 32'h00000000;\n")
        f.write("    endcase\n  end\nendmodule\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Assembler RV32E para el Espino Core")
    ap.add_argument("input", help="archivo .s")
    ap.add_argument("-o", "--output", help="archivo .hex de salida (por defecto: mismo nombre .hex)")
    ap.add_argument("-l", "--listing", help="genera un listado direccion / codigo / fuente")
    ap.add_argument("-D", action="append", default=[], metavar="NOMBRE=valor",
                    help="redefine una constante .equ (tiene prioridad sobre el fuente)")
    ap.add_argument("--words", type=int, default=512, help="tamano de la RAM en palabras (default 512)")
    ap.add_argument("--rom-v", metavar="ARCHIVO.v",
                    help="[ASIC] genera la ROM combinacional pochoco_game_rom en Verilog")
    ap.add_argument("--mem-vh", metavar="ARCHIVO.vh",
                    help="[ASIC] genera el include con tamanos y contenido inicial de la memoria")
    ap.add_argument("--rom-words", type=int, default=256,
                    help="[ASIC] capacidad de la ROM de instrucciones (default 256)")
    ap.add_argument("--data-words", type=int, default=8,
                    help="[ASIC] palabras de RAM de datos a reservar (default 8)")
    ap.add_argument("--report", action="store_true",
                    help="muestra cuantas palabras de instrucciones y datos usa el programa")
    args = ap.parse_args(argv)

    defines = {}
    for d in args.D:
        if "=" not in d:
            ap.error(f"-D espera NOMBRE=valor, recibio '{d}'")
        k, v = d.split("=", 1)
        defines[k.strip()] = int(v, 0)

    with open(args.input, encoding="utf-8") as f:
        src = f.read()
    asm = Assembler(defines, args.words)
    try:
        words, listing = asm.assemble(src, args.input)
    except AsmError as e:
        print(e, file=sys.stderr)
        return 1
    for w in sorted(set(asm.warnings)):
        print(f"{args.input}: aviso: {w}", file=sys.stderr)

    out = args.output or re.sub(r"\.s$", "", args.input) + ".hex"
    with open(out, "w") as f:
        f.write("".join(f"{w:08x}\n" for w in words))
    if args.listing:
        with open(args.listing, "w") as f:
            f.write(format_listing(listing))
    print(f"{args.input} -> {out}: {len(words)} palabras ({4 * len(words)} bytes)")

    if args.rom_v or args.mem_vh:
        if len(words) > args.rom_words:
            print(f"error: el programa ocupa {len(words)} palabras y la ROM tiene "
                  f"{args.rom_words}", file=sys.stderr)
            return 1
        if args.data_words > 64:
            print(f"aviso: {args.data_words} palabras de datos supera el maximo "
                  "recomendado (64)", file=sys.stderr)
    if args.rom_v:
        write_rom_v(args.rom_v, words, args.rom_words, args.input, listing, defines)
        print(f"  ROM  -> {args.rom_v} ({len(words)}/{args.rom_words} palabras)")
    if args.mem_vh:
        write_mem_vh(args.mem_vh, words, args.data_words, args.input, defines)
        print(f"  init -> {args.mem_vh} ({len(words)} + {args.data_words} palabras)")
    if args.report:
        r = analyze_memory(asm, src)
        print("Uso de memoria (analisis estatico):")
        print(f"  instrucciones : {len(words)} palabras ({4 * len(words)} bytes)")
        print(f"  accesos lw/sw : {r['accesses']} (a perifericos: {r['periph']}, "
              f"base desconocida: {r['unknown']})")
        print(f"  palabras de RAM de datos accedidas: {len(r['ram_words'])}"
              + (f" -> {r['ram_words']}" if r['ram_words'] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
