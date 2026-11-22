from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

QTY = Numeric(18, 4)


class AssetLevel(Base, TimestampMixin):
    """One level of a project's breakdown. ``key`` is never re-keyed once nodes use it."""

    __tablename__ = "asset_levels"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_asset_levels_project_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(80))
    label_plural: Mapped[str] = mapped_column(String(80))
    depth: Mapped[int] = mapped_column(Integer, default=0)
    allowed_parent_keys: Mapped[list] = mapped_column(JSON, default_factory=list)
    """Empty: a root level."""
    roles: Mapped[list] = mapped_column(JSON, default_factory=list)
    code_pattern: Mapped[str | None] = mapped_column(String(200), default=None)
    code_uniqueness: Mapped[str] = mapped_column(String(16), default="per_parent")
    display_code_template: Mapped[str | None] = mapped_column(String(200), default=None)
    field_schema: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """JSONSchema for the level's ``custom_fields``."""
    pack_key: Mapped[str | None] = mapped_column(String(40), default=None)


class AssetNode(Base, TimestampMixin):
    __tablename__ = "asset_nodes"
    __table_args__ = (
        Index("ix_asset_nodes_project_path", "project_id", "path"),
        Index("ix_asset_nodes_parent", "parent_id"),
        UniqueConstraint("project_id", "code_scope", "code", name="uq_asset_nodes_code_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    level_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_levels.id", ondelete="RESTRICT"))
    level_key: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str | None] = mapped_column(String(300), default=None)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), default=None)
    path: Mapped[str] = mapped_column(String(1000), default="/")
    """``/<root id>/.../<own id>/`` — derived from ``parent_id``; subtree = ``path LIKE '<path>%'``."""
    display_path: Mapped[str] = mapped_column(String(2000), default="")
    display_code: Mapped[str | None] = mapped_column(String(300), default=None)
    code_scope: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(10), default="active")
    discipline_code: Mapped[str | None] = mapped_column(String(40), default=None)
    wbs_code: Mapped[str | None] = mapped_column(String(120), default=None)
    external_source: Mapped[str | None] = mapped_column(String(40), default=None)
    external_id: Mapped[str | None] = mapped_column(String(120), default=None)
    planned_start: Mapped[date | None] = mapped_column(Date, default=None)
    planned_finish: Mapped[date | None] = mapped_column(Date, default=None)
    budget_qty: Mapped[Decimal | None] = mapped_column(QTY, default=None)
    uom: Mapped[str | None] = mapped_column(String(20), default=None)
    budget_hours: Mapped[Decimal | None] = mapped_column(QTY, default=None)
    earned_qty: Mapped[Decimal | None] = mapped_column(QTY, default=None)
    latitude: Mapped[float | None] = mapped_column(default=None)
    longitude: Mapped[float | None] = mapped_column(default=None)
    superseded_by: Mapped[list] = mapped_column(JSON, default_factory=list)
    derived_from: Mapped[list] = mapped_column(JSON, default_factory=list)
    custom_fields: Mapped[dict] = mapped_column(JSON, default_factory=dict)


class AssetCollection(Base, TimestampMixin):
    """Job packs, shutdown windows, test packs, work plans: named sets of nodes that never change the tree."""

    __tablename__ = "asset_collections"
    __table_args__ = (UniqueConstraint("project_id", "kind", "code", name="uq_asset_collections_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    window_start: Mapped[date | None] = mapped_column(Date, default=None)
    window_end: Mapped[date | None] = mapped_column(Date, default=None)


class AssetCollectionMember(Base):
    __tablename__ = "asset_collection_members"

    collection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset_collections.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="CASCADE"), primary_key=True)


class ItemType(Base, TimestampMixin):
    """A typed, versioned item schema (pipe spool, valve, weld, vessel nozzle...)."""

    __tablename__ = "asset_item_types"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_asset_item_types_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    field_schema: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    inspectable: Mapped[bool] = mapped_column(Boolean, default=True)


class AssetItem(Base, TimestampMixin):
    __tablename__ = "asset_items"
    __table_args__ = (Index("ix_asset_items_project_tag", "project_id", "tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True)
    item_type_key: Mapped[str] = mapped_column(String(64))
    tag: Mapped[str] = mapped_column(String(120))
    parent_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    work_anchor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    spec_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    discipline: Mapped[str | None] = mapped_column(String(40), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    inspectable: Mapped[bool] = mapped_column(Boolean, default=True)
    type_revision: Mapped[int] = mapped_column(Integer, default=1)
    custom_fields: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class ItemIdentifier(Base, TimestampMixin):
    """A barcode, QR or NFC value on an Item. Replaced tags are deactivated, never deleted."""

    __tablename__ = "asset_item_identifiers"
    __table_args__ = (Index("ix_asset_item_identifiers_lookup", "project_id", "kind", "value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AssetTerm(Base, TimestampMixin):
    """A project's override of a level label or domain noun, with plural forms (``level.rsw`` → RSW / RSWs)."""

    __tablename__ = "asset_terms"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_asset_terms_project_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    one: Mapped[str] = mapped_column(String(80))
    other: Mapped[str] = mapped_column(String(80))


class AssetMappingProfile(Base, TimestampMixin):
    """A saved import mapping (spreadsheet columns → levels, node fields, custom fields, item fields).

    Saving under an existing name adds a new ``version``; earlier versions are kept so a past import can be explained.
    """

    __tablename__ = "asset_mapping_profiles"
    __table_args__ = (UniqueConstraint("project_id", "name", "version", name="uq_asset_mapping_profiles_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, default=1)
    mapping: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
