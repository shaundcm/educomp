"""
EduComp C Code Generator
Walks the validated AST and emits a single, self-contained C source file.
The emitted C is then compiled by gcc (or clang) into a real native executable.

Translation strategy
────────────────────
EduComp type  →  C type
  int         →  long long
  float       →  double
  bool        →  int          (0 = false, 1 = true)
  string      →  char*        (string literals only; we use a small arena for
                               concatenation results so we never leak)
  array<T>[N] →  T arr[N]

Every EduComp operator maps 1-to-1 to its C counterpart.
print(expr) maps to the correct printf format string based on expression type,
which is tracked by re-running a lightweight type-inference pass during codegen.
"""

import os
import subprocess
from typing import List, Dict, Optional, Tuple
from ast_nodes import *


# ── Type map ──────────────────────────────────────────────────────────────────

EDUCOMP_TO_C = {
    'int':    'long long',
    'float':  'double',
    'bool':   'int',
    'string': 'char*',
    'void':   'void',
}

PRINTF_FMT = {
    'int':    '%lld',
    'float':  '%g',
    'bool':   '%s',       # special-cased: print true/false string
    'string': '%s',
}

ZERO_VAL = {
    'int':    '0LL',
    'float':  '0.0',
    'bool':   '0',
    'string': '""',
}


# ── Lightweight type inferencer (used during codegen to pick printf format) ──

class TypeInferencer:
    """
    Re-infers the type of an expression node using the same symbol/function
    tables the semantic analyser already validated.  We only need this so the
    code generator can emit the correct printf format string.
    """

    def __init__(self, sym: Dict[str, Tuple[str, bool]],
                 funcs: Dict[str, Tuple[str, list]]):
        self.sym   = sym    # name → (type, is_array)
        self.funcs = funcs  # name → (return_type, params)

    def typeof(self, node: ASTNode) -> str:
        if isinstance(node, Literal):
            return node.lit_type
        if isinstance(node, Identifier):
            return self.sym.get(node.name, ('int', False))[0]
        if isinstance(node, ArrayAccess):
            return self.sym.get(node.name, ('int', False))[0]
        if isinstance(node, BinOp):
            lt = self.typeof(node.left)
            rt = self.typeof(node.right)
            if node.op in ('+', '-', '*', '/', '%'):
                if lt == 'string' or rt == 'string':
                    return 'string'
                return 'float' if 'float' in (lt, rt) else 'int'
            return 'bool'   # comparison / logical operators
        if isinstance(node, UnaryOp):
            if node.op == '!':
                return 'bool'
            return self.typeof(node.operand)
        if isinstance(node, FuncCall):
            sig = self.funcs.get(node.name)
            return sig[0] if sig else 'int'
        return 'int'


# ── Code Generator ────────────────────────────────────────────────────────────

class CCodeGenerator:
    def __init__(self):
        self.errors: List[str] = []

        # Indentation level
        self._indent = 0

        # Output lines
        self._lines: List[str] = []

        # Symbol table for type inference during codegen
        # Maps name → (educomp_type, is_array)
        self._sym: Dict[str, Tuple[str, bool]] = {}

        # Function signature table
        # Maps name → (return_type, [(param_type, param_name)])
        self._funcs: Dict[str, Tuple[str, list]] = {}

        # Counter for unique temporary variable names (string concat)
        self._tmp_counter = 0

        # Track whether we need the string helpers
        self._uses_strings = False
        self._uses_bool_print = False

    # ── Public entry point ────────────────────────────────────────────────────

    def generate(self, program: Program) -> str:
        """
        Returns a complete C source string for the given program.
        """
        # First pass: collect all function signatures
        for stmt in program.statements:
            if isinstance(stmt, FuncDecl):
                self._funcs[stmt.name] = (stmt.return_type, stmt.params)

        # Scan for string usage and bool prints so we can emit the right helpers
        self._scan_features(program)

        # Emit everything into self._lines
        self._emit_program(program)

        return '\n'.join(self._lines)

    # ── Feature scanner ───────────────────────────────────────────────────────

    def _scan_features(self, node: ASTNode):
        """Walk the AST and set flags for features that need C helper code."""
        if isinstance(node, Literal) and node.lit_type == 'string':
            self._uses_strings = True
        if isinstance(node, PrintStmt):
            # We'll always need bool print helper if any bool is printed
            self._uses_bool_print = True
        if isinstance(node, BinOp) and node.op == '+':
            # String concatenation needs strcat helper
            pass
        # Recurse into children
        for attr in vars(node).values():
            if isinstance(attr, ASTNode):
                self._scan_features(attr)
            elif isinstance(attr, list):
                for item in attr:
                    if isinstance(item, ASTNode):
                        self._scan_features(item)

    # ── Top-level emission ────────────────────────────────────────────────────

    def _emit_program(self, program: Program):
        # ── Standard headers ──────────────────────────────────────────────────
        self._w('/*')
        self._w(' * Generated by EduComp C Code Generator')
        self._w(' * Compile: gcc -o program output.c')
        self._w(' */')
        self._w('#include <stdio.h>')
        self._w('#include <stdlib.h>')
        self._w('#include <string.h>')
        self._w('')

        # ── String arena helper (for concatenation) ───────────────────────────
        # We use a simple bump-allocator arena so string temporaries don't leak.
        self._w('/* ── EduComp string arena ───────────────────────────── */')
        self._w('#define ARENA_SIZE (1 << 20)   /* 1 MB */')
        self._w('static char  _arena[ARENA_SIZE];')
        self._w('static int   _arena_pos = 0;')
        self._w('')
        self._w('static char* _arena_alloc(int n) {')
        self._w('    if (_arena_pos + n >= ARENA_SIZE) {')
        self._w('        fprintf(stderr, "EduComp: string arena exhausted\\n");')
        self._w('        exit(1);')
        self._w('    }')
        self._w('    char* p = _arena + _arena_pos;')
        self._w('    _arena_pos += n;')
        self._w('    return p;')
        self._w('}')
        self._w('')
        self._w('static char* _concat(char* a, char* b) {')
        self._w('    int la = (int)strlen(a), lb = (int)strlen(b);')
        self._w('    char* r = _arena_alloc(la + lb + 1);')
        self._w('    memcpy(r, a, la);')
        self._w('    memcpy(r + la, b, lb + 1);')
        self._w('    return r;')
        self._w('}')
        self._w('')
        self._w('static char* _bool_str(int b) { return b ? "true" : "false"; }')
        self._w('static char* _int_to_str(long long n) {')
        self._w('    char* s = _arena_alloc(32);')
        self._w('    snprintf(s, 32, "%lld", n);')
        self._w('    return s;')
        self._w('}')
        self._w('static char* _float_to_str(double f) {')
        self._w('    char* s = _arena_alloc(64);')
        self._w('    snprintf(s, 64, "%g", f);')
        self._w('    return s;')
        self._w('}')
        self._w('')

        # ── Forward-declare all user functions ────────────────────────────────
        func_decls = [s for s in program.statements if isinstance(s, FuncDecl)]
        if func_decls:
            self._w('/* ── Forward declarations ───────────────────────────── */')
            for fd in func_decls:
                self._w(self._func_signature(fd) + ';')
            self._w('')

        # ── Emit function definitions ─────────────────────────────────────────
        if func_decls:
            self._w('/* ── Function definitions ───────────────────────────── */')
            for fd in func_decls:
                self._emit_func_decl(fd)
                self._w('')

        # ── Emit main() ───────────────────────────────────────────────────────
        self._w('/* ── main ───────────────────────────────────────────────── */')
        self._w('int main(void) {')
        self._indent += 1

        global_stmts = [s for s in program.statements if not isinstance(s, FuncDecl)]
        for stmt in global_stmts:
            self._emit_stmt(stmt)

        self._w('    return 0;')
        self._indent -= 1
        self._w('}')

    # ── Function emission ─────────────────────────────────────────────────────

    def _func_signature(self, node: FuncDecl) -> str:
        ret = EDUCOMP_TO_C.get(node.return_type, 'void')
        params = ', '.join(
            f"{self._c_type(ptype, False)} {pname}"
            for ptype, pname in node.params
        ) or 'void'
        return f"{ret} {node.name}({params})"

    def _emit_func_decl(self, node: FuncDecl):
        # Push function params into symbol table
        saved_sym = dict(self._sym)
        for ptype, pname in node.params:
            self._sym[pname] = (ptype, False)

        self._w(self._func_signature(node) + ' {')
        self._indent += 1
        self._emit_block_body(node.body)
        self._indent -= 1
        self._w('}')

        # Restore symbol table
        self._sym = saved_sym

    # ── Statement emission ────────────────────────────────────────────────────

    def _emit_stmt(self, node: ASTNode):
        if isinstance(node, VarDecl):
            self._emit_var_decl(node)
        elif isinstance(node, ArrayDecl):
            self._emit_array_decl(node)
        elif isinstance(node, Assign):
            self._emit_assign(node)
        elif isinstance(node, IfStmt):
            self._emit_if(node)
        elif isinstance(node, WhileStmt):
            self._emit_while(node)
        elif isinstance(node, ReturnStmt):
            self._emit_return(node)
        elif isinstance(node, PrintStmt):
            self._emit_print(node)
        elif isinstance(node, Block):
            self._w(self._ind() + '{')
            self._indent += 1
            self._emit_block_body(node)
            self._indent -= 1
            self._w(self._ind() + '}')
        elif isinstance(node, ExprStmt):
            self._w(self._ind() + self._emit_expr(node.expr) + ';')
        elif isinstance(node, FuncDecl):
            pass  # emitted separately before main()

    def _emit_block_body(self, block: Block):
        for stmt in block.statements:
            self._emit_stmt(stmt)

    def _emit_var_decl(self, node: VarDecl):
        ctype = self._c_type(node.var_type, False)
        self._sym[node.name] = (node.var_type, False)
        if node.initializer:
            rhs = self._emit_expr(node.initializer)
        else:
            rhs = ZERO_VAL.get(node.var_type, '0')
        self._w(f"{self._ind()}{ctype} {node.name} = {rhs};")

    def _emit_array_decl(self, node: ArrayDecl):
        ctype = self._c_type(node.element_type, False)
        self._sym[node.name] = (node.element_type, True)
        size_expr = self._emit_expr(node.size)

        if node.initializer:
            init_vals = ', '.join(self._emit_expr(e) for e in node.initializer)
            self._w(f"{self._ind()}{ctype} {node.name}[{size_expr}] = {{{init_vals}}};")
        else:
            zero = ZERO_VAL.get(node.element_type, '0')
            self._w(f"{self._ind()}{ctype} {node.name}[{size_expr}];")
            # Zero-initialise in a loop
            idx = self._tmp('i')
            self._w(f"{self._ind()}for (long long {idx} = 0; {idx} < {size_expr}; {idx}++) "
                    f"{node.name}[{idx}] = {zero};")

    def _emit_assign(self, node: Assign):
        rhs = self._emit_expr(node.value)
        if node.index is not None:
            idx = self._emit_expr(node.index)
            self._w(f"{self._ind()}{node.name}[{idx}] = {rhs};")
        else:
            self._w(f"{self._ind()}{node.name} = {rhs};")

    def _emit_if(self, node: IfStmt):
        cond = self._emit_expr(node.condition)
        self._w(f"{self._ind()}if ({cond}) {{")
        self._indent += 1
        self._emit_block_body(node.then_branch)
        self._indent -= 1
        if node.else_branch:
            self._w(f"{self._ind()}}} else {{")
            self._indent += 1
            self._emit_block_body(node.else_branch)
            self._indent -= 1
        self._w(f"{self._ind()}}}")

    def _emit_while(self, node: WhileStmt):
        cond = self._emit_expr(node.condition)
        self._w(f"{self._ind()}while ({cond}) {{")
        self._indent += 1
        self._emit_block_body(node.body)
        self._indent -= 1
        self._w(f"{self._ind()}}}")

    def _emit_return(self, node: ReturnStmt):
        if node.value:
            self._w(f"{self._ind()}return {self._emit_expr(node.value)};")
        else:
            self._w(f"{self._ind()}return;")

    def _emit_print(self, node: PrintStmt):
        """
        Emit the correct printf call.
        bool values are printed as "true"/"false" via _bool_str().
        string values use %s.
        int/float use their own format specifiers.
        """
        inferencer = TypeInferencer(self._sym, self._funcs)
        etype = inferencer.typeof(node.value)
        expr  = self._emit_expr(node.value)

        if etype == 'bool':
            self._w(f'{self._ind()}printf("%s\\n", _bool_str({expr}));')
        elif etype == 'float':
            self._w(f'{self._ind()}printf("%g\\n", {expr});')
        elif etype == 'string':
            self._w(f'{self._ind()}printf("%s\\n", {expr});')
        else:
            # int (default)
            self._w(f'{self._ind()}printf("%lld\\n", (long long)({expr}));')

    # ── Expression emission ───────────────────────────────────────────────────

    def _emit_expr(self, node: ASTNode) -> str:
        """
        Returns a C expression string for the given AST expression node.
        For string concatenation (BinOp +) this emits a _concat() call.
        """
        if isinstance(node, Literal):
            return self._emit_literal(node)

        if isinstance(node, Identifier):
            return node.name

        if isinstance(node, ArrayAccess):
            idx = self._emit_expr(node.index)
            return f"{node.name}[{idx}]"

        if isinstance(node, UnaryOp):
            operand = self._emit_expr(node.operand)
            if node.op == '!':
                return f"(!{operand})"
            if node.op == '-':
                return f"(-{operand})"
            return operand

        if isinstance(node, BinOp):
            return self._emit_binop(node)

        if isinstance(node, FuncCall):
            args = ', '.join(self._emit_expr(a) for a in node.args)
            return f"{node.name}({args})"

        return '0'

    def _emit_literal(self, node: Literal) -> str:
        if node.lit_type == 'int':
            return f"{node.value}LL"
        if node.lit_type == 'float':
            # Ensure there is always a decimal point so C treats it as double
            s = str(node.value)
            return s if '.' in s or 'e' in s else s + '.0'
        if node.lit_type == 'bool':
            return '1' if node.value else '0'
        if node.lit_type == 'string':
            # Escape the string for C
            escaped = (str(node.value)
                       .replace('\\', '\\\\')
                       .replace('"',  '\\"')
                       .replace('\n', '\\n')
                       .replace('\t', '\\t'))
            return f'"{escaped}"'
        return '0'

    def _emit_binop(self, node: BinOp) -> str:
        inferencer = TypeInferencer(self._sym, self._funcs)
        lt = inferencer.typeof(node.left)
        rt = inferencer.typeof(node.right)

        lhs = self._emit_expr(node.left)
        rhs = self._emit_expr(node.right)

        # String concatenation
        if node.op == '+' and (lt == 'string' or rt == 'string'):
            # Coerce non-string side to string
            if lt != 'string':
                lhs = self._coerce_to_string(node.left, lt, lhs)
            if rt != 'string':
                rhs = self._coerce_to_string(node.right, rt, rhs)
            return f"_concat({lhs}, {rhs})"

        # Integer division: EduComp int/int → truncated division (like C)
        if node.op == '/' and lt == 'int' and rt == 'int':
            return f"({lhs} / {rhs})"

        # Map EduComp operators to C operators (all are identical)
        op_map = {
            '&&': '&&', '||': '||',
            '==': '==', '!=': '!=',
            '<': '<', '<=': '<=', '>': '>', '>=': '>=',
            '+': '+', '-': '-', '*': '*', '/': '/', '%': '%',
        }
        c_op = op_map.get(node.op, node.op)
        return f"({lhs} {c_op} {rhs})"

    def _coerce_to_string(self, node: ASTNode, etype: str, c_expr: str) -> str:
        """Wrap a non-string C expression in the appropriate to-string helper."""
        if etype == 'int':
            return f"_int_to_str({c_expr})"
        if etype == 'float':
            return f"_float_to_str({c_expr})"
        if etype == 'bool':
            return f"_bool_str({c_expr})"
        return c_expr   # already a string

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _c_type(self, educomp_type: str, is_array: bool) -> str:
        return EDUCOMP_TO_C.get(educomp_type, 'long long')

    def _tmp(self, prefix: str = 't') -> str:
        self._tmp_counter += 1
        return f"_edu_{prefix}{self._tmp_counter}"

    def _ind(self) -> str:
        return '    ' * self._indent

    def _w(self, line: str):
        self._lines.append(line)


# ── Compile C → native executable ─────────────────────────────────────────────

def compile_c_to_binary(c_path: str, exe_path: str) -> Tuple[bool, str]:
    """
    Calls gcc (or clang as fallback) to compile c_path into exe_path.
    Returns (success: bool, message: str).
    """
    compilers = ['gcc', 'clang', 'cc']
    for compiler in compilers:
        try:
            result = subprocess.run(
                [compiler, '-O2', '-Wall', '-o', exe_path, c_path],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return True, f"{compiler} compiled successfully"
            else:
                return False, f"{compiler} error:\n{result.stderr.strip()}"
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return False, "Compiler timed out"

    return False, ("No C compiler found. Install gcc: "
                   "sudo apt install gcc  OR  brew install gcc")


def run_binary(exe_path: str) -> Tuple[bool, str]:
    """Run the compiled executable and capture its output."""
    try:
        result = subprocess.run(
            [exe_path], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, f"Exit code {result.returncode}:\n{result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "Execution timed out"
    except Exception as e:
        return False, str(e)
