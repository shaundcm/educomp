"""
EduComp — Main Compiler Driver
Usage:
    python main.py <source_file.edu>        # compile + run + generate visuals
    python main.py <source_file.edu> --no-run
    python main.py --demo                   # run the built-in demo program
"""

import sys
import os
import argparse

from lexer import Lexer
from parser import Parser
from semantic import SemanticAnalyser
from cfg import CFGBuilder
from visualizer import ASTVisualizer, ASTPrinter, all_cfgs_to_dot
from interpreter import Interpreter
from codegen_c import CCodeGenerator, compile_c_to_binary, run_binary


BANNER = """
╔══════════════════════════════════════════════════════╗
║          EduComp — Educational Compiler              ║
║  Lexer → Parser → Semantic → CFG → C Codegen        ║
╚══════════════════════════════════════════════════════╝
"""

# ── Demo source program ───────────────────────────────────────────────────────

DEMO_SOURCE = """\
// EduComp demo program
// Demonstrates: variables, arrays, if/else, while, functions, recursion-lite

func factorial(int n): int {
    if (n <= 1) {
        return 1;
    } else {
        return n * factorial(n - 1);
    }
}

func max(int a, int b): int {
    if (a > b) {
        return a;
    } else {
        return b;
    }
}

func greet(string name): string {
    return "Hello, " + name + "!";
}

// Main program
int result = factorial(6);
print(result);

string msg = greet("EduComp");
print(msg);

int a = 15;
int b = 28;
int bigger = max(a, b);
print(bigger);

// Array demo
array<int> nums[5] = {10, 20, 30, 40, 50};
int i = 0;
int total = 0;
while (i < 5) {
    total = total + nums[i];
    i = i + 1;
}
print(total);

// Boolean / conditional
bool flag = true;
if (flag && (result > 100)) {
    print("Result is large");
} else {
    print("Result is small");
}

// Float arithmetic
float pi = 3.14159;
float radius = 5.0;
float area = pi * radius * radius;
print(area);
"""


# ── Pipeline ──────────────────────────────────────────────────────────────────

def compile_and_run(source: str, run: bool = True, output_dir: str = '.',
                    use_codegen: bool = True) -> bool:
    print(BANNER)
    all_ok = True
    interp = None   # declared here so summary block can always reference it

    # ── 1. Lexing ─────────────────────────────────────────────────────────────
    section("1. LEXICAL ANALYSIS")
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    if lexer.errors:
        for e in lexer.errors:
            print(f"  [LEXER ERROR] {e}")
        all_ok = False
    else:
        print(f"  ✓ Tokenised {len(tokens)} tokens (no lexer errors)")

    # Print token summary (skip EOF)
    visible = [t for t in tokens if t.type.name != 'EOF']
    print(f"  Token breakdown:")
    from collections import Counter
    counts = Counter(t.type.name for t in visible)
    for name, count in counts.most_common():
        print(f"    {name:20s} × {count}")

    # ── 2. Parsing ────────────────────────────────────────────────────────────
    section("2. SYNTAX ANALYSIS (PARSING)")
    parser = Parser(tokens)
    ast = parser.parse()

    if parser.errors:
        for e in parser.errors:
            print(f"  [PARSE ERROR] {e}")
        all_ok = False
    else:
        print("  ✓ AST constructed (no parse errors)")

    # ── 3. Semantic Analysis ──────────────────────────────────────────────────
    section("3. SEMANTIC ANALYSIS")
    analyser = SemanticAnalyser()
    analyser.analyse(ast)

    if analyser.errors:
        for e in analyser.errors:
            print(f"  [SEMANTIC ERROR] {e}")
        all_ok = False
    else:
        print("  ✓ Type checking and scope analysis passed")

    # ── 4. AST Visualisation ──────────────────────────────────────────────────
    section("4. AST VISUALISATION")
    ast_printer = ASTPrinter()
    tree_text = ast_printer.print(ast)
    tree_path = os.path.join(output_dir, 'ast_tree.txt')
    with open(tree_path, 'w') as f:
        f.write(tree_text)
    print(f"  ✓ Plain-text AST written to: {tree_path}")

    ast_dot = ASTVisualizer().to_dot(ast)
    ast_dot_path = os.path.join(output_dir, 'ast.dot')
    with open(ast_dot_path, 'w') as f:
        f.write(ast_dot)
    print(f"  ✓ AST DOT file written to:   {ast_dot_path}")

    _try_render(ast_dot_path, os.path.join(output_dir, 'ast.png'), 'AST')

    # ── 5. CFG Generation ─────────────────────────────────────────────────────
    section("5. CONTROL FLOW GRAPH GENERATION")
    cfg_builder = CFGBuilder()
    cfgs = cfg_builder.build(ast)
    cfg_dots = all_cfgs_to_dot(cfgs)

    for name, dot_src in cfg_dots.items():
        safe = name.replace(' ', '_').replace('/', '_')
        dot_path = os.path.join(output_dir, f'cfg_{safe}.dot')
        with open(dot_path, 'w') as f:
            f.write(dot_src)
        png_path = os.path.join(output_dir, f'cfg_{safe}.png')
        print(f"  ✓ CFG '{name}' DOT written to: {dot_path}")
        _try_render(dot_path, png_path, f"CFG '{name}'")

    # ── 6. C Code Generation ──────────────────────────────────────────────────
    section("6. C CODE GENERATION")
    codegen = CCodeGenerator()
    c_source = codegen.generate(ast)

    c_path  = os.path.join(output_dir, 'output.c')
    exe_path = os.path.join(output_dir, 'program')

    with open(c_path, 'w') as f:
        f.write(c_source)
    print(f"  ✓ C source written to: {c_path}")

    if codegen.errors:
        for e in codegen.errors:
            print(f"  [CODEGEN ERROR] {e}")
        all_ok = False

    # ── 7. Compile C → Native Binary ──────────────────────────────────────────
    section("7. COMPILING C → NATIVE BINARY")
    compiled, msg = compile_c_to_binary(c_path, exe_path)
    if compiled:
        print(f"  ✓ {msg}")
        print(f"  ✓ Native executable: {exe_path}")
    else:
        print(f"  ℹ  {msg}")
        print(f"  ℹ  You can still compile manually: gcc -o program {c_path}")

    # ── 8. Run the native binary (if compiled) ────────────────────────────────
    if compiled and run:
        section("8. PROGRAM OUTPUT (Native Binary)")
        ok, output = run_binary(exe_path)
        if ok:
            print(output.rstrip())
        else:
            print(f"  [RUNTIME ERROR] {output}")
            all_ok = False

    # ── 9. Tree-Walk Interpreter (always runs, for cross-checking) ────────────
    if run:
        section("9. PROGRAM OUTPUT (Tree-Walk Interpreter)")
        interp = Interpreter()
        interp.execute(ast)
        if interp.errors:
            for e in interp.errors:
                print(f"  [RUNTIME ERROR] {e}")
            all_ok = False
        else:
            print("  (output above)")

        if compiled:
            print()
            print("  ℹ  Both backends ran — outputs should be identical.")
            print(f"  ℹ  Native binary: {exe_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    section("COMPILATION SUMMARY")
    interp_errs = len(interp.errors) if interp else 0
    total_errors = (len(lexer.errors) + len(parser.errors) +
                    len(analyser.errors) + len(codegen.errors) + interp_errs)
    if total_errors == 0:
        print("  ✓ Compilation successful — 0 errors")
        if compiled:
            print(f"  ✓ Native executable ready: {exe_path}")
    else:
        print(f"  ✗ Compilation finished with {total_errors} error(s)")

    return all_ok


# ── Helpers ───────────────────────────────────────────────────────────────────

def section(title: str):
    print(f"\n{'─' * 56}")
    print(f"  {title}")
    print(f"{'─' * 56}")


def _try_render(dot_path: str, png_path: str, label: str):
    """Try to render DOT → PNG via graphviz (if installed)."""
    try:
        import subprocess
        result = subprocess.run(
            ['dot', '-Tpng', dot_path, '-o', png_path],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            print(f"  ✓ {label} PNG rendered: {png_path}")
        else:
            print(f"  ℹ  Graphviz render skipped (dot error): {result.stderr.decode()[:80]}")
    except FileNotFoundError:
        print(f"  ℹ  Graphviz not found — open '{dot_path}' at https://dreampuf.github.io/GraphvizOnline/")
    except Exception as e:
        print(f"  ℹ  Render skipped: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="EduComp — Educational Compiler")
    ap.add_argument('source', nargs='?', help='Source file (.edu)')
    ap.add_argument('--no-run', action='store_true', help='Skip interpretation step')
    ap.add_argument('--demo', action='store_true', help='Run built-in demo program')
    ap.add_argument('--output-dir', default='.', help='Directory for output files')
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    if args.demo:
        print("Running built-in demo program…\n")
        demo_path = os.path.join(args.output_dir, 'demo.edu')
        with open(demo_path, 'w') as f:
            f.write(DEMO_SOURCE)
        print(f"Demo source saved to: {demo_path}\n")
        compile_and_run(DEMO_SOURCE, run=not args.no_run, output_dir=args.output_dir)
        return

    if not args.source:
        ap.print_help()
        print("\nTip: run  python main.py --demo  to see a full example.")
        sys.exit(1)

    with open(args.source, 'r') as f:
        source = f.read()

    ok = compile_and_run(source, run=not args.no_run, output_dir=args.output_dir)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
