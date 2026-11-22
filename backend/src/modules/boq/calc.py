"""The arithmetic of a bill, free of the database so it can be tested on its own.

* A resource line costs ``factor × (1 + waste % / 100) × rate`` per unit of its position, where
  ``rate`` is the line's override or else the catalog rate.
* A position with resource lines takes its unit rate from them: the sum of their costs. Without
  lines its unit rate is whatever was typed.
* A leaf's total is ``quantity × unit rate``, rounded to cents. Anything with children (a section,
  or a position broken into sub-positions) totals its children instead.
* Ordinals number siblings 1, 2, 3 in their order, prefixed by the parent's: ``1``, ``1.1``,
  ``1.1.1``. They are recomputed from scratch after every change, so a move renumbers everything.
* Markups apply to the net total (the sum of the top-level totals)::

      overhead    = net × overhead %
      profit      = (net + overhead) × profit %
      contingency = net × contingency %
      subtotal    = net + overhead + profit + contingency
      tax         = subtotal × tax %
      grand total = subtotal + tax
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)
CENT = Decimal("0.01")
RATE = Decimal("0.0001")


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def rate4(value: Decimal) -> Decimal:
    return value.quantize(RATE, rounding=ROUND_HALF_UP)


@dataclass
class Line:
    factor: Decimal
    rate: Decimal
    waste_pct: Decimal = ZERO

    @property
    def cost(self) -> Decimal:
        return self.factor * (1 + self.waste_pct / 100) * self.rate


@dataclass
class Node:
    id: int
    parent_id: int | None
    sort: int = 0
    kind: str = "position"
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    lines: list[Line] = field(default_factory=list)


@dataclass
class Computed:
    ordinal: str
    depth: int
    unit_rate: Decimal | None
    total: Decimal
    has_children: bool


def rate_of(lines: Iterable[Line]) -> Decimal:
    return rate4(sum((line.cost for line in lines), ZERO))


def children_of(nodes: Iterable[Node]) -> dict[int | None, list[Node]]:
    """Each parent's children in order; nodes whose parent is missing count as top level."""
    nodes = list(nodes)
    ids = {n.id for n in nodes}
    kids: dict[int | None, list[Node]] = defaultdict(list)
    for n in nodes:
        kids[n.parent_id if n.parent_id in ids else None].append(n)
    for siblings in kids.values():
        siblings.sort(key=lambda n: (n.sort, n.id))
    return kids


def depth_first(nodes: Iterable[Node]) -> list[tuple[Node, int, str]]:
    """``(node, depth, ordinal)`` in reading order. Depth 0 is the top level."""
    kids = children_of(nodes)
    out: list[tuple[Node, int, str]] = []
    stack: list[tuple[Node, int, str]] = [(n, 0, str(i)) for i, n in reversed(list(enumerate(kids.get(None, []), start=1)))]
    seen: set[int] = set()
    while stack:
        node, depth, ordinal = stack.pop()
        if node.id in seen:  # a cycle can't be stored through the API, but don't loop if one is
            continue
        seen.add(node.id)
        out.append((node, depth, ordinal))
        stack.extend((c, depth + 1, f"{ordinal}.{i}") for i, c in reversed(list(enumerate(kids.get(node.id, []), start=1))))
    return out


def rollup(nodes: Sequence[Node]) -> dict[int, Computed]:
    """Unit rates, totals, ordinals and depths for every node."""
    order = depth_first(nodes)
    kids = children_of(nodes)
    result: dict[int, Computed] = {}
    for node, depth, ordinal in reversed(order):  # children before parents
        children = kids.get(node.id, [])
        unit_rate = rate_of(node.lines) if node.lines else node.unit_rate
        if children:
            total = sum((result[c.id].total for c in children if c.id in result), ZERO)
        else:
            total = cents((node.quantity or ZERO) * (unit_rate or ZERO))
        result[node.id] = Computed(ordinal, depth, unit_rate, total, bool(children))
    return result


def net_total(nodes: Sequence[Node], computed: dict[int, Computed]) -> Decimal:
    return sum((computed[n.id].total for n in children_of(nodes).get(None, []) if n.id in computed), ZERO)


def markups(
    net: Decimal, overhead_pct: Decimal, profit_pct: Decimal, contingency_pct: Decimal, tax_pct: Decimal
) -> dict[str, Decimal]:
    overhead = cents(net * overhead_pct / 100)
    profit = cents((net + overhead) * profit_pct / 100)
    contingency = cents(net * contingency_pct / 100)
    subtotal = net + overhead + profit + contingency
    tax = cents(subtotal * tax_pct / 100)
    return {
        "net_total": cents(net),
        "overhead": overhead,
        "profit": profit,
        "contingency": contingency,
        "subtotal": cents(subtotal),
        "tax": tax,
        "grand_total": cents(subtotal + tax),
    }


def descendants(nodes: Iterable[Node], node_id: int) -> set[int]:
    kids = children_of(nodes)
    found: set[int] = set()
    stack = [node_id]
    while stack:
        for child in kids.get(stack.pop(), []):
            if child.id not in found:
                found.add(child.id)
                stack.append(child.id)
    return found


def reorder(sibling_ids: Sequence[int], moved_id: int, before_id: int | None) -> list[int]:
    """The siblings with ``moved_id`` placed just above ``before_id`` (at the end when ``None``)."""
    ids = [i for i in sibling_ids if i != moved_id]
    if before_id is None or before_id not in ids:
        return [*ids, moved_id]
    at = ids.index(before_id)
    return [*ids[:at], moved_id, *ids[at:]]
