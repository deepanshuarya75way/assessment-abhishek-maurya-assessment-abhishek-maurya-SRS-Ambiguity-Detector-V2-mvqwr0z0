"""`user_preferences` — per-user privacy/lifecycle settings (Stage 23).

Only real enforced preferences live here. `history_retention_days` drives the
retention purge service/command; NULL means no automatic history retention rule.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin, UpdatedMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserPreference(Base, CreatedMixin, UpdatedMixin):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint(
            "history_retention_days IS NULL OR "
            "(history_retention_days >= 1 AND history_retention_days <= 3650)",
            name="ck_user_preferences_history_retention_days",
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    history_retention_days: Mapped[int | None] = mapped_column(Integer)

    owner: Mapped["User"] = relationship(back_populates="preferences")
