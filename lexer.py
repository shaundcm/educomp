"""
EduComp Lexer (Tokenizer)
Converts raw source code into a stream of tokens.
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional


class TokenType(Enum):
    # Literals
    INTEGER    = auto()
    FLOAT      = auto()
    STRING     = auto()
    BOOL       = auto()

    # Identifiers & Keywords
    IDENTIFIER = auto()
    INT        = auto()
    FLOAT_KW   = auto()
    BOOL_KW    = auto()
    STRING_KW  = auto()
    IF         = auto()
    ELSE       = auto()
    WHILE      = auto()
    FUNC       = auto()
    RETURN     = auto()
    TRUE       = auto()
    FALSE      = auto()
    ARRAY      = auto()
    PRINT      = auto()

    # Operators
    PLUS       = auto()
    MINUS      = auto()
    STAR       = auto()
    SLASH      = auto()
    PERCENT    = auto()
    EQ         = auto()
    NEQ        = auto()
    LT         = auto()
    LTE        = auto()
    GT         = auto()
    GTE        = auto()
    AND        = auto()
    OR         = auto()
    NOT        = auto()
    ASSIGN     = auto()

    # Delimiters
    LPAREN     = auto()
    RPAREN     = auto()
    LBRACE     = auto()
    RBRACE     = auto()
    LBRACKET   = auto()
    RBRACKET   = auto()
    SEMICOLON  = auto()
    COMMA      = auto()
    COLON      = auto()

    # Special
    EOF        = auto()
    UNKNOWN    = auto()


KEYWORDS = {
    'int':    TokenType.INT,
    'float':  TokenType.FLOAT_KW,
    'bool':   TokenType.BOOL_KW,
    'string': TokenType.STRING_KW,
    'if':     TokenType.IF,
    'else':   TokenType.ELSE,
    'while':  TokenType.WHILE,
    'func':   TokenType.FUNC,
    'return': TokenType.RETURN,
    'true':   TokenType.TRUE,
    'false':  TokenType.FALSE,
    'array':  TokenType.ARRAY,
    'print':  TokenType.PRINT,
}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:C{self.col})"


class LexerError(Exception):
    def __init__(self, message: str, line: int, col: int):
        super().__init__(message)
        self.line = line
        self.col = col


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.errors: List[str] = []

    def _current(self) -> Optional[str]:
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def _peek(self, offset=1) -> Optional[str]:
        p = self.pos + offset
        if p < len(self.source):
            return self.source[p]
        return None

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_whitespace_and_comments(self):
        while self.pos < len(self.source):
            ch = self._current()
            if ch in (' ', '\t', '\r', '\n'):
                self._advance()
            elif ch == '/' and self._peek() == '/':
                while self.pos < len(self.source) and self._current() != '\n':
                    self._advance()
            elif ch == '/' and self._peek() == '*':
                self._advance(); self._advance()
                while self.pos < len(self.source):
                    if self._current() == '*' and self._peek() == '/':
                        self._advance(); self._advance()
                        break
                    self._advance()
            else:
                break

    def _read_number(self) -> Token:
        start_line, start_col = self.line, self.col
        num = ''
        is_float = False
        while self._current() and self._current().isdigit():
            num += self._advance()
        if self._current() == '.' and self._peek() and self._peek().isdigit():
            is_float = True
            num += self._advance()
            while self._current() and self._current().isdigit():
                num += self._advance()
        ttype = TokenType.FLOAT if is_float else TokenType.INTEGER
        return Token(ttype, num, start_line, start_col)

    def _read_string(self) -> Token:
        start_line, start_col = self.line, self.col
        self._advance()  # opening "
        s = ''
        while self._current() and self._current() != '"':
            if self._current() == '\\':
                self._advance()
                esc = self._advance()
                s += {'n': '\n', 't': '\t', '"': '"', '\\': '\\'}.get(esc, esc)
            else:
                s += self._advance()
        if self._current() == '"':
            self._advance()
        else:
            self.errors.append(f"L{start_line}:{start_col} - Unterminated string literal")
        return Token(TokenType.STRING, s, start_line, start_col)

    def _read_identifier(self) -> Token:
        start_line, start_col = self.line, self.col
        ident = ''
        while self._current() and (self._current().isalnum() or self._current() == '_'):
            ident += self._advance()
        ttype = KEYWORDS.get(ident, TokenType.IDENTIFIER)
        # Map true/false to BOOL literal type for convenience
        if ttype in (TokenType.TRUE, TokenType.FALSE):
            return Token(TokenType.BOOL, ident, start_line, start_col)
        return Token(ttype, ident, start_line, start_col)

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while True:
            self._skip_whitespace_and_comments()
            if self.pos >= len(self.source):
                tokens.append(Token(TokenType.EOF, '', self.line, self.col))
                break
            ch = self._current()
            line, col = self.line, self.col

            if ch.isdigit():
                tokens.append(self._read_number())
            elif ch == '"':
                tokens.append(self._read_string())
            elif ch.isalpha() or ch == '_':
                tokens.append(self._read_identifier())
            else:
                self._advance()
                two = ch + (self._current() or '')
                if two == '==':   self._advance(); tokens.append(Token(TokenType.EQ,   '==', line, col))
                elif two == '!=': self._advance(); tokens.append(Token(TokenType.NEQ,  '!=', line, col))
                elif two == '<=': self._advance(); tokens.append(Token(TokenType.LTE,  '<=', line, col))
                elif two == '>=': self._advance(); tokens.append(Token(TokenType.GTE,  '>=', line, col))
                elif two == '&&': self._advance(); tokens.append(Token(TokenType.AND,  '&&', line, col))
                elif two == '||': self._advance(); tokens.append(Token(TokenType.OR,   '||', line, col))
                elif ch == '+':   tokens.append(Token(TokenType.PLUS,      '+', line, col))
                elif ch == '-':   tokens.append(Token(TokenType.MINUS,     '-', line, col))
                elif ch == '*':   tokens.append(Token(TokenType.STAR,      '*', line, col))
                elif ch == '/':   tokens.append(Token(TokenType.SLASH,     '/', line, col))
                elif ch == '%':   tokens.append(Token(TokenType.PERCENT,   '%', line, col))
                elif ch == '<':   tokens.append(Token(TokenType.LT,        '<', line, col))
                elif ch == '>':   tokens.append(Token(TokenType.GT,        '>', line, col))
                elif ch == '=':   tokens.append(Token(TokenType.ASSIGN,    '=', line, col))
                elif ch == '!':   tokens.append(Token(TokenType.NOT,       '!', line, col))
                elif ch == '(':   tokens.append(Token(TokenType.LPAREN,    '(', line, col))
                elif ch == ')':   tokens.append(Token(TokenType.RPAREN,    ')', line, col))
                elif ch == '{':   tokens.append(Token(TokenType.LBRACE,    '{', line, col))
                elif ch == '}':   tokens.append(Token(TokenType.RBRACE,    '}', line, col))
                elif ch == '[':   tokens.append(Token(TokenType.LBRACKET,  '[', line, col))
                elif ch == ']':   tokens.append(Token(TokenType.RBRACKET,  ']', line, col))
                elif ch == ';':   tokens.append(Token(TokenType.SEMICOLON, ';', line, col))
                elif ch == ',':   tokens.append(Token(TokenType.COMMA,     ',', line, col))
                elif ch == ':':   tokens.append(Token(TokenType.COLON,     ':', line, col))
                else:
                    self.errors.append(f"L{line}:{col} - Unknown character: {ch!r}")
                    tokens.append(Token(TokenType.UNKNOWN, ch, line, col))

        return tokens
