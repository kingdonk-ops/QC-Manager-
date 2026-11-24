"""As-built records: what was captured on site, judged against an acceptance criterion of the inspections library."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class AsBuiltRecord(Base, TimestampMixin):
    """One as-built record. The measured value, deviation value and accuracy value are kept as short text so a survey
    can be entered exactly as taken; the tolerance rules parse the measured value as an exact decimal."""

    __tablename__ = "as_built_records"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_as_built_records_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    discipline: Mapped[str | None] = mapped_column(String(100), default=None)
    location: Mapped[str | None] = mapped_column(String(300), default=None)
    capture_method: Mapped[str] = mapped_column(String(24), default="manual")
    instrument: Mapped[str | None] = mapped_column(String(200), default=None)
    calibration_ref: Mapped[str | None] = mapped_column(String(100), default=None)
    accuracy_class: Mapped[str] = mapped_column(String(12), default="standard")
    accuracy_value: Mapped[str | None] = mapped_column(String(40), default=None)
    accuracy_unit: Mapped[str | None] = mapped_column(String(30), default=None)
    coordinate_system: Mapped[str | None] = mapped_column(String(100), default=None)
    surveyed_on: Mapped[date | None] = mapped_column(Date, default=None)
    surveyed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """Set by the first survey to the acting user when it was empty."""
    criterion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_criteria.id", ondelete="RESTRICT"), index=True, default=None
    )
    measured_value: Mapped[str | None] = mapped_column(String(40), default=None)
    deviation_value: Mapped[str | None] = mapped_column(String(40), default=None)
    """A manually entered deviation distance only; it is never compared and never holds a count."""
    tolerance_result: Mapped[str] = mapped_column(String(16), default="not_assessed")
    """Within, out of tolerance or not assessed, stored by each survey; anything undecidable stays not assessed."""
    source_kind: Mapped[str] = mapped_column(String(24), default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(200), default=None)
    deviation_map_ref: Mapped[str | None] = mapped_column(String(300), default=None)
    node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True, default=None
    )
    item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_items.id", ondelete="RESTRICT"), index=True, default=None
    )
    status: Mapped[str] = mapped_column(String(12), default="draft")
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    verifier_notes: Mapped[str | None] = mapped_column(Text, default=None)
    report_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The workmanship report raised when an out-of-tolerance record was verified."""
    legal_record: Mapped[bool] = mapped_column(Boolean, default=False)
    """Set only by a signed attestation as valid, never by a survey or a verification."""
    signed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    signed_ip: Mapped[str | None] = mapped_column(String(64), default=None)
    signed_digest: Mapped[str | None] = mapped_column(String(64), default=None)
    signature_notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    supplementary: Mapped[dict] = mapped_column(JSON, default_factory=dict)
