from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class ModuleAccess(Base, TimestampMixin):
    """A user's access level to one module, replacing what their roles give for it."""

    __tablename__ = "platform_module_access"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    module: Mapped[str] = mapped_column(String(64), primary_key=True)
    level: Mapped[str] = mapped_column(String(10))


class UserPreference(Base, TimestampMixin):
    """Small per-user settings the UI keeps on the server: onboarding progress, interface mode."""

    __tablename__ = "platform_user_preferences"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
