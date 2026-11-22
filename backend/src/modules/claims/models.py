from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

Money = Numeric(16, 2)
Qty = Numeric(18, 4)


class RateItem(Base, TimestampMixin):
    """One line of the contract's schedule of rates, on a breakdown node (progress unit or work anchor).

    A claim values it from the verified quantity of the progress units at or below ``node_id``; an item with
    no node can't be verified, so it never earns.
    """

    __tablename__ = "claims_rate_items"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_claims_rate_items_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str | None] = mapped_column(String(20), default=None)
    contract_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    rate: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), index=True, default=None
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Claim(Base, TimestampMixin):
    """A progress claim for a period: ``draft`` → ``submitted`` → ``certified`` → ``paid``.

    ``totals`` freezes the figures at submission (``previous_payments`` included), so a later certification of
    an earlier claim never rewrites what was claimed.
    """

    __tablename__ = "claims_claims"
    __table_args__ = (Index("ix_claims_claims_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    retention_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(5))
    retention_cap: Mapped[Decimal | None] = mapped_column(Money, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    totals: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    certified_amount: Mapped[Decimal | None] = mapped_column(Money, default=None)
    certified_on: Mapped[date | None] = mapped_column(Date, default=None)
    certified_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    client_reference: Mapped[str | None] = mapped_column(String(120), default=None)
    paid_amount: Mapped[Decimal | None] = mapped_column(Money, default=None)
    paid_on: Mapped[date | None] = mapped_column(Date, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class ClaimLine(Base):
    """A work line (a rate item) or a variation line (an approved change card or change order).

    Quantities are to date. A variation is ``contract_qty`` 1 at its approved amount; ``to_date_qty`` is the
    share claimed so far. A work line's ``to_date_qty`` never exceeds ``verified_qty``.
    """

    __tablename__ = "claims_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    claim_id: Mapped[int] = mapped_column(Integer, ForeignKey("claims_claims.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str | None] = mapped_column(String(20), default=None)
    contract_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    rate: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    verified_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    previous_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    to_date_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("claims_rate_items.id", ondelete="SET NULL"), default=None
    )
    node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    source_type: Mapped[str | None] = mapped_column(String(20), default=None)
    source_id: Mapped[int | None] = mapped_column(Integer, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
