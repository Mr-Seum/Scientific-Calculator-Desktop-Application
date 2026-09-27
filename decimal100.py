"""
decimal100.py
Fixed-point arbitrary-precision decimal arithmetic built entirely on top of
bignum100.BigInt100 (base-100 integers). Every operation -- including
sin/cos/tan/asin/acos/atan/sinh/cosh/tanh/ln/log10/exp/sqrt/pow/factorial --
is implemented from scratch using this engine (Taylor series / Newton's
method / range reduction), NOT Python's math module.

Python's math module is used in exactly one place: to get a cheap, low-
precision *integer* estimate during range reduction (e.g. "roughly how many
multiples of 2*pi do we need to subtract"). All actual numeric computation
happens via BigInt100.
"""

from bignum100 import BigInt100, check_cancel

SCALE = 30                     # working decimal digits after the point
_UNIT = 10 ** SCALE            # 1.0 represented as this many raw units


def _pow10(n):
    return BigInt100.from_int(10 ** n)


_SCALE_FACTOR = _pow10(SCALE)


class Decimal100:
    __slots__ = ("raw",)  # raw: BigInt100, value = raw / 10**SCALE

    def __init__(self, raw):
        self.raw = raw

    # ---------------- construction ----------------
    @classmethod
    def from_string(cls, s):
        s = s.strip()
        neg = s.startswith("-")
        if neg:
            s = s[1:]
        if "." in s:
            int_part, frac_part = s.split(".")
        else:
            int_part, frac_part = s, ""
        int_part = int_part or "0"
        frac_part = (frac_part + "0" * SCALE)[:SCALE]
        combined = int_part + frac_part
        raw = BigInt100.from_decimal_string(combined)
        if neg:
            raw = -raw
        return cls(raw)

    @classmethod
    def from_int(cls, n):
        return cls(BigInt100.from_int(n) * _SCALE_FACTOR)

    @classmethod
    def zero(cls):
        return cls(BigInt100.from_int(0))

    @classmethod
    def one(cls):
        return cls.from_int(1)

    # ---------------- display ----------------
    def to_string(self, sig_digits=15):
        raw_int = self.raw.to_int()
        neg = raw_int < 0
        raw_int = abs(raw_int)
        if raw_int == 0:
            return "0"

        digit_str = str(raw_int)          # exact digits, no leading zeros
        total_len = len(digit_str)
        int_len = total_len - SCALE       # may be <= 0 (value < 1)

        keep = min(sig_digits, total_len)
        if total_len <= keep:
            rounded_digits = digit_str
            int_len_new = int_len
        else:
            divisor = 10 ** (total_len - keep)
            q, r = divmod(raw_int, divisor)
            if 2 * r >= divisor:
                q += 1
            rounded_digits = str(q)
            if len(rounded_digits) > keep:
                # rounding carried into a new leading digit (e.g. 999->1000)
                rounded_digits = rounded_digits[:keep]
                int_len_new = int_len + 1
            else:
                int_len_new = int_len

        if int_len_new <= 0:
            frac = ("0" * (-int_len_new) + rounded_digits).rstrip("0")
            out = "0" if frac == "" else "0." + frac
        elif int_len_new >= len(rounded_digits):
            out = rounded_digits + "0" * (int_len_new - len(rounded_digits))
        else:
            int_part = rounded_digits[:int_len_new]
            frac_part = rounded_digits[int_len_new:].rstrip("0")
            out = int_part if frac_part == "" else f"{int_part}.{frac_part}"

        return ("-" + out) if (neg and out != "0") else out

    def to_scientific(self, sig_digits=20):
        """Format as d.ddddd...\u00d710^n using exact integer digit rounding
        (same rounding approach as to_string, just formatted differently)."""
        raw_int = self.raw.to_int()
        neg = raw_int < 0
        raw_int = abs(raw_int)
        if raw_int == 0:
            return "0"

        digit_str = str(raw_int)
        total_len = len(digit_str)
        int_len = total_len - SCALE     # exponent of first digit is int_len - 1

        keep = min(sig_digits, total_len)
        if total_len <= keep:
            rounded_digits = digit_str
            exponent = int_len - 1
        else:
            divisor = 10 ** (total_len - keep)
            q, r = divmod(raw_int, divisor)
            if 2 * r >= divisor:
                q += 1
            rounded_digits = str(q)
            exponent = int_len - 1
            if len(rounded_digits) > keep:
                rounded_digits = rounded_digits[:keep]
                exponent += 1

        rounded_digits = rounded_digits.rstrip("0") or "0"
        if len(rounded_digits) == 1:
            mantissa = rounded_digits
        else:
            mantissa = rounded_digits[0] + "." + rounded_digits[1:]

        out = f"{mantissa}\u00d710^{exponent}"
        return ("-" + out) if neg else out

    def to_float(self):
        # ONLY used internally for cheap range-reduction bookkeeping
        return self.raw.to_int() / _UNIT

    # ---------------- comparisons ----------------
    def cmp(self, other):
        return self.raw.cmp(other.raw)

    def __eq__(self, other): return self.cmp(other) == 0
    def __lt__(self, other): return self.cmp(other) < 0
    def __le__(self, other): return self.cmp(other) <= 0
    def __gt__(self, other): return self.cmp(other) > 0
    def __ge__(self, other): return self.cmp(other) >= 0

    def is_zero(self):
        return self.raw.is_zero()

    def abs(self):
        return Decimal100(self.raw.abs())

    def neg_(self):
        return Decimal100(-self.raw)

    # ---------------- core arithmetic ----------------
    def add(self, other):
        return Decimal100(self.raw + other.raw)

    def sub(self, other):
        return Decimal100(self.raw - other.raw)

    def mul(self, other):
        big = self.raw * other.raw           # scale = 2*SCALE
        q, r = big.divmod(_SCALE_FACTOR)      # bring back to scale
        # round half up based on remainder vs half of scale factor
        two_r = r.abs() * BigInt100.from_int(2)
        if two_r.cmp(_SCALE_FACTOR.abs()) >= 0:
            if q.neg:
                q = q - BigInt100.from_int(1)
            else:
                q = q + BigInt100.from_int(1)
        return Decimal100(q)

    def div(self, other):
        if other.is_zero():
            raise ZeroDivisionError("division by zero")
        numerator = self.raw * _SCALE_FACTOR
        q, r = numerator.divmod(other.raw)
        two_r = r.abs() * BigInt100.from_int(2)
        if two_r.cmp(other.raw.abs()) >= 0:
            if q.neg:
                q = q - BigInt100.from_int(1)
            else:
                q = q + BigInt100.from_int(1)
        return Decimal100(q)

    def mod(self, other):
        # a mod b = a - trunc(a/b)*b   (trunc toward zero, like Python's math.fmod)
        div_result = self.div(other)
        truncated_int = div_result.raw.to_int() // _UNIT
        truncated = Decimal100.from_int(truncated_int)
        return self.sub(truncated.mul(other))

    # ---------------- integer power (exact, exponentiation by squaring) ----
    def ipow(self, n):
        if n < 0:
            return Decimal100.one().div(self.ipow(-n))
        result = Decimal100.one()
        base = self
        while n > 0:
            check_cancel()
            if n & 1:
                result = result.mul(base)
            base = base.mul(base)
            n >>= 1
        return result

    # ---------------- sqrt via Newton's method ----------------
    def sqrt(self):
        if self.raw.neg:
            raise ValueError("sqrt of negative number")
        if self.is_zero():
            return Decimal100.zero()
        xf = self.to_float()
        guess = Decimal100.from_string(repr(xf ** 0.5) if xf > 0 else "1")
        two = Decimal100.from_int(2)
        for _ in range(60):
            check_cancel()
            new_guess = guess.add(self.div(guess)).div(two)
            if new_guess.cmp(guess) == 0:
                break
            guess = new_guess
        return guess

    def nth_root(self, n):
        if n == 0:
            raise ValueError("zeroth root undefined")
        neg_result = False
        base = self
        if self.raw.neg:
            if n % 2 == 0:
                raise ValueError("even root of negative number")
            neg_result = True
            base = self.abs()
        result = _exp(_ln(base).div(Decimal100.from_int(n)))
        return result.neg_() if neg_result else result


EPS = Decimal100(BigInt100.from_int(20))  # ~20 * 10^-SCALE, series cutoff


def _small_enough(term):
    return term.abs().cmp(EPS) < 0


# ---------------- constants (hardcoded to >SCALE digits) ----------------
PI = Decimal100.from_string(
    "3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798"
)
E = Decimal100.from_string(
    "2.71828182845904523536028747135266249775724709369995957496696762772407663035354759457138217852516642743"
)
LN2 = Decimal100.from_string(
    "0.69314718055994530941723212145817656807550013436025525412068000949339362196969471560586332699641868754"
)
LN10 = Decimal100.from_string(
    "2.30258509299404568401799145468436420760110148862877297603332790096757260967735248023599720508959820588"
)
TWO_PI = PI.mul(Decimal100.from_int(2))
HALF_PI = PI.div(Decimal100.from_int(2))


# ---------------- exp(x) via range reduction + Taylor series ----------------
def _exp(x):
    if x.is_zero():
        return Decimal100.one()
    xf = x.to_float()
    # choose k so that |x / 2^k| < 0.5   (cheap float estimate only)
    k = 0
    ax = abs(xf)
    while ax > 0.5:
        ax /= 2
        k += 1
    xr = x
    two = Decimal100.from_int(2)
    for _ in range(k):
        xr = xr.div(two)

    term = Decimal100.one()
    total = Decimal100.one()
    n = 1
    while n < 300:
        check_cancel()
        term = term.mul(xr).div(Decimal100.from_int(n))
        total = total.add(term)
        if _small_enough(term):
            break
        n += 1

    for _ in range(k):
        total = total.mul(total)
    return total


# ---------------- ln(x) via range reduction (x = m * 2^k) + series ----------
def _ln(x):
    if x.raw.neg or x.is_zero():
        raise ValueError("ln domain error")
    xf = x.to_float()
    k = 0
    m = x
    two = Decimal100.from_int(2)
    if xf >= 2:
        while m.to_float() >= 2:
            m = m.div(two)
            k += 1
    elif xf < 1:
        while m.to_float() < 1:
            m = m.mul(two)
            k -= 1

    # ln(m) via atanh-style series: y=(m-1)/(m+1); ln(m)=2*(y + y^3/3 + ...)
    y = m.sub(Decimal100.one()).div(m.add(Decimal100.one()))
    y2 = y.mul(y)
    term = y
    total = y
    n = 1
    while n < 300:
        check_cancel()
        term = term.mul(y2)
        n += 2
        add_term = term.div(Decimal100.from_int(n))
        total = total.add(add_term)
        if _small_enough(add_term):
            break
    ln_m = total.mul(two)
    return ln_m.add(LN2.mul(Decimal100.from_int(k)))


def _log10(x):
    return _ln(x).div(LN10)


def _log_base(x, base):
    return _ln(x).div(_ln(base))


def _power(x, y):
    # x^y = exp(y * ln(x)) for x>0 ; integer y handled exactly elsewhere
    if x.is_zero():
        return Decimal100.zero()
    return _exp(y.mul(_ln(x)))


# ---------------- trig: sin/cos via range reduction + Taylor series -------
def _reduce_angle(x):
    # reduce x to (-pi, pi] using a cheap float estimate for k
    xf = x.to_float()
    two_pi_f = 6.283185307179586
    k = round(xf / two_pi_f)
    if k != 0:
        x = x.sub(TWO_PI.mul(Decimal100.from_int(k)))
    return x


def _sin(x):
    x = _reduce_angle(x)
    term = x
    total = x
    x2 = x.mul(x)
    n = 1
    sign_term = term
    while n < 300:
        check_cancel()
        n += 2
        sign_term = sign_term.mul(x2).div(Decimal100.from_int((n - 1) * n)).neg_()
        total = total.add(sign_term)
        if _small_enough(sign_term):
            break
    return total


def _cos(x):
    x = _reduce_angle(x)
    total = Decimal100.one()
    term = Decimal100.one()
    x2 = x.mul(x)
    n = 0
    while n < 300:
        check_cancel()
        n += 2
        term = term.mul(x2).div(Decimal100.from_int((n - 1) * n)).neg_()
        total = total.add(term)
        if _small_enough(term):
            break
    return total


def _tan(x):
    c = _cos(x)
    if c.is_zero():
        raise ZeroDivisionError("tan undefined here")
    return _sin(x).div(c)


# ---------------- atan via half-angle reduction + series ----------
def _atan_small(x):
    # series, valid best for |x| small
    term = x
    total = x
    x2 = x.mul(x)
    n = 1
    while n < 400:
        check_cancel()
        n += 2
        term = term.mul(x2)
        add_term = term.div(Decimal100.from_int(n))
        if n % 4 == 3:
            total = total.sub(add_term)
        else:
            total = total.add(add_term)
        if _small_enough(add_term):
            break
    return total


def _atan(x):
    if x.is_zero():
        return Decimal100.zero()
    neg = x.raw.neg
    x = x.abs()
    swapped = False
    if x.cmp(Decimal100.one()) > 0:
        x = Decimal100.one().div(x)
        swapped = True
    # halve x using tan half-angle identity until small
    halvings = 0
    one = Decimal100.one()
    while x.to_float() > 0.4142135623730951:  # tan(pi/8)
        check_cancel()
        denom = one.add((one.add(x.mul(x))).sqrt())
        x = x.div(denom)
        halvings += 1
    result = _atan_small(x)
    two = Decimal100.from_int(2)
    for _ in range(halvings):
        result = result.mul(two)
    if swapped:
        result = HALF_PI.sub(result)
    return result.neg_() if neg else result


def _asin(x):
    if x.abs().cmp(Decimal100.one()) > 0:
        raise ValueError("asin domain error")
    if x.cmp(Decimal100.one()) == 0:
        return HALF_PI
    if x.cmp(Decimal100.one().neg_()) == 0:
        return HALF_PI.neg_()
    denom = (Decimal100.one().sub(x.mul(x))).sqrt()
    return _atan(x.div(denom))


def _acos(x):
    return HALF_PI.sub(_asin(x))


# ---------------- hyperbolic ----------
def _sinh(x):
    return _exp(x).sub(_exp(x.neg_())).div(Decimal100.from_int(2))


def _cosh(x):
    return _exp(x).add(_exp(x.neg_())).div(Decimal100.from_int(2))


def _tanh(x):
    ep = _exp(x)
    en = _exp(x.neg_())
    return ep.sub(en).div(ep.add(en))


def _asinh(x):
    return _ln(x.add((x.mul(x).add(Decimal100.one())).sqrt()))


def _acosh(x):
    if x.cmp(Decimal100.one()) < 0:
        raise ValueError("acosh domain error")
    return _ln(x.add((x.mul(x).sub(Decimal100.one())).sqrt()))


def _atanh(x):
    if x.abs().cmp(Decimal100.one()) >= 0:
        raise ValueError("atanh domain error")
    num = Decimal100.one().add(x)
    den = Decimal100.one().sub(x)
    return _ln(num.div(den)).div(Decimal100.from_int(2))


# ---------------- factorial (exact integer) ----------
def _factorial(n_int):
    if n_int < 0:
        raise ValueError("factorial of negative number")
    result = BigInt100.from_int(1)
    for i in range(2, n_int + 1):
        check_cancel()
        result = result * BigInt100.from_int(i)
    return Decimal100(result * _SCALE_FACTOR)


# Public function table used by the UI layer
FUNCTIONS = {
    "sin": _sin, "cos": _cos, "tan": _tan,
    "asin": _asin, "acos": _acos, "atan": _atan,
    "sinh": _sinh, "cosh": _cosh, "tanh": _tanh,
    "asinh": _asinh, "acosh": _acosh, "atanh": _atanh,
    "ln": _ln, "log10": _log10, "exp": _exp,
    "sqrt": lambda x: x.sqrt(),
}
