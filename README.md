# EduComp — Educational Compiler

A complete, error-resilient compiler built entirely from scratch in Python with no third-party libraries. EduComp defines its own statically-typed programming language (`.edu`) and processes it through every classical compiler phase — all the way to a **native binary** via C code generation and gcc.

---

## Pipeline

```
Source (.edu)
    │
    ▼
Stage 1 — Lexical Analysis       lexer.py         Tokenises source text character by character
    │
    ▼
Stage 2 — Syntax Analysis        parser.py        Recursive-descent parser → builds the AST
    │
    ▼
Stage 3 — Semantic Analysis      semantic.py      Type checking, scope validation, function signatures
    │
    ▼
Stage 4 — AST Visualisation      visualizer.py    Colour-coded Graphviz DOT/PNG diagram
    │
    ▼
Stage 5 — CFG Generation         cfg.py           Basic blocks + directed edges per function
    │
    ├─────────────────────────────────────┐
    ▼                                     ▼
Stage 6 — C Code Generation      Stage 7 — Tree-Walk Interpreter
codegen_c.py → output.c          interpreter.py → runs directly in Python
    │
    ▼
gcc -O2 → native executable
```

---

## The EduComp Language

EduComp is a statically-typed, C-like language. Programs are written in `.edu` files.

**Types:** `int` (64-bit), `float` (double), `bool`, `string`, `array<T>`

**Features:** variables, arrays, arithmetic/logical operators, `if/else`, `while` loops, functions, recursion, single and multi-line comments

```c
func factorial(int n): int {
    if (n <= 1) { return 1; }
    else        { return n * factorial(n - 1); }
}

int result = factorial(6);
print(result);              // 720

array<int> nums[5] = {10, 20, 30, 40, 50};
int i = 0;
int total = 0;
while (i < 5) {
    total = total + nums[i];
    i = i + 1;
}
print(total);               // 150
```

---

## Error-Resilient Compilation

EduComp never stops at the first error — all errors across all phases are collected and reported in a single pass.

| Phase | Mechanism |
|---|---|
| Lexer | Unknown characters appended to error list; scanning continues |
| Parser | `_synchronize()` skips to the next safe token on `ParseError` |
| Semantic | All type and scope errors collected; AST traversal never aborts |

---

## File Structure

| File | Role | Lines |
|---|---|---|
| `lexer.py` | Lexical analyser — 33 token types | ~220 |
| `ast_nodes.py` | 16 AST node dataclass definitions | ~138 |
| `parser.py` | Recursive-descent parser | ~290 |
| `semantic.py` | Type checking, block-level scoping, two-pass function resolution | ~280 |
| `cfg.py` | Control Flow Graph builder | ~200 |
| `visualizer.py` | DOT/PNG generator for AST and CFG | ~280 |
| `codegen_c.py` | C code generator — emits compilable C source | ~310 |
| `interpreter.py` | Tree-walk interpreter — executes AST directly | ~237 |
| `main.py` | Compiler driver — orchestrates all 9 pipeline stages | ~200 |
| `tests.py` | 56 automated unit tests across all phases | ~220 |

---

## Getting Started

**Requirements:** Python 3.8+, no pip packages needed.  
**Optional:** Graphviz (for PNG diagrams), gcc/clang (for native binary compilation).

```bash
# Clone and enter the project
git clone https://github.com/shaundcm/educomp
cd educomp

# Run the built-in demo (recommended first step)
python main.py --demo

# Compile an example program
python main.py examples/example1.edu

# Write and run your own program
python main.py myprogram.edu

# Compile only, no execution
python main.py myprogram.edu --no-run

# Custom output directory
python main.py myprogram.edu --output-dir ./results

# Run the test suite
python tests.py
```

---

## Output Files

After compilation, all output is written to `./output/` (or your `--output-dir`):

```
output/
├── ast_tree.txt        # plain-text AST dump
├── ast.dot             # AST Graphviz source
├── ast.png             # AST diagram image (requires Graphviz)
├── cfg_<name>.dot      # CFG source per function/scope
├── cfg_<name>.png      # CFG diagram per function/scope
├── output.c            # generated C source
└── program             # native executable (Linux/macOS)
```

> If Graphviz isn't installed, paste any `.dot` file into [dreampuf.github.io/GraphvizOnline](https://dreampuf.github.io/GraphvizOnline) to view diagrams in the browser.

---

## Test Suite

56 unit tests across all compiler phases — run with `python tests.py`.

| Phase | Tests |
|---|---|
| Lexer | 8 |
| Parser | 9 |
| Semantic | 12 |
| CFG | 6 |
| Interpreter | 9 |
| C Code Generator | 12 |
| **Total** | **56 / 56 passing** |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python: command not found` | Install Python 3.8+ or try `python3` |
| No PNG files generated | Install Graphviz, or view `.dot` files online |
| `gcc: command not found` | Install gcc — `output.c` is still generated and can be compiled manually |
| `Permission denied` on binary | Run `chmod +x output/program` |
| Compilation errors reported | Read the `[PARSE ERROR]` / `[SEMANTIC ERROR]` messages — they include line numbers |

---

## Authors

Deishaun Colins Martin (23PT05) · Devanand K (23PT06)  
PSG College of Technology — Principles of Compiler Design
