from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Equipment(Base, TimestampMixin):
    """A measuring or test instrument (or vehicle / plant) whose readings must come from a calibrated tool."""

    __tablename__ = "calibration_equipment"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_calibration_equipment_code"),
        Index("ix_calibration_equipment_due", "project_id", "status", "due_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64))
    """Asset / fleet number."""
    name: Mapped[str] = mapped_column(String(200))
    equipment_type: Mapped[str] = mapped_column(String(32), default="other")
    equipment_class: Mapped[str] = mapped_column(String(16), default="instrument")
    requires_calibration: Mapped[bool] = mapped_column(Boolean, default=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120), default=None)
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    serial_number: Mapped[str | None] = mapped_column(String(128), default=None)
    range_text: Mapped[str | None] = mapped_column(String(120), default=None)
    custodian_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    """The owner: receives the due reminders."""
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    interval_days: Mapped[int] = mapped_column(Integer, default=365)
    reminder_days: Mapped[int] = mapped_column(Integer, default=14)
    last_calibrated_on: Mapped[date | None] = mapped_column(Date, default=None)
    due_on: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(24), default="out_of_service")
    last_reminder_on: Mapped[date | None] = mapped_column(Date, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class CalibrationCertificate(Base, TimestampMixin):
    """One calibration. Never edited: a new certificate supersedes the active one."""

    __tablename__ = "calibration_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    equipment_id: Mapped[int] = mapped_column(Integer, ForeignKey("calibration_equipment.id", ondelete="CASCADE"), index=True)
    certificate_number: Mapped[str] = mapped_column(String(128))
    calibrated_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    facility: Mapped[str | None] = mapped_column(String(255), default=None)
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"), default=None)
    result: Mapped[str] = mapped_column(String(16), default="pass")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
