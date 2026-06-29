"""
EduComp Control Flow Graph (CFG) Generator
Converts an AST into a CFG of basic blocks connected by directed edges.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from ast_nodes import *


# ── Basic Block ───────────────────────────────────────────────────────────────

@dataclass
class BasicBlock:
    id: int
    label: str
    statements: List[str] = field(default_factory=list)
    successors: List['BasicBlock'] = field(default_factory=list)
    predecessors: List['BasicBlock'] = field(default_factory=list)
    block_type: str = 'normal'   # 'normal' | 'entry' | 'exit' | 'condition' | 'merge'

    def add_stmt(self, s: str):
        self.statements.append(s)

    def link_to(self, other: 'BasicBlock', label: str = ''):
        if other not in self.successors:
            self.successors.append(other)
        if self not in other.predecessors:
            other.predecessors.append(self)

    def __repr__(self):
        return f"BB{self.id}({self.label})"


# ── CFG ───────────────────────────────────────────────────────────────────────

class CFG:
    def __init__(self, name: str = 'main'):
        self.name = name
        self.blocks: List[BasicBlock] = []
        self._counter = 0

    def new_block(self, label: str = '', btype: str = 'normal') -> BasicBlock:
        self._counter += 1
        label = label or f"B{self._counter}"
        bb = BasicBlock(self._counter, label, block_type=btype)
        self.blocks.append(bb)
        return bb

    def entry(self) -> Optional[BasicBlock]:
        for b in self.blocks:
            if b.block_type == 'entry':
                return b
        return self.blocks[0] if self.blocks else None


# ── CFG Builder ───────────────────────────────────────────────────────────────

class CFGBuilder:
    def __init__(self):
        self.cfgs: Dict[str, CFG] = {}
        self._cfg: Optional[CFG] = None

    def build(self, program: Program) -> Dict[str, CFG]:
        # Build a CFG for the top-level "main" scope
        global_stmts = [s for s in program.statements if not isinstance(s, FuncDecl)]
        func_decls = [s for s in program.statements if isinstance(s, FuncDecl)]

        if global_stmts:
            self._build_cfg('__main__', global_stmts)

        for fd in func_decls:
            self._build_func_cfg(fd)

        return self.cfgs

    # ── Per-function CFG ──────────────────────────────────────────────────────

    def _build_func_cfg(self, func: FuncDecl):
        params_str = ', '.join(f"{t} {n}" for t, n in func.params)
        label = f"func {func.name}({params_str}): {func.return_type}"
        self._build_cfg(func.name, func.body.statements, entry_label=label)

    def _build_cfg(self, name: str, stmts: List[ASTNode], entry_label: str = ''):
        self._cfg = CFG(name)
        entry = self._cfg.new_block(entry_label or 'entry', 'entry')
        exit_block = self._cfg.new_block('exit', 'exit')

        current = self._process_stmts(stmts, entry, exit_block)
        if current and exit_block not in current.successors:
            current.link_to(exit_block)

        self.cfgs[name] = self._cfg

    # ── Statement processing ──────────────────────────────────────────────────

    def _process_stmts(self, stmts: List[ASTNode],
                       current: BasicBlock,
                       exit_block: BasicBlock) -> Optional[BasicBlock]:
        for stmt in stmts:
            current = self._process_stmt(stmt, current, exit_block)
            if current is None:
                return None
        return current

    def _process_stmt(self, node: ASTNode,
                      current: BasicBlock,
                      exit_block: BasicBlock) -> Optional[BasicBlock]:

        if isinstance(node, VarDecl):
            init = f" = {self._expr_str(node.initializer)}" if node.initializer else ""
            current.add_stmt(f"{node.var_type} {node.name}{init}")
            return current

        if isinstance(node, ArrayDecl):
            current.add_stmt(f"array<{node.element_type}> {node.name}[{self._expr_str(node.size)}]")
            return current

        if isinstance(node, Assign):
            if node.index:
                current.add_stmt(f"{node.name}[{self._expr_str(node.index)}] = {self._expr_str(node.value)}")
            else:
                current.add_stmt(f"{node.name} = {self._expr_str(node.value)}")
            return current

        if isinstance(node, PrintStmt):
            current.add_stmt(f"print({self._expr_str(node.value)})")
            return current

        if isinstance(node, ExprStmt):
            current.add_stmt(self._expr_str(node.expr))
            return current

        if isinstance(node, ReturnStmt):
            val = self._expr_str(node.value) if node.value else ""
            current.add_stmt(f"return {val}")
            current.link_to(exit_block)
            return None   # no further statements reachable

        if isinstance(node, IfStmt):
            return self._process_if(node, current, exit_block)

        if isinstance(node, WhileStmt):
            return self._process_while(node, current, exit_block)

        if isinstance(node, Block):
            return self._process_stmts(node.statements, current, exit_block)

        if isinstance(node, FuncDecl):
            # Nested function decls: skip (already handled at top level)
            return current

        return current

    def _process_if(self, node: IfStmt,
                    current: BasicBlock,
                    exit_block: BasicBlock) -> BasicBlock:
        cond_block = self._cfg.new_block(f"if ({self._expr_str(node.condition)})", 'condition')
        current.link_to(cond_block)

        then_block = self._cfg.new_block('then', 'normal')
        cond_block.link_to(then_block)

        merge_block = self._cfg.new_block('merge', 'merge')

        # Then branch
        then_end = self._process_stmts(node.then_branch.statements, then_block, exit_block)
        if then_end:
            then_end.link_to(merge_block)

        # Else branch
        if node.else_branch:
            else_block = self._cfg.new_block('else', 'normal')
            cond_block.link_to(else_block)
            else_end = self._process_stmts(node.else_branch.statements, else_block, exit_block)
            if else_end:
                else_end.link_to(merge_block)
        else:
            cond_block.link_to(merge_block)

        return merge_block

    def _process_while(self, node: WhileStmt,
                       current: BasicBlock,
                       exit_block: BasicBlock) -> BasicBlock:
        cond_block = self._cfg.new_block(f"while ({self._expr_str(node.condition)})", 'condition')
        current.link_to(cond_block)

        body_block = self._cfg.new_block('loop_body', 'normal')
        after_block = self._cfg.new_block('after_loop', 'normal')

        cond_block.link_to(body_block)   # true
        cond_block.link_to(after_block)  # false

        body_end = self._process_stmts(node.body.statements, body_block, exit_block)
        if body_end:
            body_end.link_to(cond_block)  # back-edge

        return after_block

    # ── Expression pretty-printer ─────────────────────────────────────────────

    def _expr_str(self, node: Optional[ASTNode]) -> str:
        if node is None:
            return ""
        if isinstance(node, Literal):
            if node.lit_type == 'string':
                return f'"{node.value}"'
            return str(node.value).lower() if isinstance(node.value, bool) else str(node.value)
        if isinstance(node, Identifier):
            return node.name
        if isinstance(node, BinOp):
            return f"({self._expr_str(node.left)} {node.op} {self._expr_str(node.right)})"
        if isinstance(node, UnaryOp):
            return f"({node.op}{self._expr_str(node.operand)})"
        if isinstance(node, FuncCall):
            args = ', '.join(self._expr_str(a) for a in node.args)
            return f"{node.name}({args})"
        if isinstance(node, ArrayAccess):
            return f"{node.name}[{self._expr_str(node.index)}]"
        return "?"
