"""SQLAlchemy 2.0 models (the project contract). Importing this package registers
every table on Base.metadata (alembic target + tests). Auth-token tables arrive Stage 04."""

from app.models.ai_credential import AICredential
from app.models.analysis import Analysis
from app.models.auth_tokens import (
    PasswordResetToken,
    RefreshToken,
)
from app.models.base import Base, CreatedMixin, UpdatedMixin
from app.models.document import Document
from app.models.issue import Issue
from app.models.requirement import Requirement
from app.models.user import User
from app.models.user_preference import UserPreference

__all__ = [
    "AICredential",
    "Analysis",
    "Base",
    "CreatedMixin",
    "Document",
    "Issue",
    "PasswordResetToken",
    "RefreshToken",
    "Requirement",
    "UpdatedMixin",
    "User",
    "UserPreference",
]
