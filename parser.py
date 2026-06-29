"""
EduComp Parser
Recursive-descent parser that builds an AST from the token stream.
Includes error recovery so compilation can continue after syntax errors.
"""

from typing import List, Optional
from lexer import Token, TokenType
from ast_nodes import *


class ParseError(Exception):
    def __init__(self, message: str, token: Token):
        super().__init__(message)
        self.token = token


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.errors: List[str] = []

    # ── Token navigation ──────────────────────────────────────────────────────

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _peek(self, offset=1) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _check(self, *types: TokenType) -> bool:
        return self._current().type in types

    def _match(self, *types: TokenType) -> Optional[Token]:
        if self._check(*types):
            return self._advance()
        return None

    def _expect(self, ttype: TokenType, msg: str) -> Token:
        if self._check(ttype):
            return self._advance()
        tok = self._current()
        err = f"L{tok.line}:{tok.col} - {msg} (got {tok.value!r})"
        self.errors.append(err)
        raise ParseError(err, tok)

    # ── Error recovery: skip to next synchronisation point ───────────────────

    def _synchronize(self):
        """Skip tokens until we find a likely statement start or block end."""
        sync_types = {
            TokenType.SEMICOLON, TokenType.RBRACE,
            TokenType.IF, TokenType.WHILE, TokenType.FUNC,
            TokenType.RETURN, TokenType.INT, TokenType.FLOAT_KW,
            TokenType.BOOL_KW, TokenType.STRING_KW, TokenType.ARRAY,
            TokenType.PRINT, TokenType.EOF,
        }
        while not self._check(TokenType.EOF):
            if self._current().type in sync_types:
                if self._current().type == TokenType.SEMICOLON:
                    self._advance()
                return
            self._advance()

    # ── Top-level ─────────────────────────────────────────────────────────────

    def parse(self) -> Program:
        stmts = []
        while not self._check(TokenType.EOF):
            try:
                stmts.append(self._parse_top_level())
            except ParseError:
                self._synchronize()
        return Program(stmts)

    def _parse_top_level(self) -> ASTNode:
        if self._check(TokenType.FUNC):
            return self._parse_func_decl()
        return self._parse_statement()

    # ── Declarations ──────────────────────────────────────────────────────────

    def _parse_func_decl(self) -> FuncDecl:
        line = self._current().line
        self._expect(TokenType.FUNC, "Expected 'func'")
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected function name")
        self._expect(TokenType.LPAREN, "Expected '(' after function name")

        params = []
        if not self._check(TokenType.RPAREN):
            params = self._parse_param_list()
        self._expect(TokenType.RPAREN, "Expected ')' after parameters")

        return_type = 'void'
        if self._match(TokenType.COLON):
            return_type = self._parse_type()

        body = self._parse_block()
        return FuncDecl(name_tok.value, params, return_type, body, line)

    def _parse_param_list(self) -> List[tuple]:
        params = []
        ptype = self._parse_type()
        pname = self._expect(TokenType.IDENTIFIER, "Expected parameter name").value
        params.append((ptype, pname))
        while self._match(TokenType.COMMA):
            ptype = self._parse_type()
            pname = self._expect(TokenType.IDENTIFIER, "Expected parameter name").value
            params.append((ptype, pname))
        return params

    def _parse_type(self) -> str:
        type_map = {
            TokenType.INT:       'int',
            TokenType.FLOAT_KW:  'float',
            TokenType.BOOL_KW:   'bool',
            TokenType.STRING_KW: 'string',
        }
        tok = self._current()
        if tok.type in type_map:
            self._advance()
            return type_map[tok.type]
        err = f"L{tok.line}:{tok.col} - Expected type keyword, got {tok.value!r}"
        self.errors.append(err)
        raise ParseError(err, tok)

    def _parse_var_decl(self) -> ASTNode:
        line = self._current().line
        if self._check(TokenType.ARRAY):
            return self._parse_array_decl()
        vtype = self._parse_type()
        name = self._expect(TokenType.IDENTIFIER, "Expected variable name").value
        init = None
        if self._match(TokenType.ASSIGN):
            init = self._parse_expr()
        self._expect(TokenType.SEMICOLON, "Expected ';' after variable declaration")
        return VarDecl(vtype, name, init, line)

    def _parse_array_decl(self) -> ArrayDecl:
        line = self._current().line
        self._expect(TokenType.ARRAY, "Expected 'array'")
        self._expect(TokenType.LT, "Expected '<' after 'array'")
        elem_type = self._parse_type()
        self._expect(TokenType.GT, "Expected '>' after element type")
        name = self._expect(TokenType.IDENTIFIER, "Expected array name").value
        self._expect(TokenType.LBRACKET, "Expected '[' for array size")
        size = self._parse_expr()
        self._expect(TokenType.RBRACKET, "Expected ']' after array size")
        init = None
        if self._match(TokenType.ASSIGN):
            self._expect(TokenType.LBRACE, "Expected '{' for array initializer")
            init = []
            if not self._check(TokenType.RBRACE):
                init.append(self._parse_expr())
                while self._match(TokenType.COMMA):
                    init.append(self._parse_expr())
            self._expect(TokenType.RBRACE, "Expected '}' after array initializer")
        self._expect(TokenType.SEMICOLON, "Expected ';' after array declaration")
        return ArrayDecl(elem_type, name, size, init, line)

    # ── Statements ────────────────────────────────────────────────────────────

    def _parse_statement(self) -> ASTNode:
        try:
            tok = self._current()

            if self._check(TokenType.INT, TokenType.FLOAT_KW,
                           TokenType.BOOL_KW, TokenType.STRING_KW):
                return self._parse_var_decl()

            if self._check(TokenType.ARRAY):
                return self._parse_array_decl()

            if self._check(TokenType.IF):
                return self._parse_if()

            if self._check(TokenType.WHILE):
                return self._parse_while()

            if self._check(TokenType.RETURN):
                return self._parse_return()

            if self._check(TokenType.PRINT):
                return self._parse_print()

            if self._check(TokenType.LBRACE):
                return self._parse_block()

            # Assignment or expression statement
            return self._parse_assign_or_expr()

        except ParseError:
            self._synchronize()
            return ExprStmt(Literal(None, 'int'))   # placeholder

    def _parse_block(self) -> Block:
        self._expect(TokenType.LBRACE, "Expected '{'")
        stmts = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            try:
                stmts.append(self._parse_statement())
            except ParseError:
                self._synchronize()
        self._expect(TokenType.RBRACE, "Expected '}'")
        return Block(stmts)

    def _parse_if(self) -> IfStmt:
        line = self._current().line
        self._expect(TokenType.IF, "Expected 'if'")
        self._expect(TokenType.LPAREN, "Expected '(' after 'if'")
        cond = self._parse_expr()
        self._expect(TokenType.RPAREN, "Expected ')' after condition")
        then_b = self._parse_block()
        else_b = None
        if self._match(TokenType.ELSE):
            else_b = self._parse_block()
        return IfStmt(cond, then_b, else_b, line)

    def _parse_while(self) -> WhileStmt:
        line = self._current().line
        self._expect(TokenType.WHILE, "Expected 'while'")
        self._expect(TokenType.LPAREN, "Expected '(' after 'while'")
        cond = self._parse_expr()
        self._expect(TokenType.RPAREN, "Expected ')' after condition")
        body = self._parse_block()
        return WhileStmt(cond, body, line)

    def _parse_return(self) -> ReturnStmt:
        line = self._current().line
        self._expect(TokenType.RETURN, "Expected 'return'")
        val = None
        if not self._check(TokenType.SEMICOLON):
            val = self._parse_expr()
        self._expect(TokenType.SEMICOLON, "Expected ';' after return")
        return ReturnStmt(val, line)

    def _parse_print(self) -> PrintStmt:
        line = self._current().line
        self._expect(TokenType.PRINT, "Expected 'print'")
        self._expect(TokenType.LPAREN, "Expected '(' after 'print'")
        val = self._parse_expr()
        self._expect(TokenType.RPAREN, "Expected ')' after print argument")
        self._expect(TokenType.SEMICOLON, "Expected ';' after print")
        return PrintStmt(val, line)

    def _parse_assign_or_expr(self) -> ASTNode:
        line = self._current().line
        # Look-ahead: IDENTIFIER [ = | [ ... ] = ]
        if (self._check(TokenType.IDENTIFIER) and
                self._peek().type == TokenType.ASSIGN):
            name = self._advance().value
            self._advance()  # consume '='
            val = self._parse_expr()
            self._expect(TokenType.SEMICOLON, "Expected ';' after assignment")
            return Assign(name, val, None, line)

        if (self._check(TokenType.IDENTIFIER) and
                self._peek().type == TokenType.LBRACKET):
            name = self._advance().value
            self._advance()  # consume '['
            idx = self._parse_expr()
            self._expect(TokenType.RBRACKET, "Expected ']'")
            if self._match(TokenType.ASSIGN):
                val = self._parse_expr()
                self._expect(TokenType.SEMICOLON, "Expected ';' after array assignment")
                return Assign(name, val, idx, line)
            # Otherwise treat as expression starting with array access
            expr = ArrayAccess(name, idx, line)
            self._expect(TokenType.SEMICOLON, "Expected ';' after expression")
            return ExprStmt(expr, line)

        expr = self._parse_expr()
        self._expect(TokenType.SEMICOLON, "Expected ';' after expression")
        return ExprStmt(expr, line)

    # ── Expressions (Pratt / precedence climbing) ─────────────────────────────

    def _parse_expr(self) -> ASTNode:
        return self._parse_or()

    def _parse_or(self) -> ASTNode:
        left = self._parse_and()
        while self._match(TokenType.OR):
            right = self._parse_and()
            left = BinOp('||', left, right)
        return left

    def _parse_and(self) -> ASTNode:
        left = self._parse_equality()
        while self._match(TokenType.AND):
            right = self._parse_equality()
            left = BinOp('&&', left, right)
        return left

    def _parse_equality(self) -> ASTNode:
        left = self._parse_comparison()
        while self._check(TokenType.EQ, TokenType.NEQ):
            op = self._advance().value
            right = self._parse_comparison()
            left = BinOp(op, left, right)
        return left

    def _parse_comparison(self) -> ASTNode:
        left = self._parse_addition()
        while self._check(TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE):
            op = self._advance().value
            right = self._parse_addition()
            left = BinOp(op, left, right)
        return left

    def _parse_addition(self) -> ASTNode:
        left = self._parse_multiplication()
        while self._check(TokenType.PLUS, TokenType.MINUS):
            op = self._advance().value
            right = self._parse_multiplication()
            left = BinOp(op, left, right)
        return left

    def _parse_multiplication(self) -> ASTNode:
        left = self._parse_unary()
        while self._check(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self._advance().value
            right = self._parse_unary()
            left = BinOp(op, left, right)
        return left

    def _parse_unary(self) -> ASTNode:
        if self._check(TokenType.NOT):
            op = self._advance().value
            operand = self._parse_unary()
            return UnaryOp(op, operand)
        if self._check(TokenType.MINUS):
            op = self._advance().value
            operand = self._parse_unary()
            return UnaryOp('-', operand)
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        tok = self._current()

        if tok.type == TokenType.INTEGER:
            self._advance()
            return Literal(int(tok.value), 'int', tok.line)

        if tok.type == TokenType.FLOAT:
            self._advance()
            return Literal(float(tok.value), 'float', tok.line)

        if tok.type == TokenType.STRING:
            self._advance()
            return Literal(tok.value, 'string', tok.line)

        if tok.type == TokenType.BOOL:
            self._advance()
            return Literal(tok.value == 'true', 'bool', tok.line)

        if tok.type == TokenType.IDENTIFIER:
            name = self._advance().value
            # Function call
            if self._match(TokenType.LPAREN):
                args = []
                if not self._check(TokenType.RPAREN):
                    args.append(self._parse_expr())
                    while self._match(TokenType.COMMA):
                        args.append(self._parse_expr())
                self._expect(TokenType.RPAREN, "Expected ')' after arguments")
                return FuncCall(name, args, tok.line)
            # Array access
            if self._match(TokenType.LBRACKET):
                idx = self._parse_expr()
                self._expect(TokenType.RBRACKET, "Expected ']'")
                return ArrayAccess(name, idx, tok.line)
            return Identifier(name, tok.line)

        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenType.RPAREN, "Expected ')'")
            return expr

        err = f"L{tok.line}:{tok.col} - Unexpected token {tok.value!r} in expression"
        self.errors.append(err)
        raise ParseError(err, tok)
