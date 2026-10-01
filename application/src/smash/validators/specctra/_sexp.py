"""S-expression tokenizer + parser for Specctra DSN files.

DSN uses a LISP-like syntax:
  (pcb "name"
    (parser
      (string_quote ")
      (host_cad "KiCad's Pcbnew"))
    (resolution um 10)
    ...)

Output is nested Python lists with strings and numbers as atoms:
  ["pcb", "name", ["parser", ["string_quote", "\""], ["host_cad", "KiCad's Pcbnew"]], ["resolution", "um", "10"], ...]

Notes:
  - The `(string_quote ")` metadata declaration carries a single literal
    `"` character that confuses naive tokenizers; we strip it (matching
    the TS reference implementation).
  - All atoms are returned as strings — the interpreters convert to
    int/float as needed.
"""

from __future__ import annotations

import re


def parse_sexp(text: str) -> list:
    """Parse a DSN s-expression into nested lists. Returns the top-
    level list (typically ['pcb', name, [section, ...], ...]).

    Raises ValueError on tokenization or balance errors.
    """
    # Strip the lone `"` in `(string_quote ")` so the tokenizer's quote
    # state stays consistent. Matches the TS reference implementation.
    text = re.sub(r"\(string_quote\s+.\s*\)", "", text)

    tokens = _tokenize(text)
    pos = [0]   # mutable cursor for the recursive parser

    def _read_list() -> list:
        if pos[0] >= len(tokens) or tokens[pos[0]] != "(":
            raise ValueError(
                f"expected '(' at token {pos[0]}, got "
                f"{tokens[pos[0]] if pos[0] < len(tokens) else 'EOF'}"
            )
        pos[0] += 1
        items: list = []
        while pos[0] < len(tokens):
            tok = tokens[pos[0]]
            if tok == ")":
                pos[0] += 1
                return items
            if tok == "(":
                items.append(_read_list())
            else:
                pos[0] += 1
                items.append(tok)
        raise ValueError("unexpected EOF inside (...)")

    out = _read_list()
    if pos[0] != len(tokens):
        raise ValueError(
            f"unconsumed tokens after top-level (...): "
            f"{tokens[pos[0]:pos[0]+5]}..."
        )
    return out


def _tokenize(text: str) -> list[str]:
    """Tokenize into '(', ')', and atom strings. Quoted strings keep
    their inner content (without the quotes); unquoted atoms are split
    on whitespace.

    DSN uses double-quote `"` for strings; backslash isn't an escape
    character in this dialect.
    """
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            tokens.append("(")
            i += 1
        elif ch == ")":
            tokens.append(")")
            i += 1
        elif ch == '"':
            # quoted string — read until next unescaped "
            end = text.find('"', i + 1)
            if end == -1:
                raise ValueError(f"unterminated string starting at byte {i}")
            tokens.append(text[i + 1:end])
            i = end + 1
        else:
            # atom — read until whitespace, ( or )
            start = i
            while i < n and not text[i].isspace() and text[i] not in "()\"":
                i += 1
            tokens.append(text[start:i])
    return tokens
