"""The asset register, shaped after COBie: facility > floor > space, zones of spaces, product types,
components (the individual assets) and the systems they belong to.

Every row carries its ``project_id`` so visibility checks need no joins.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class AssetFacility(Base, TimestampMixin):
    __tablename__ = "assets_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(200), default=None)
    site_name: Mapped[str | None] = mapped_column(String(200), default=None)
    linear_units: Mapped[str] = mapped_column(String(30), default="meters")
    area_units: Mapped[str] = mapped_column(String(30), default="squaremeters")
    volume_units: Mapped[str] = mapped_column(String(30), default="cubicmeters")
    area_measurement: Mapped[str | None] = mapped_column(String(100), default=None)
    phase: Mapped[str | None] = mapped_column(String(100), default=None)


class AssetFloor(Base, TimestampMixin):
    __tablename__ = "assets_floors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets_facilities.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(200), default="Floor")
    elevation: Mapped[float | None] = mapped_column(Float, default=None)
    height: Mapped[float | None] = mapped_column(Float, default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)


class AssetSpace(Base, TimestampMixin):
    __tablename__ = "assets_spaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    floor_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets_floors.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(200), default=None)
    room_tag: Mapped[str | None] = mapped_column(String(100), default=None)
    usable_height: Mapped[float | None] = mapped_column(Float, default=None)
    gross_area: Mapped[float | None] = mapped_column(Float, default=None)
    net_area: Mapped[float | None] = mapped_column(Float, default=None)


class AssetZone(Base, TimestampMixin):
    """A named group of spaces: a fire zone, a lettable area, a heating zone."""

    __tablename__ = "assets_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(200), default=None)
    space_ids: Mapped[list] = mapped_column(JSON, default_factory=list)


class AssetType(Base, TimestampMixin):
    """A product type: every component of a type shares its manufacturer, model and warranty."""

    __tablename__ = "assets_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(200), default=None)
    """A classification code and title as text, e.g. ``Pr_70_60_36_73 : Pumps`` (Uniclass) or OmniClass."""
    asset_kind: Mapped[str] = mapped_column(String(20), default="Fixed")
    manufacturer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None)
    model_number: Mapped[str | None] = mapped_column(String(200), default=None)
    warranty_guarantor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None
    )
    warranty_duration_parts: Mapped[float | None] = mapped_column(Float, default=None)
    warranty_duration_labor: Mapped[float | None] = mapped_column(Float, default=None)
    warranty_duration_unit: Mapped[str] = mapped_column(String(20), default="year")
    warranty_description: Mapped[str | None] = mapped_column(Text, default=None)
    replacement_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    expected_life: Mapped[float | None] = mapped_column(Float, default=None)
    duration_unit: Mapped[str] = mapped_column(String(20), default="year")
    nominal_length: Mapped[float | None] = mapped_column(Float, default=None)
    nominal_width: Mapped[float | None] = mapped_column(Float, default=None)
    nominal_height: Mapped[float | None] = mapped_column(Float, default=None)
    model_reference: Mapped[str | None] = mapped_column(String(200), default=None)
    shape: Mapped[str | None] = mapped_column(String(100), default=None)
    size: Mapped[str | None] = mapped_column(String(100), default=None)
    color: Mapped[str | None] = mapped_column(String(100), default=None)
    finish: Mapped[str | None] = mapped_column(String(100), default=None)
    grade: Mapped[str | None] = mapped_column(String(100), default=None)
    material: Mapped[str | None] = mapped_column(String(100), default=None)
    attributes: Mapped[dict] = mapped_column(JSON, default_factory=dict)


class AssetComponent(Base, TimestampMixin):
    """One asset: a pump, a door, a fire extinguisher."""

    __tablename__ = "assets_components"
    __table_args__ = (Index("ix_assets_components_project_name", "project_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assets_types.id", ondelete="SET NULL"), index=True, default=None
    )
    space_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assets_spaces.id", ondelete="SET NULL"), index=True, default=None
    )
    serial_number: Mapped[str | None] = mapped_column(String(200), default=None)
    installation_date: Mapped[date | None] = mapped_column(Date, default=None)
    warranty_start_date: Mapped[date | None] = mapped_column(Date, default=None)
    tag_number: Mapped[str | None] = mapped_column(String(200), default=None)
    bar_code: Mapped[str | None] = mapped_column(String(200), default=None)
    asset_identifier: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    attributes: Mapped[dict] = mapped_column(JSON, default_factory=dict)


class AssetSystem(Base, TimestampMixin):
    __tablename__ = "assets_systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(200), default=None)


class AssetSystemComponent(Base):
    __tablename__ = "assets_system_components"

    system_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets_systems.id", ondelete="CASCADE"), primary_key=True)
    component_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets_components.id", ondelete="CASCADE"), primary_key=True, index=True
    )
