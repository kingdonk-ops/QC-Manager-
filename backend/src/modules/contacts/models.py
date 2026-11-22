from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Company(Base, TimestampMixin):
    __tablename__ = "contact_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(200), index=True)
    type: Mapped[str] = mapped_column(String(20), default="other")
    tax_id: Mapped[str | None] = mapped_column(String(50), default=None)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    phone: Mapped[str | None] = mapped_column(String(50), default=None)
    email: Mapped[str | None] = mapped_column(String(200), default=None)
    website: Mapped[str | None] = mapped_column(String(200), default=None)
    banking: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """Bank name, account name, BSB/sort code, account number, SWIFT, as entered."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), default="")
    company_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contact_companies.id", ondelete="SET NULL"), index=True, default=None
    )
    type: Mapped[str] = mapped_column(String(20), default="other")
    job_title: Mapped[str | None] = mapped_column(String(150), default=None)
    email: Mapped[str | None] = mapped_column(String(200), index=True, default=None)
    phone: Mapped[str | None] = mapped_column(String(50), default=None)
    mobile: Mapped[str | None] = mapped_column(String(50), default=None)
    tags: Mapped[list] = mapped_column(JSON, default_factory=list)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    """The app account this person signs in with, if any."""


class ProjectContact(Base, TimestampMixin):
    __tablename__ = "project_contacts"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str | None] = mapped_column(String(150), default=None)
