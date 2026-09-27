"""
evaluator.py
Tokenizes and evaluates calculator expressions such as:
    "sin(30) + 5^2"
    "log(1000) * (3 + 4)"
    "sqrt(2) / 3"
Every numeric operation is performed via Decimal100 (base-100 engine).
Trig functions respect a degrees/radians mode flag.
"""

import re
from decimal100 import (Decimal100, PI, E, _sin, _cos, _tan, _asin, _acos, _atan,
                         _sinh, _cosh, _tanh, _asinh, _acosh, _atanh,
                         _ln, _log10, _log_base, _exp, _power, _factorial)

TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<num>\d+\.?\d*|\.\d+)
      | (?P<ident>[A-Za-z_][A-Za-z_0-9]*)
      | (?P<op>\*\*|[+\-*/^%(),!])
    )
""", re.VERBOSE)

FUNC1 = {"sin", "cos", "tan", "asin", "acos", "atan",
          "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
          "ln", "log", "log10", "sqrt", "cbrt", "exp", "abs"}
CONSTANTS = {"pi": PI, "e": E}


class EvalError(Exception):
    pass


def tokenize(s):
    tokens = []
    pos = 0
    while pos < len(s):
        m = TOKEN_RE.match(s, pos)
        if not m or m.end() == pos:
            if s[pos].isspace():
                pos += 1
                continue
            raise EvalError(f"Unexpected character: {s[pos]!r}")
        pos = m.end()
        if m.group("num"):
            tokens.append(("num", m.group("num")))
        elif m.group("ident"):
            tokens.append(("ident", m.group("ident")))
        elif m.group("op"):
            tokens.append(("op", m.group("op")))
    return tokens


class Parser:
    """Recursive-descent parser / evaluator.
    Grammar (highest to lowest precedence):
        primary   := NUMBER | IDENT | IDENT '(' expr ')' | '(' expr ')' | '-' unary
        postfix   := primary ('!')*
        power     := postfix ('^' unary)?         (right-assoc)
        term      := power (('*'|'/'|'%') power)*
        expr      := term (('+'|'-') term)*
    """

    def __init__(self, tokens, angle_mode="deg"):
        self.tokens = tokens
        self.pos = 0
        self.angle_mode = angle_mode  # "deg" or "rad"

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def advance(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def expect_op(self, val):
        kind, v = self.peek()
        if kind == "op" and v == val:
            self.advance()
            return True
        return False

    # ---------------- grammar ----------------
    def parse(self):
        result = self.expr()
        if self.pos != len(self.tokens):
            raise EvalError("Unexpected trailing input")
        return result

    def expr(self):
        val = self.term()
        while True:
            kind, v = self.peek()
            if kind == "op" and v in ("+", "-"):
                self.advance()
                rhs = self.term()
                val = val.add(rhs) if v == "+" else val.sub(rhs)
            else:
                break
        return val

    def term(self):
        val = self.power()
        while True:
            kind, v = self.peek()
            if kind == "op" and v in ("*", "/", "%"):
                self.advance()
                rhs = self.power()
                if v == "*":
                    val = val.mul(rhs)
                elif v == "/":
                    val = val.div(rhs)
                else:
                    val = val.mod(rhs)
            else:
                break
        return val

    def power(self):
        base = self.postfix()
        kind, v = self.peek()
        if kind == "op" and v in ("^", "**"):
            self.advance()
            exponent = self.unary()  # right-associative
            base = self._apply_power(base, exponent)
        return base

    def _apply_power(self, base, exponent):
        # exact integer power when possible, else exp(y*ln(x))
        exp_str = exponent.to_string(30)
        if "." not in exp_str:
            n = int(exp_str)
            return base.ipow(n)
        return _power(base, exponent)

    def postfix(self):
        val = self.unary()
        while True:
            kind, v = self.peek()
            if kind == "op" and v == "!":
                self.advance()
                n_str = val.to_string(15)
                if "." in n_str or float(n_str) < 0:
                    raise EvalError("factorial requires a non-negative integer")
                val = _factorial(int(n_str))
            else:
                break
        return val

    def unary(self):
        kind, v = self.peek()
        if kind == "op" and v == "-":
            self.advance()
            return self.unary().neg_()
        if kind == "op" and v == "+":
            self.advance()
            return self.unary()
        return self.primary()

    def primary(self):
        kind, v = self.advance()
        if kind == "num":
            return Decimal100.from_string(v)
        if kind == "op" and v == "(":
            val = self.expr()
            if not self.expect_op(")"):
                raise EvalError("Expected ')'")
            return val
        if kind == "ident":
            name = v.lower()
            if name in CONSTANTS:
                return CONSTANTS[name]
            if name in FUNC1:
                if not self.expect_op("("):
                    raise EvalError(f"Expected '(' after {name}")
                # support log(x, base)
                arg = self.expr()
                second_arg = None
                kind2, v2 = self.peek()
                if kind2 == "op" and v2 == ",":
                    self.advance()
                    second_arg = self.expr()
                if not self.expect_op(")"):
                    raise EvalError("Expected ')'")
                return self._apply_func(name, arg, second_arg)
            raise EvalError(f"Unknown identifier: {name}")
        raise EvalError(f"Unexpected token: {kind} {v}")

    def _apply_func(self, name, arg, second_arg):
        to_rad = (lambda a: a.mul(PI).div(Decimal100.from_int(180))) if self.angle_mode == "deg" else (lambda a: a)
        from_rad = (lambda a: a.mul(Decimal100.from_int(180)).div(PI)) if self.angle_mode == "deg" else (lambda a: a)

        if name == "sin":
            return _sin(to_rad(arg))
        if name == "cos":
            return _cos(to_rad(arg))
        if name == "tan":
            return _tan(to_rad(arg))
        if name == "asin":
            return from_rad(_asin(arg))
        if name == "acos":
            return from_rad(_acos(arg))
        if name == "atan":
            return from_rad(_atan(arg))
        if name == "sinh":
            return _sinh(arg)
        if name == "cosh":
            return _cosh(arg)
        if name == "tanh":
            return _tanh(arg)
        if name == "asinh":
            return _asinh(arg)
        if name == "acosh":
            return _acosh(arg)
        if name == "atanh":
            return _atanh(arg)
        if name == "ln":
            return _ln(arg)
        if name in ("log", "log10"):
            if second_arg is not None:
                return _log_base(arg, second_arg)
            return _log10(arg)
        if name == "sqrt":
            return arg.sqrt()
        if name == "cbrt":
            return arg.nth_root(3)
        if name == "exp":
            return _exp(arg)
        if name == "abs":
            return arg.abs()
        raise EvalError(f"Unhandled function: {name}")


def evaluate(expression, angle_mode="deg"):
    """Evaluate a full expression string and return a Decimal100 result."""
    tokens = tokenize(expression)
    if not tokens:
        raise EvalError("Empty expression")
    parser = Parser(tokens, angle_mode=angle_mode)
    return parser.parse()
