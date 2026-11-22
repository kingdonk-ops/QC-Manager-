"""Markups on PDF drawings.

Geometry is in PDF units (1/72 inch) of the page as displayed, at scale 1, with the origin at the
top-left corner and y pointing down: the same numbers whatever the zoom.
"""

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class MarkupSet(Base, TimestampMixin):
    """One person's layer of markups on one revision of a file."""

    __tablename__ = "markups_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)


class Markup(Base, TimestampMixin):
    __tablename__ = "markups"
    __table_args__ = (Index("ix_markups_file_page", "file_id", "page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    set_id: Mapped[int] = mapped_column(Integer, ForeignKey("markups_sets.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"))
    page: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(30))
    geometry: Mapped[dict] = mapped_column(JSON)
    style: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    text: Mapped[str | None] = mapped_column(Text, default=None)
    measurement: Mapped[dict | None] = mapped_column(JSON, default=None)
    """``{"value": 12.3, "unit": "m" | "m2", "meters_per_unit": ...}`` for measure tools on a calibrated page."""
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)


class MarkupCalibration(Base, TimestampMixin):
    """A page's scale: two points picked on the drawing and the real distance between them."""

    __tablename__ = "markups_calibrations"

    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    points: Mapped[list] = mapped_column(JSON)
    real_distance: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(5))
    meters_per_unit: Mapped[float] = mapped_column(Float)
    set_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)


class StampTemplate(Base, TimestampMixin):
    __tablename__ = "markups_stamp_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(9), default="#16a34a")
    include_date: Mapped[bool] = mapped_column(Boolean, default=True)
    include_author: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, default=None)
