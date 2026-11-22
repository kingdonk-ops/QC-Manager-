"""A small, safe arithmetic evaluator for quantity formulas such as ``2*3.5+1.2``.

Grammar (recursive descent, no ``eval``)::

    expr   := term (("+" | "-") term)*
    term   := factor (("*" | "/") factor)*
    factor := ("+" | "-") factor | power
    power  := atom ("^" factor)?
    atom   := NUMBER | "(" expr ")"

Numbers take ``.`` or ``,`` as the decimal mark (``3,5`` is 3.5). ``x`` and ``×`` multiply, so a
dimension like ``2 x 3.5`` reads naturally. Results are ``Decimal``. Length, nesting and exponent
are bounded, so a formula can't make the server do unbounded work.
"""

from decimal import Decimal, InvalidOperation

MAX_LENGTH = 200
MAX_DEPTH = 30
MAX_EXPONENT = 10


class FormulaError(ValueError):
    pass


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit() or (ch in ".," and i + 1 < len(text) and text[i + 1].isdigit()):
            start = i
            while i < len(text) and (text[i].isdigit() or text[i] in ".,"):
                i += 1
            number = text[start:i].replace(",", ".")
            if number.count(".") > 1:
                raise FormulaError(f"'{text[start:i]}' isn't a number")
            tokens.append(number)
        elif ch in "+-*/()^":
            tokens.append(ch)
            i += 1
        elif ch in "xX×":
            tokens.append("*")
            i += 1
        elif ch == "÷":
            tokens.append("/")
            i += 1
        else:
            raise FormulaError(f"Unexpected '{ch}' in the formula")
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.depth = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise FormulaError("The formula ends too early")
        self.pos += 1
        return token

    def enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise FormulaError("The formula is nested too deeply")

    def expr(self) -> Decimal:
        self.enter()
        value = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            right = self.term()
            value = value + right if op == "+" else value - right
        self.depth -= 1
        return value

    def term(self) -> Decimal:
        value = self.factor()
        while self.peek() in ("*", "/"):
            op = self.take()
            right = self.factor()
            if op == "*":
                value *= right
            else:
                if right == 0:
                    raise FormulaError("Division by zero")
                value /= right
        return value

    def factor(self) -> Decimal:
        if self.peek() in ("+", "-"):
            self.enter()
            sign = self.take()
            value = self.factor()
            self.depth -= 1
            return -value if sign == "-" else value
        return self.power()

    def power(self) -> Decimal:
        base = self.atom()
        if self.peek() == "^":
            self.take()
            exponent = self.factor()
            if exponent != exponent.to_integral_value() or abs(exponent) > MAX_EXPONENT:
                raise FormulaError(f"Exponents are whole numbers up to {MAX_EXPONENT}")
            if base == 0 and exponent < 0:
                raise FormulaError("Division by zero")
            return base ** int(exponent)
        return base

    def atom(self) -> Decimal:
        token = self.take()
        if token == "(":
            value = self.expr()
            if self.take() != ")":
                raise FormulaError("A bracket isn't closed")
            return value
        try:
            return Decimal(token)
        except InvalidOperation as exc:
            raise FormulaError(f"Unexpected '{token}' in the formula") from exc


def evaluate(formula: str) -> Decimal:
    """The value of ``formula``. Raises ``FormulaError`` with a readable reason."""
    text = formula.strip().lstrip("=")
    if not text:
        raise FormulaError("The formula is empty")
    if len(text) > MAX_LENGTH:
        raise FormulaError(f"Formulas are limited to {MAX_LENGTH} characters")
    parser = _Parser(_tokenize(text))
    value = parser.expr()
    if parser.peek() is not None:
        raise FormulaError(f"Unexpected '{parser.peek()}' in the formula")
    return value
