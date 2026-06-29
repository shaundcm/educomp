"""
EduComp Tree-Walk Interpreter
Executes an EduComp program directly from the AST.
Provides runtime output so the compiler pipeline is end-to-end runnable.
"""

from typing import Any, Dict, List, Optional
from ast_nodes import *


class RuntimeError_(Exception):
    def __init__(self, msg: str, line: int = 0):
        super().__init__(msg)
        self.line = line


class ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


# ── Environment (runtime scope chain) ────────────────────────────────────────

class Environment:
    def __init__(self, parent: Optional['Environment'] = None):
        self.store: Dict[str, Any] = {}
        self.parent = parent

    def set(self, name: str, value: Any):
        self.store[name] = value

    def assign(self, name: str, value: Any):
        if name in self.store:
            self.store[name] = value
        elif self.parent:
            self.parent.assign(name, value)
        else:
            raise RuntimeError_(f"Undeclared variable '{name}'")

    def get(self, name: str) -> Any:
        if name in self.store:
            return self.store[name]
        if self.parent:
            return self.parent.get(name)
        raise RuntimeError_(f"Undeclared variable '{name}'")


# ── Interpreter ───────────────────────────────────────────────────────────────

class Interpreter:
    def __init__(self):
        self.global_env = Environment()
        self.functions: Dict[str, FuncDecl] = {}
        self.output: List[str] = []
        self.errors: List[str] = []

    def execute(self, program: Program):
        # Register all functions first
        for stmt in program.statements:
            if isinstance(stmt, FuncDecl):
                self.functions[stmt.name] = stmt

        # Execute top-level statements
        for stmt in program.statements:
            if not isinstance(stmt, FuncDecl):
                try:
                    self._exec(stmt, self.global_env)
                except RuntimeError_ as e:
                    self.errors.append(f"Runtime error: {e}")
                except ReturnSignal:
                    pass

    def _exec(self, node: ASTNode, env: Environment):
        method = f"_exec_{type(node).__name__}"
        getattr(self, method, self._exec_default)(node, env)

    def _exec_default(self, node, env):
        pass

    def _exec_VarDecl(self, node: VarDecl, env: Environment):
        val = self._eval(node.initializer, env) if node.initializer else self._zero(node.var_type)
        env.set(node.name, val)

    def _exec_ArrayDecl(self, node: ArrayDecl, env: Environment):
        size = int(self._eval(node.size, env))
        if node.initializer:
            arr = [self._eval(e, env) for e in node.initializer]
            # Pad with zeros if needed
            while len(arr) < size:
                arr.append(self._zero(node.element_type))
        else:
            arr = [self._zero(node.element_type)] * size
        env.set(node.name, arr)

    def _exec_Assign(self, node: Assign, env: Environment):
        val = self._eval(node.value, env)
        if node.index is not None:
            arr = env.get(node.name)
            idx = int(self._eval(node.index, env))
            if not isinstance(arr, list):
                raise RuntimeError_(f"'{node.name}' is not an array", node.line)
            if idx < 0 or idx >= len(arr):
                raise RuntimeError_(f"Array index {idx} out of bounds for '{node.name}'", node.line)
            arr[idx] = val
        else:
            env.assign(node.name, val)

    def _exec_PrintStmt(self, node: PrintStmt, env: Environment):
        val = self._eval(node.value, env)
        out = self._to_str(val)
        self.output.append(out)
        print(out)

    def _exec_IfStmt(self, node: IfStmt, env: Environment):
        cond = self._eval(node.condition, env)
        child_env = Environment(env)
        if cond:
            self._exec_block(node.then_branch, child_env)
        elif node.else_branch:
            self._exec_block(node.else_branch, child_env)

    def _exec_WhileStmt(self, node: WhileStmt, env: Environment):
        limit = 100_000  # guard against infinite loops in demo
        count = 0
        while self._eval(node.condition, env):
            child_env = Environment(env)
            try:
                self._exec_block(node.body, child_env)
            except ReturnSignal:
                raise
            count += 1
            if count > limit:
                raise RuntimeError_("While loop exceeded iteration limit (possible infinite loop)")

    def _exec_ReturnStmt(self, node: ReturnStmt, env: Environment):
        val = self._eval(node.value, env) if node.value else None
        raise ReturnSignal(val)

    def _exec_Block(self, node: Block, env: Environment):
        self._exec_block(node, env)

    def _exec_block(self, block: Block, env: Environment):
        for stmt in block.statements:
            self._exec(stmt, env)

    def _exec_ExprStmt(self, node: ExprStmt, env: Environment):
        self._eval(node.expr, env)

    def _exec_FuncDecl(self, node: FuncDecl, env: Environment):
        pass  # already registered

    # ── Evaluator ─────────────────────────────────────────────────────────────

    def _eval(self, node: ASTNode, env: Environment) -> Any:
        method = f"_eval_{type(node).__name__}"
        return getattr(self, method, self._eval_default)(node, env)

    def _eval_default(self, node, env):
        return None

    def _eval_Literal(self, node: Literal, env: Environment) -> Any:
        return node.value

    def _eval_Identifier(self, node: Identifier, env: Environment) -> Any:
        return env.get(node.name)

    def _eval_ArrayAccess(self, node: ArrayAccess, env: Environment) -> Any:
        arr = env.get(node.name)
        idx = int(self._eval(node.index, env))
        if not isinstance(arr, list):
            raise RuntimeError_(f"'{node.name}' is not an array")
        if idx < 0 or idx >= len(arr):
            raise RuntimeError_(f"Array index {idx} out of bounds for '{node.name}'")
        return arr[idx]

    def _eval_BinOp(self, node: BinOp, env: Environment) -> Any:
        op = node.op
        # Short-circuit logic
        if op == '&&':
            return bool(self._eval(node.left, env)) and bool(self._eval(node.right, env))
        if op == '||':
            return bool(self._eval(node.left, env)) or bool(self._eval(node.right, env))

        l = self._eval(node.left, env)
        r = self._eval(node.right, env)

        if op == '+':  return l + r
        if op == '-':  return l - r
        if op == '*':  return l * r
        if op == '/':
            if r == 0: raise RuntimeError_("Division by zero")
            return l / r if isinstance(l, float) or isinstance(r, float) else l // r
        if op == '%':
            if r == 0: raise RuntimeError_("Modulo by zero")
            return l % r
        if op == '<':  return l < r
        if op == '<=': return l <= r
        if op == '>':  return l > r
        if op == '>=': return l >= r
        if op == '==': return l == r
        if op == '!=': return l != r
        raise RuntimeError_(f"Unknown operator '{op}'")

    def _eval_UnaryOp(self, node: UnaryOp, env: Environment) -> Any:
        v = self._eval(node.operand, env)
        if node.op == '-': return -v
        if node.op == '!': return not v
        return v

    def _eval_FuncCall(self, node: FuncCall, env: Environment) -> Any:
        if node.name not in self.functions:
            raise RuntimeError_(f"Undefined function '{node.name}'", node.line)
        func = self.functions[node.name]
        args = [self._eval(a, env) for a in node.args]
        func_env = Environment(self.global_env)
        for (_, pname), arg_val in zip(func.params, args):
            func_env.set(pname, arg_val)
        try:
            self._exec_block(func.body, func_env)
            return None
        except ReturnSignal as ret:
            return ret.value

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _zero(self, vtype: str) -> Any:
        return {'int': 0, 'float': 0.0, 'bool': False, 'string': ''}.get(vtype, None)

    def _to_str(self, val: Any) -> str:
        if isinstance(val, bool):
            return 'true' if val else 'false'
        if isinstance(val, float):
            return f"{val:g}"
        if isinstance(val, list):
            return '[' + ', '.join(self._to_str(v) for v in val) + ']'
        return str(val)
