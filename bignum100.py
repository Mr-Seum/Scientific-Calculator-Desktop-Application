"""
bignum100.py
Arbitrary-precision SIGNED INTEGER arithmetic, stored internally in base-100.
Each "digit" is an int in [0, 100), most-significant first.
This is the foundation that Decimal100 (fixed-point decimals) builds on.
"""

import threading

BASE = 100

# A single global cancellation flag. The UI sets this when the user clicks
# "Cancel"; the hot loops below (multiplication, division) check it
# periodically and abort the in-progress calculation cleanly.
CANCEL_EVENT = threading.Event()


class CalculationCancelled(Exception):
    """Raised inside a computation when the user cancels it."""
    pass


def check_cancel():
    if CANCEL_EVENT.is_set():
        raise CalculationCancelled("Calculation cancelled by user")


class BigInt100:
    __slots__ = ("digits", "neg")

    def __init__(self, digits, neg=False):
        # strip leading zero "digits"
        i = 0
        while i < len(digits) - 1 and digits[i] == 0:
            i += 1
        digits = digits[i:]
        if digits == [0]:
            neg = False
        self.digits = digits
        self.neg = neg

    # ---------------- construction ----------------
    @classmethod
    def from_int(cls, n):
        neg = n < 0
        n = abs(n)
        if n == 0:
            return cls([0], False)
        digits = []
        while n > 0:
            digits.append(n % BASE)
            n //= BASE
        digits.reverse()
        return cls(digits, neg)

    @classmethod
    def from_decimal_string(cls, s):
        s = s.strip()
        neg = s.startswith("-")
        if neg:
            s = s[1:]
        s = s.lstrip("0") or "0"
        pad = (-len(s)) % 2
        s = "0" * pad + s
        digits = [int(s[i:i + 2]) for i in range(0, len(s), 2)]
        return cls(digits, neg)

    def to_decimal_string(self):
        s = "".join(str(d).zfill(2) for d in self.digits)
        s = s.lstrip("0") or "0"
        if self.neg and s != "0":
            s = "-" + s
        return s

    def to_int(self):
        return int(self.to_decimal_string())

    def is_zero(self):
        return self.digits == [0]

    # ---------------- comparisons ----------------
    @staticmethod
    def _cmp_mag(a, b):
        if len(a) != len(b):
            return -1 if len(a) < len(b) else 1
        for x, y in zip(a, b):
            if x != y:
                return -1 if x < y else 1
        return 0

    def cmp(self, other):
        if self.neg != other.neg:
            if self.is_zero() and other.is_zero():
                return 0
            return -1 if self.neg else 1
        c = self._cmp_mag(self.digits, other.digits)
        return -c if self.neg else c

    def __eq__(self, other): return self.cmp(other) == 0
    def __lt__(self, other): return self.cmp(other) < 0
    def __le__(self, other): return self.cmp(other) <= 0
    def __gt__(self, other): return self.cmp(other) > 0
    def __ge__(self, other): return self.cmp(other) >= 0

    # ---------------- magnitude add/sub ----------------
    @staticmethod
    def _add_mag(a, b):
        a, b = a[::-1], b[::-1]
        if len(a) < len(b):
            a, b = b, a
        out = []
        carry = 0
        for i in range(len(a)):
            total = a[i] + (b[i] if i < len(b) else 0) + carry
            out.append(total % BASE)
            carry = total // BASE
        if carry:
            out.append(carry)
        out.reverse()
        return out

    @staticmethod
    def _sub_mag(a, b):  # assumes a >= b
        a, b = a[::-1], b[::-1]
        out = []
        borrow = 0
        for i in range(len(a)):
            total = a[i] - (b[i] if i < len(b) else 0) - borrow
            if total < 0:
                total += BASE
                borrow = 1
            else:
                borrow = 0
            out.append(total)
        out.reverse()
        return out

    def __add__(self, other):
        if self.neg == other.neg:
            return BigInt100(self._add_mag(self.digits, other.digits), self.neg)
        c = self._cmp_mag(self.digits, other.digits)
        if c == 0:
            return BigInt100([0], False)
        if c > 0:
            return BigInt100(self._sub_mag(self.digits, other.digits), self.neg)
        return BigInt100(self._sub_mag(other.digits, self.digits), other.neg)

    def __sub__(self, other):
        return self.__add__(BigInt100(other.digits, not other.neg))

    def __neg__(self):
        return BigInt100(self.digits, not self.neg)

    def abs(self):
        return BigInt100(self.digits, False)

    # ---------------- multiplication (schoolbook) ----------------
    def __mul__(self, other):
        a, b = self.digits[::-1], other.digits[::-1]
        n, m = len(a), len(b)
        result = [0] * (n + m)
        for i in range(n):
            if i % 64 == 0:
                check_cancel()
            ai = a[i]
            if ai == 0:
                continue
            carry = 0
            for j in range(m):
                pos = i + j
                total = ai * b[j] + result[pos] + carry
                result[pos] = total % BASE
                carry = total // BASE
            result[i + m] += carry
        result.reverse()
        neg = (self.neg != other.neg)
        return BigInt100(result, neg)

    # ---------------- long division ----------------
    def divmod(self, other):
        if other.is_zero():
            raise ZeroDivisionError("division by zero")
        a, b = self.digits, other.digits
        if self._cmp_mag(a, b) < 0:
            q = BigInt100([0], False)
            r = BigInt100(a[:], self.neg)
            return q, r

        quotient = []
        remainder = []
        for idx, digit in enumerate(a):
            if idx % 32 == 0:
                check_cancel()
            remainder.append(digit)
            while len(remainder) > 1 and remainder[0] == 0:
                remainder.pop(0)
            lo, hi, best = 0, BASE - 1, 0
            while lo <= hi:
                mid = (lo + hi) // 2
                prod = BigInt100._mul_small(b, mid)
                if BigInt100._cmp_mag(prod, remainder) <= 0:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            quotient.append(best)
            if best:
                prod = BigInt100._mul_small(b, best)
                remainder = BigInt100._sub_mag(remainder, prod)
                while len(remainder) > 1 and remainder[0] == 0:
                    remainder.pop(0)

        q_neg = (self.neg != other.neg)
        r_neg = self.neg
        q = BigInt100(quotient, q_neg)
        r = BigInt100(remainder, r_neg)
        return q, r

    @staticmethod
    def _mul_small(digits, small):
        if small == 0:
            return [0]
        a = digits[::-1]
        out = []
        carry = 0
        for d in a:
            total = d * small + carry
            out.append(total % BASE)
            carry = total // BASE
        while carry:
            out.append(carry % BASE)
            carry //= BASE
        out.reverse()
        return out

    def __truediv__(self, other):
        q, _ = self.divmod(other)
        return q

    def __repr__(self):
        return f"BigInt100({self.to_decimal_string()})"
