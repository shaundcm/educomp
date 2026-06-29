"""
EduComp Semantic Analyser
Performs:
  - Type checking
  - Scope/symbol-table management (block-level scoping)
  - Function declaration and call validation
  - Return-path checking
"""

from typing import Dict, List, Optional, Tuple
from ast_nodes import *


class SemanticError(Exception):
    def __init__(self, message: str, line: int = 0):
        super().__init__(message)
        self.line = line


# ── Symbol table (stack of scopes) ───────────────────────────────────────────

class SymbolTable:
    """Linked chain of scopes.  Each scope is a dict name → (type, is_array)."""

    def __init__(self):
        self.scopes: List[Dict[str, Tuple[str, bool]]] = [{}]

    def push(self):
        self.scopes.append({})

    def pop(self):
        self.scopes.pop()

    def declare(self, name: str, vtype: str, is_array: bool = False):
        self.scopes[-1][name] = (vtype, is_array)

    def lookup(self, name: str) -> Optional[Tuple[str, bool]]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def declared_in_current(self, name: str) -> bool:
        return name in self.scopes[-1]


# ── Function table ────────────────────────────────────────────────────────────

class FunctionTable:
    """Stores function signatures: name → (return_type, [(param_type, param_name)])"""

    def __init__(self):
        self.funcs: Dict[str, Tuple[str, List[Tuple[str, str]]]] = {}

    def declare(self, name: str, return_type: str, params: List[Tuple[str, str]]):
        self.funcs[name] = (return_type, params)

    def lookup(self, name: str) -> Optional[Tuple[str, List[Tuple[str, str]]]]:
        return self.funcs.get(name)


# ── Numeric promotion helper ──────────────────────────────────────────────────

def _numeric_result(t1: str, t2: str) -> str:
    """int op int → int; anything involving float → float."""
    if t1 == 'float' or t2 == 'float':
        return 'float'
    return 'int'


NUMERIC = {'int', 'float'}
COMPARABLE = {'int', 'float', 'string', 'bool'}

TYPE_KEYWORDS = {'int', 'float', 'bool', 'string'}


# ── Semantic Analyser ─────────────────────────────────────────────────────────

class SemanticAnalyser:
    def __init__(self):
        self.symbols = SymbolTable()
        self.functions = FunctionTable()
        self.errors: List[str] = []
        self._current_func_return: Optional[str] = None

    def _err(self, msg: str, line: int = 0):
        prefix = f"L{line}: " if line else ""
        self.errors.append(f"{prefix}{msg}")

    # ── Entry point ───────────────────────────────────────────────────────────

    def analyse(self, node: Program):
        # First pass: collect all function signatures (allows forward calls)
        for stmt in node.statements:
            if isinstance(stmt, FuncDecl):
                if self.functions.lookup(stmt.name):
                    self._err(f"Function '{stmt.name}' already declared", stmt.line)
                else:
                    self.functions.declare(stmt.name, stmt.return_type, stmt.params)

        # Second pass: full analysis
        for stmt in node.statements:
            self._visit(stmt)

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def _visit(self, node: ASTNode) -> str:
        """Visit a node and return its type string (or 'void')."""
        method = f"_visit_{type(node).__name__}"
        visitor = getattr(self, method, self._visit_default)
        return visitor(node)

    def _visit_default(self, node: ASTNode) -> str:
        return 'void'

    # ── Statements ────────────────────────────────────────────────────────────

    def _visit_Program(self, node: Program) -> str:
        for s in node.statements:
            self._visit(s)
        return 'void'

    def _visit_VarDecl(self, node: VarDecl) -> str:
        if self.symbols.declared_in_current(node.name):
            self._err(f"Variable '{node.name}' already declared in this scope", node.line)
        else:
            self.symbols.declare(node.name, node.var_type)
        if node.initializer:
            init_type = self._visit(node.initializer)
            if not self._compatible(node.var_type, init_type):
                self._err(
                    f"Type mismatch: cannot assign '{init_type}' to '{node.var_type}' variable '{node.name}'",
                    node.line)
        return 'void'

    def _visit_ArrayDecl(self, node: ArrayDecl) -> str:
        if self.symbols.declared_in_current(node.name):
            self._err(f"Array '{node.name}' already declared in this scope", node.line)
        else:
            self.symbols.declare(node.name, node.element_type, is_array=True)
        size_type = self._visit(node.size)
        if size_type != 'int':
            self._err(f"Array size must be an integer expression, got '{size_type}'", node.line)
        if node.initializer:
            for elem in node.initializer:
                et = self._visit(elem)
                if not self._compatible(node.element_type, et):
                    self._err(
                        f"Array initializer type mismatch: expected '{node.element_type}', got '{et}'",
                        node.line)
        return 'void'

    def _visit_Assign(self, node: Assign) -> str:
        sym = self.symbols.lookup(node.name)
        if sym is None:
            self._err(f"Undeclared variable '{node.name}'", node.line)
            return 'void'
        var_type, is_array = sym
        val_type = self._visit(node.value)

        if node.index is not None:
            # Array element assignment
            if not is_array:
                self._err(f"'{node.name}' is not an array", node.line)
            idx_type = self._visit(node.index)
            if idx_type != 'int':
                self._err(f"Array index must be integer, got '{idx_type}'", node.line)
            if not self._compatible(var_type, val_type):
                self._err(
                    f"Type mismatch: cannot assign '{val_type}' to array '{node.name}' of type '{var_type}'",
                    node.line)
        else:
            if is_array:
                self._err(f"Cannot assign scalar to array '{node.name}'", node.line)
            if not self._compatible(var_type, val_type):
                self._err(
                    f"Type mismatch: cannot assign '{val_type}' to '{var_type}' variable '{node.name}'",
                    node.line)
        return 'void'

    def _visit_IfStmt(self, node: IfStmt) -> str:
        cond_type = self._visit(node.condition)
        if cond_type != 'bool':
            self._err(f"If condition must be bool, got '{cond_type}'", node.line)
        self.symbols.push()
        self._visit(node.then_branch)
        self.symbols.pop()
        if node.else_branch:
            self.symbols.push()
            self._visit(node.else_branch)
            self.symbols.pop()
        return 'void'

    def _visit_WhileStmt(self, node: WhileStmt) -> str:
        cond_type = self._visit(node.condition)
        if cond_type != 'bool':
            self._err(f"While condition must be bool, got '{cond_type}'", node.line)
        self.symbols.push()
        self._visit(node.body)
        self.symbols.pop()
        return 'void'

    def _visit_ReturnStmt(self, node: ReturnStmt) -> str:
        if self._current_func_return is None:
            self._err("'return' used outside of a function", node.line)
            return 'void'
        if node.value is None:
            if self._current_func_return != 'void':
                self._err(
                    f"Function expects return type '{self._current_func_return}' but returns nothing",
                    node.line)
        else:
            ret_type = self._visit(node.value)
            if not self._compatible(self._current_func_return, ret_type):
                self._err(
                    f"Return type mismatch: expected '{self._current_func_return}', got '{ret_type}'",
                    node.line)
        return 'void'

    def _visit_PrintStmt(self, node: PrintStmt) -> str:
        self._visit(node.value)
        return 'void'

    def _visit_Block(self, node: Block) -> str:
        for s in node.statements:
            self._visit(s)
        return 'void'

    def _visit_FuncDecl(self, node: FuncDecl) -> str:
        self.symbols.push()
        for ptype, pname in node.params:
            self.symbols.declare(pname, ptype)
        prev_return = self._current_func_return
        self._current_func_return = node.return_type
        self._visit(node.body)
        self._current_func_return = prev_return
        self.symbols.pop()
        return 'void'

    def _visit_ExprStmt(self, node: ExprStmt) -> str:
        self._visit(node.expr)
        return 'void'

    # ── Expressions ───────────────────────────────────────────────────────────

    def _visit_Literal(self, node: Literal) -> str:
        return node.lit_type

    def _visit_Identifier(self, node: Identifier) -> str:
        sym = self.symbols.lookup(node.name)
        if sym is None:
            self._err(f"Undeclared variable '{node.name}'", node.line)
            return 'int'
        return sym[0]

    def _visit_ArrayAccess(self, node: ArrayAccess) -> str:
        sym = self.symbols.lookup(node.name)
        if sym is None:
            self._err(f"Undeclared variable '{node.name}'", node.line)
            return 'int'
        var_type, is_array = sym
        if not is_array:
            self._err(f"'{node.name}' is not an array", node.line)
        idx_type = self._visit(node.index)
        if idx_type != 'int':
            self._err(f"Array index must be integer, got '{idx_type}'", node.line)
        return var_type

    def _visit_BinOp(self, node: BinOp) -> str:
        lt = self._visit(node.left)
        rt = self._visit(node.right)
        op = node.op

        if op in ('+', '-', '*', '/', '%'):
            if op == '+' and (lt == 'string' or rt == 'string'):
                # String concatenation
                return 'string'
            if lt not in NUMERIC or rt not in NUMERIC:
                self._err(
                    f"Operator '{op}' requires numeric operands, got '{lt}' and '{rt}'",
                    node.line)
                return 'int'
            return _numeric_result(lt, rt)

        if op in ('<', '<=', '>', '>='):
            if lt not in NUMERIC or rt not in NUMERIC:
                self._err(
                    f"Operator '{op}' requires numeric operands, got '{lt}' and '{rt}'",
                    node.line)
            return 'bool'

        if op in ('==', '!='):
            if lt != rt and not (lt in NUMERIC and rt in NUMERIC):
                self._err(
                    f"Operator '{op}' requires compatible types, got '{lt}' and '{rt}'",
                    node.line)
            return 'bool'

        if op in ('&&', '||'):
            if lt != 'bool' or rt != 'bool':
                self._err(
                    f"Logical operator '{op}' requires bool operands, got '{lt}' and '{rt}'",
                    node.line)
            return 'bool'

        return 'void'

    def _visit_UnaryOp(self, node: UnaryOp) -> str:
        t = self._visit(node.operand)
        if node.op == '!':
            if t != 'bool':
                self._err(f"Operator '!' requires bool operand, got '{t}'", node.line)
            return 'bool'
        if node.op == '-':
            if t not in NUMERIC:
                self._err(f"Unary '-' requires numeric operand, got '{t}'", node.line)
            return t
        return t

    def _visit_FuncCall(self, node: FuncCall) -> str:
        sig = self.functions.lookup(node.name)
        if sig is None:
            self._err(f"Undeclared function '{node.name}'", node.line)
            return 'int'
        ret_type, params = sig
        if len(node.args) != len(params):
            self._err(
                f"Function '{node.name}' expects {len(params)} arguments, got {len(node.args)}",
                node.line)
        else:
            for i, (arg, (ptype, _)) in enumerate(zip(node.args, params)):
                atype = self._visit(arg)
                if not self._compatible(ptype, atype):
                    self._err(
                        f"Argument {i+1} of '{node.name}': expected '{ptype}', got '{atype}'",
                        node.line)
        return ret_type

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compatible(self, expected: str, actual: str) -> bool:
        if expected == actual:
            return True
        # Allow int ↔ float implicit widening
        if expected in NUMERIC and actual in NUMERIC:
            return True
        return False
