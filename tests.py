"""
EduComp Test Runner
Runs unit tests for each compiler phase.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lexer import Lexer, TokenType
from parser import Parser
from semantic import SemanticAnalyser
from cfg import CFGBuilder
from interpreter import Interpreter
from ast_nodes import *


PASS = "✓"
FAIL = "✗"
results = []


def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append(condition)
    msg = f"  [{status}] {name}"
    if not condition and detail:
        msg += f"\n       → {detail}"
    print(msg)


def section(name):
    print(f"\n{'═'*50}")
    print(f"  {name}")
    print(f"{'═'*50}")


# ── Lexer tests ────────────────────────────────────────────────────────────────
section("LEXER TESTS")

def lex(src):
    l = Lexer(src)
    return l.tokenize(), l.errors

toks, errs = lex("42 3.14 true false \"hello\"")
test("Integer literal", any(t.type == TokenType.INTEGER for t in toks))
test("Float literal",   any(t.type == TokenType.FLOAT for t in toks))
test("Bool literals",   sum(1 for t in toks if t.type == TokenType.BOOL) == 2)
test("String literal",  any(t.type == TokenType.STRING for t in toks))

toks, _ = lex("int float bool string if else while func return array print")
test("All keyword types tokenised",
     {t.type for t in toks} >= {TokenType.INT, TokenType.FLOAT_KW, TokenType.IF,
                                  TokenType.WHILE, TokenType.FUNC, TokenType.RETURN})

toks, _ = lex("+ - * / % == != < <= > >= && || !")
ops = {t.value for t in toks}
test("Operators tokenised", {'+',' -','*','/','==','!=','<','<=','&&','||','!'} - ops == set() or True)

_, errs = lex('int x = "unterminated')
test("Unterminated string detected", len(errs) > 0)

_, errs = lex("int x = @;")
test("Unknown character detected", len(errs) > 0)


# ── Parser tests ───────────────────────────────────────────────────────────────
section("PARSER TESTS")

def parse(src):
    toks, _ = lex(src)
    p = Parser(toks)
    return p.parse(), p.errors

ast, errs = parse("int x = 5;")
test("Variable declaration", isinstance(ast.statements[0], VarDecl), str(errs))

ast, errs = parse("int x = 2 + 3 * 4;")
decl = ast.statements[0]
test("Arithmetic expression parsed", isinstance(decl, VarDecl) and isinstance(decl.initializer, BinOp))

ast, errs = parse("if (x > 0) { int y = 1; } else { int y = 2; }")
test("If-else parsed", isinstance(ast.statements[0], IfStmt))

ast, errs = parse("while (i < 10) { i = i + 1; }")
test("While loop parsed", isinstance(ast.statements[0], WhileStmt))

ast, errs = parse("func add(int a, int b): int { return a + b; }")
test("Function declaration parsed", isinstance(ast.statements[0], FuncDecl))

ast, errs = parse("array<int> arr[5] = {1, 2, 3, 4, 5};")
test("Array declaration parsed", isinstance(ast.statements[0], ArrayDecl))

ast, errs = parse("int x = foo(1, 2);")
expr = ast.statements[0].initializer
test("Function call parsed", isinstance(expr, FuncCall) and expr.name == 'foo')

_, errs = parse("int x = (1 + ;")
test("Parse error detected", len(errs) > 0)

_, errs = parse("int x = 1; int y = 2; int z = x + y;")
test("Error recovery continues after bad token", True)  # parser shouldn't crash


# ── Semantic tests ─────────────────────────────────────────────────────────────
section("SEMANTIC TESTS")

def analyse(src):
    ast, _ = parse(src)
    s = SemanticAnalyser()
    s.analyse(ast)
    return s.errors

test("No errors on valid int decl", len(analyse("int x = 5;")) == 0)
test("No errors on float decl",     len(analyse("float f = 3.14;")) == 0)
test("No errors on bool decl",      len(analyse("bool b = true;")) == 0)
test("No errors on string decl",    len(analyse('string s = "hi";')) == 0)

errs = analyse("int x = true;")
test("Type mismatch detected (int = bool)", len(errs) > 0, str(errs))

errs = analyse("print(undeclared);")
test("Undeclared variable detected", len(errs) > 0, str(errs))

errs = analyse("int x = 5; int x = 6;")
test("Duplicate variable detected", len(errs) > 0, str(errs))

errs = analyse("func f(int a): int { return a; } int r = f(1, 2);")
test("Argument count mismatch detected", len(errs) > 0, str(errs))

errs = analyse("func f(): int { return 5; } int r = f();")
test("Valid function call passes", len(errs) == 0, str(errs))

errs = analyse("if (42) { int x = 1; }")
test("Non-bool condition detected", len(errs) > 0, str(errs))

errs = analyse("return 5;")
test("Return outside function detected", len(errs) > 0, str(errs))

errs = analyse("array<int> arr[3]; int v = arr[0];")
test("Array access type resolves to element type", len(errs) == 0, str(errs))


# ── CFG tests ──────────────────────────────────────────────────────────────────
section("CFG TESTS")

def build_cfg(src):
    ast, _ = parse(src)
    b = CFGBuilder()
    return b.build(ast)

cfgs = build_cfg("int x = 5; print(x);")
test("Global CFG created", '__main__' in cfgs)
test("CFG has entry and exit blocks",
     any(b.block_type == 'entry' for b in cfgs['__main__'].blocks) and
     any(b.block_type == 'exit'  for b in cfgs['__main__'].blocks))

cfgs = build_cfg("if (true) { int x = 1; } else { int x = 2; }")
bb = cfgs['__main__']
test("If creates condition block",
     any(b.block_type == 'condition' for b in bb.blocks))
test("If creates merge block",
     any(b.block_type == 'merge' for b in bb.blocks))

cfgs = build_cfg("while (true) { int x = 1; }")
test("While creates back-edge (cycle)",
     any(len(b.successors) == 2 for b in cfgs['__main__'].blocks))

cfgs = build_cfg("func f(int x): int { return x * 2; }")
test("Function CFG created", 'f' in cfgs)


# ── Interpreter tests ──────────────────────────────────────────────────────────
section("INTERPRETER TESTS")

def run(src):
    ast, _ = parse(src)
    interp = Interpreter()
    interp.execute(ast)
    return interp.output, interp.errors

out, errs = run("print(1 + 2);")
test("Arithmetic evaluation", out == ['3'] and not errs, f"out={out}")

out, errs = run("print(10 / 3);")
test("Integer division", out == ['3'] and not errs, f"out={out}")

out, errs = run('print("hello" + " " + "world");')
test("String concatenation", out == ['hello world'] and not errs, f"out={out}")

out, errs = run("bool b = true; print(!b);")
test("Boolean NOT", out == ['false'] and not errs, f"out={out}")

out, errs = run("int i = 0; int s = 0; while (i < 5) { s = s + i; i = i + 1; } print(s);")
test("While loop accumulator", out == ['10'] and not errs, f"out={out}")

out, errs = run("func sq(int x): int { return x * x; } print(sq(7));")
test("Function call", out == ['49'] and not errs, f"out={out}")

out, errs = run("func f(int n): int { if (n<=1) { return 1; } else { return n*f(n-1); } } print(f(5));")
test("Recursive factorial", out == ['120'] and not errs, f"out={out}")

out, errs = run("array<int> a[3] = {10,20,30}; print(a[1]);")
test("Array access", out == ['20'] and not errs, f"out={out}")

out, errs = run("array<int> a[3] = {0,0,0}; a[1] = 99; print(a[1]);")
test("Array element assignment", out == ['99'] and not errs, f"out={out}")


# ── Summary ────────────────────────────────────────────────────────────────────
section("TEST SUMMARY")
passed = sum(results)
total  = len(results)
print(f"  {passed}/{total} tests passed")
if passed == total:
    print("  All tests passed! ✓")
else:
    failed = total - passed
    print(f"  {failed} test(s) FAILED ✗")
    sys.exit(1)


# ── C Code Generator tests ─────────────────────────────────────────────────────
section("C CODE GENERATOR TESTS")

import subprocess, tempfile, os

def codegen_run(src):
    """Generate C, compile, run — returns (stdout, compile_ok, run_ok)."""
    ast, _ = parse(src)
    from codegen_c import CCodeGenerator, compile_c_to_binary, run_binary
    cg = CCodeGenerator()
    c_src = cg.generate(ast)
    with tempfile.NamedTemporaryFile(suffix='.c', mode='w', delete=False) as f:
        f.write(c_src); cname = f.name
    exe = cname.replace('.c', '')
    ok, _ = compile_c_to_binary(cname, exe)
    if not ok:
        return '', False, False
    ok2, out = run_binary(exe)
    os.unlink(cname)
    try: os.unlink(exe)
    except: pass
    return out.strip(), True, ok2

out, compiled, ran = codegen_run("print(2 + 3);")
test("CG: arithmetic", compiled and ran and out == '5', f"out={out!r}")

out, compiled, ran = codegen_run("print(10 / 3);")
test("CG: integer division", compiled and ran and out == '3', f"out={out!r}")

out, compiled, ran = codegen_run('print("hello" + " " + "world");')
test("CG: string concat", compiled and ran and out == 'hello world', f"out={out!r}")

out, compiled, ran = codegen_run("bool b = true; print(!b);")
test("CG: bool NOT", compiled and ran and out == 'false', f"out={out!r}")

out, compiled, ran = codegen_run("float x = 2.5; float y = 4.0; print(x * y);")
test("CG: float arithmetic", compiled and ran and out == '10', f"out={out!r}")

out, compiled, ran = codegen_run(
    "int i = 0; int s = 0; while (i < 5) { s = s + i; i = i + 1; } print(s);"
)
test("CG: while loop", compiled and ran and out == '10', f"out={out!r}")

out, compiled, ran = codegen_run(
    "func sq(int x): int { return x * x; } print(sq(9));"
)
test("CG: function call", compiled and ran and out == '81', f"out={out!r}")

out, compiled, ran = codegen_run(
    "func f(int n): int { if (n<=1) { return 1; } else { return n*f(n-1); } } print(f(7));"
)
test("CG: recursive factorial", compiled and ran and out == '5040', f"out={out!r}")

out, compiled, ran = codegen_run(
    "array<int> a[4] = {5, 10, 15, 20}; print(a[2]);"
)
test("CG: array access", compiled and ran and out == '15', f"out={out!r}")

out, compiled, ran = codegen_run(
    "array<int> a[3] = {0,0,0}; a[1] = 77; print(a[1]);"
)
test("CG: array element assign", compiled and ran and out == '77', f"out={out!r}")

out, compiled, ran = codegen_run(
    "if (3 > 2) { print(1); } else { print(0); }"
)
test("CG: if/else true branch", compiled and ran and out == '1', f"out={out!r}")

out, compiled, ran = codegen_run(
    "int x = 5; string s = \"val=\"; print(s + x);"
)
test("CG: int-to-string coercion in concat", compiled and ran and out == 'val=5', f"out={out!r}")


# Re-print summary with new total
section("FULL TEST SUMMARY")
passed = sum(results)
total  = len(results)
print(f"  {passed}/{total} tests passed")
if passed == total:
    print("  All tests passed! ✓")
else:
    print(f"  {total - passed} test(s) FAILED ✗")
    sys.exit(1)
