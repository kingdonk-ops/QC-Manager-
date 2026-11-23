"""Response bodies of the read-only register views. Nothing here is ever stored: every figure is worked out from the rows
for the as-of day of the request."""

from datetime import date

from pydantic import BaseModel


class TwItemRef(BaseModel):
    """An item named in an overdue list; its required dates are calendar-day text."""

    id: int
    reference: str
    title: str
    family: str
    status: str
    required_load_on: str | None
    required_strike_on: str | None


class TwBreachRead(BaseModel):
    """An item bearing load without a valid permit to load; the reason names the status and the day."""

    item_id: int | None
    reference: str | None
    title: str | None
    reason: str


class TwGateRead(BaseModel):
    """Whether the item is cleared to load, and to strike, on the as-of day."""

    item_id: int
    reference: str
    status: str
    load_gate_open: bool
    strike_gate_open: bool


class TwRegisterWarning(BaseModel):
    """Advice that never affects the compliant flag. Kept apart from the breaches so a later decision can promote some."""

    item_id: int
    reference: str
    rule: str
    message: str


class TwLoadStatusRead(BaseModel):
    as_of: date
    total: int
    compliant: bool
    gates: list[TwGateRead]
    breaches: list[TwBreachRead]


class TwRegisterRollup(TwLoadStatusRead):
    status_counts: dict[str, int]
    category_counts: dict[str, int]
    design_clearance: str | None
    """A plain decimal such as ``50.00``, or absent for an empty register (never zero)."""
    overdue_to_load: list[TwItemRef]
    overdue_to_strike: list[TwItemRef]
    warnings: list[TwRegisterWarning]
