"""Validator decorator + module-level VALIDATORS registry.

A validator is a `Callable[[Design], Iterable[Issue]]`. Decorate
with `@validator` to register; consumers run them via
`design.validate()`.
"""
from __future__ import annotations

from typing import Callable


# Module-level registry: a validator is `Callable[[Design], Iterable[Issue]]`.
# Append to this list to register a new check (or call
# `design.validate(extra=[my_check])`).
VALIDATORS: list = []


def validator(fn: Callable) -> Callable:
    """Decorator: register `fn` as a Design-level validator. The
    function takes a Design and yields/returns Issue objects."""
    VALIDATORS.append(fn)
    return fn
