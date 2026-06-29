"""
EduComp Visualizer
Produces:
  - Graphviz DOT source for AST
  - Graphviz DOT source for CFG (one per function / global scope)
  - Plain-text tree dump of the AST
"""

from ast_nodes import *
from cfg import CFG, BasicBlock
from typing import Dict, List


# ── AST → DOT ────────────────────────────────────────────────────────────────

class ASTVisualizer:
    def __init__(self):
        self._counter = 0
        self._lines: List[str] = []

    def _new_id(self) -> str:
        self._counter += 1
        return f"n{self._counter}"

    def to_dot(self, root: ASTNode) -> str:
        self._lines = [
            'digraph AST {',
            '  graph [rankdir=TB fontname="Courier" bgcolor="#1e1e2e"];',
            '  node  [shape=box style="rounded,filled" fontname="Courier" fontsize=10'
            '         fillcolor="#313244" fontcolor="#cdd6f4" color="#89b4fa"];',
            '  edge  [color="#6c7086" arrowsize=0.7];',
        ]
        self._visit(root)
        self._lines.append('}')
        return '\n'.join(self._lines)

    def _node(self, nid: str, label: str, color: str = '#313244') -> None:
        safe = label.replace('"', '\\"').replace('\n', '\\n')
        self._lines.append(f'  {nid} [label="{safe}" fillcolor="{color}"];')

    def _edge(self, parent: str, child: str, label: str = '') -> None:
        lbl = f' [label="{label}"]' if label else ''
        self._lines.append(f'  {parent} -> {child}{lbl};')

    def _visit(self, node: ASTNode, parent_id: str = '') -> str:
        nid = self._new_id()
        method = f"_dot_{type(node).__name__}"
        visitor = getattr(self, method, self._dot_default)
        visitor(node, nid, parent_id)
        return nid

    def _dot_default(self, node, nid, parent_id):
        self._node(nid, type(node).__name__)
        if parent_id:
            self._edge(parent_id, nid)

    # ── Node-specific renderers ───────────────────────────────────────────────

    def _dot_Program(self, node: Program, nid, parent_id):
        self._node(nid, 'Program', '#1e66f5')
        if parent_id: self._edge(parent_id, nid)
        for s in node.statements:
            self._visit(s, nid)

    def _dot_FuncDecl(self, node: FuncDecl, nid, parent_id):
        params = ', '.join(f"{t} {n}" for t, n in node.params)
        self._node(nid, f"FuncDecl\\n{node.name}({params}): {node.return_type}", '#8839ef')
        if parent_id: self._edge(parent_id, nid)
        self._visit(node.body, nid)

    def _dot_Block(self, node: Block, nid, parent_id):
        self._node(nid, 'Block', '#40a02b')
        if parent_id: self._edge(parent_id, nid)
        for s in node.statements:
            self._visit(s, nid)

    def _dot_VarDecl(self, node: VarDecl, nid, parent_id):
        self._node(nid, f"VarDecl\\n{node.var_type} {node.name}", '#df8e1d')
        if parent_id: self._edge(parent_id, nid)
        if node.initializer:
            cid = self._visit(node.initializer, '')
            self._edge(nid, cid, '=')

    def _dot_ArrayDecl(self, node: ArrayDecl, nid, parent_id):
        self._node(nid, f"ArrayDecl\\narray<{node.element_type}> {node.name}", '#df8e1d')
        if parent_id: self._edge(parent_id, nid)
        sid = self._visit(node.size, '')
        self._edge(nid, sid, 'size')

    def _dot_Assign(self, node: Assign, nid, parent_id):
        lbl = f"Assign\\n{node.name}" + (f"[idx]" if node.index else "")
        self._node(nid, lbl, '#fe640b')
        if parent_id: self._edge(parent_id, nid)
        if node.index:
            iid = self._visit(node.index, '')
            self._edge(nid, iid, 'index')
        vid = self._visit(node.value, '')
        self._edge(nid, vid, 'value')

    def _dot_IfStmt(self, node: IfStmt, nid, parent_id):
        self._node(nid, 'IfStmt', '#d20f39')
        if parent_id: self._edge(parent_id, nid)
        cid = self._visit(node.condition, '')
        self._edge(nid, cid, 'cond')
        tid = self._visit(node.then_branch, '')
        self._edge(nid, tid, 'then')
        if node.else_branch:
            eid = self._visit(node.else_branch, '')
            self._edge(nid, eid, 'else')

    def _dot_WhileStmt(self, node: WhileStmt, nid, parent_id):
        self._node(nid, 'WhileStmt', '#d20f39')
        if parent_id: self._edge(parent_id, nid)
        cid = self._visit(node.condition, '')
        self._edge(nid, cid, 'cond')
        bid = self._visit(node.body, '')
        self._edge(nid, bid, 'body')

    def _dot_ReturnStmt(self, node: ReturnStmt, nid, parent_id):
        self._node(nid, 'Return', '#ea76cb')
        if parent_id: self._edge(parent_id, nid)
        if node.value:
            vid = self._visit(node.value, '')
            self._edge(nid, vid)

    def _dot_PrintStmt(self, node: PrintStmt, nid, parent_id):
        self._node(nid, 'Print', '#ea76cb')
        if parent_id: self._edge(parent_id, nid)
        vid = self._visit(node.value, '')
        self._edge(nid, vid)

    def _dot_ExprStmt(self, node: ExprStmt, nid, parent_id):
        self._node(nid, 'ExprStmt')
        if parent_id: self._edge(parent_id, nid)
        self._visit(node.expr, nid)

    def _dot_BinOp(self, node: BinOp, nid, parent_id):
        self._node(nid, f"BinOp '{node.op}'", '#179299')
        if parent_id: self._edge(parent_id, nid)
        lid = self._visit(node.left, '')
        self._edge(nid, lid, 'L')
        rid = self._visit(node.right, '')
        self._edge(nid, rid, 'R')

    def _dot_UnaryOp(self, node: UnaryOp, nid, parent_id):
        self._node(nid, f"UnaryOp '{node.op}'", '#179299')
        if parent_id: self._edge(parent_id, nid)
        self._visit(node.operand, nid)

    def _dot_Literal(self, node: Literal, nid, parent_id):
        val = repr(node.value) if node.lit_type == 'string' else str(node.value)
        self._node(nid, f"Literal ({node.lit_type})\\n{val}", '#04a5e5')
        if parent_id: self._edge(parent_id, nid)

    def _dot_Identifier(self, node: Identifier, nid, parent_id):
        self._node(nid, f"Identifier\\n{node.name}", '#04a5e5')
        if parent_id: self._edge(parent_id, nid)

    def _dot_FuncCall(self, node: FuncCall, nid, parent_id):
        self._node(nid, f"FuncCall\\n{node.name}()", '#8839ef')
        if parent_id: self._edge(parent_id, nid)
        for i, arg in enumerate(node.args):
            aid = self._visit(arg, '')
            self._edge(nid, aid, f"arg{i+1}")

    def _dot_ArrayAccess(self, node: ArrayAccess, nid, parent_id):
        self._node(nid, f"ArrayAccess\\n{node.name}[...]", '#179299')
        if parent_id: self._edge(parent_id, nid)
        iid = self._visit(node.index, '')
        self._edge(nid, iid, 'idx')


# ── AST → plain-text tree ────────────────────────────────────────────────────

class ASTPrinter:
    def print(self, node: ASTNode, indent: int = 0) -> str:
        lines = []
        self._visit(node, indent, lines)
        return '\n'.join(lines)

    def _visit(self, node, indent, lines):
        prefix = '  ' * indent
        method = f"_print_{type(node).__name__}"
        visitor = getattr(self, method, self._print_default)
        visitor(node, indent, prefix, lines)

    def _print_default(self, node, indent, prefix, lines):
        lines.append(f"{prefix}{type(node).__name__}")
        for attr, val in vars(node).items():
            if isinstance(val, ASTNode):
                lines.append(f"{prefix}  .{attr}:")
                self._visit(val, indent + 2, lines)
            elif isinstance(val, list):
                lines.append(f"{prefix}  .{attr}: [{len(val)} items]")
                for item in val:
                    if isinstance(item, ASTNode):
                        self._visit(item, indent + 2, lines)
            elif attr != 'line':
                lines.append(f"{prefix}  .{attr} = {val!r}")

    def _print_Literal(self, node: Literal, indent, prefix, lines):
        lines.append(f"{prefix}Literal({node.lit_type}) = {node.value!r}")

    def _print_Identifier(self, node: Identifier, indent, prefix, lines):
        lines.append(f"{prefix}Identifier: {node.name}")

    def _print_BinOp(self, node: BinOp, indent, prefix, lines):
        lines.append(f"{prefix}BinOp '{node.op}'")
        lines.append(f"{prefix}  left:")
        self._visit(node.left, indent + 2, lines)
        lines.append(f"{prefix}  right:")
        self._visit(node.right, indent + 2, lines)


# ── CFG → DOT ────────────────────────────────────────────────────────────────

BLOCK_COLORS = {
    'entry':     '#1e66f5',
    'exit':      '#d20f39',
    'condition': '#df8e1d',
    'merge':     '#40a02b',
    'normal':    '#313244',
}


def cfg_to_dot(cfg: CFG) -> str:
    safe_name = cfg.name.replace(' ', '_').replace('(', '').replace(')', '').replace(':', '')
    lines = [
        f'digraph CFG_{safe_name} {{',
        f'  label="CFG: {cfg.name}";',
        '  graph [rankdir=TB fontname="Courier" bgcolor="#1e1e2e"'
        '         labelfontcolor="#cdd6f4" fontcolor="#cdd6f4" fontsize=12];',
        '  node  [shape=record style="filled,rounded" fontname="Courier" fontsize=9'
        '         fontcolor="#cdd6f4" color="#89b4fa"];',
        '  edge  [color="#6c7086" arrowsize=0.8 fontcolor="#a6adc8" fontsize=8];',
    ]

    def _esc(s: str) -> str:
        """Escape characters special to DOT record labels."""
        return (s.replace('\\', '\\\\')
                 .replace('"', '\\"')
                 .replace('{', '\\{')
                 .replace('}', '\\}')
                 .replace('<', '\\<')
                 .replace('>', '\\>')
                 .replace('|', '\\|'))

    for bb in cfg.blocks:
        color = BLOCK_COLORS.get(bb.block_type, '#313244')
        stmts_str = '\\l'.join(_esc(s) for s in bb.statements) + ('\\l' if bb.statements else '')
        header = _esc(f"BB{bb.id}: {bb.label}")
        label = f"{{{header}|{stmts_str}}}" if stmts_str else f"{{{header}}}"
        lines.append(f'  bb{bb.id} [label="{label}" fillcolor="{color}"];')

    seen_edges = set()
    for bb in cfg.blocks:
        for succ in bb.successors:
            key = (bb.id, succ.id)
            if key not in seen_edges:
                seen_edges.add(key)
                # Label true/false for condition blocks
                lbl = ''
                if bb.block_type == 'condition':
                    idx = bb.successors.index(succ)
                    lbl = ' [label="T"]' if idx == 0 else ' [label="F"]'
                lines.append(f'  bb{bb.id} -> bb{succ.id}{lbl};')

    lines.append('}')
    return '\n'.join(lines)


def all_cfgs_to_dot(cfgs: Dict[str, CFG]) -> Dict[str, str]:
    return {name: cfg_to_dot(cfg) for name, cfg in cfgs.items()}
