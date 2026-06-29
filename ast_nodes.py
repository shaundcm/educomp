"""
EduComp AST Node Definitions
All AST node types used by the parser and semantic analyser.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any


# ── Base ──────────────────────────────────────────────────────────────────────

class ASTNode:
    """Base class for every AST node."""
    pass


# ── Statements ────────────────────────────────────────────────────────────────

@dataclass
class Program(ASTNode):
    statements: List[ASTNode]


@dataclass
class VarDecl(ASTNode):
    var_type: str          # 'int' | 'float' | 'bool' | 'string'
    name: str
    initializer: Optional[ASTNode]
    line: int = 0


@dataclass
class ArrayDecl(ASTNode):
    element_type: str
    name: str
    size: ASTNode          # expression for size
    initializer: Optional[List[ASTNode]]
    line: int = 0


@dataclass
class Assign(ASTNode):
    name: str
    value: ASTNode
    index: Optional[ASTNode] = None   # for array element assignment
    line: int = 0


@dataclass
class IfStmt(ASTNode):
    condition: ASTNode
    then_branch: 'Block'
    else_branch: Optional['Block']
    line: int = 0


@dataclass
class WhileStmt(ASTNode):
    condition: ASTNode
    body: 'Block'
    line: int = 0


@dataclass
class ReturnStmt(ASTNode):
    value: Optional[ASTNode]
    line: int = 0


@dataclass
class PrintStmt(ASTNode):
    value: ASTNode
    line: int = 0


@dataclass
class Block(ASTNode):
    statements: List[ASTNode]


@dataclass
class FuncDecl(ASTNode):
    name: str
    params: List[tuple]   # list of (type_str, param_name)
    return_type: str      # 'int' | 'float' | 'bool' | 'string' | 'void'
    body: Block
    line: int = 0


@dataclass
class ExprStmt(ASTNode):
    expr: ASTNode
    line: int = 0


# ── Expressions ───────────────────────────────────────────────────────────────

@dataclass
class BinOp(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode
    line: int = 0


@dataclass
class UnaryOp(ASTNode):
    op: str
    operand: ASTNode
    line: int = 0


@dataclass
class Literal(ASTNode):
    value: Any
    lit_type: str         # 'int' | 'float' | 'bool' | 'string'
    line: int = 0


@dataclass
class Identifier(ASTNode):
    name: str
    line: int = 0


@dataclass
class FuncCall(ASTNode):
    name: str
    args: List[ASTNode]
    line: int = 0


@dataclass
class ArrayAccess(ASTNode):
    name: str
    index: ASTNode
    line: int = 0
