"""Database foundation: config, migrations, schema, constraints (§30).

DB-backed tests need PostgreSQL (see conftest); pure-config tests always run.
All fixture data uses obviously-fake `@example.com` identities — never real users.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import get_engine, normalize_url
from app.models import AICredential, Analysis, Document, Issue, Requirement, User
from app.models.auth_tokens import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)
from tests.conftest import db_test_session, run


def _user(email: str = "stage02-foundation@example.com") -> User:
    return User(email=email, display_name="Stage 02 Fixture")


def _analysis(owner_id: uuid.UUID, **kw: object) -> Analysis:
    params: dict[str, object] = {
        "owner_id": owner_id,
        "title": "fixture",
        "source_type": "text",
        "score": 50,
        "band": "high",
    }
    params.update(kw)
    return Analysis(**params)


# --- Configuration (no database needed) -------------------------------------


def test_normalize_url_coerces_driver() -> None:
    assert normalize_url("postgresql://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
    assert normalize_url("postgres://u@h/db") == "postgresql+asyncpg://u@h/db"
    assert normalize_url("postgresql+asyncpg://u@h/db") == "postgresql+asyncpg://u@h/db"


def test_normalize_url_rejects_non_postgres() -> None:
    for bad in ("mysql://u@h/db", "sqlite:///x.db", "not-a-url"):
        with pytest.raises(RuntimeError, match="postgresql://"):
            normalize_url(bad)


def test_engine_requires_url_and_hides_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="not configured"):
            get_engine()
        monkeypatch.setenv("DATABASE_URL", "definitely not a url")
        get_settings.cache_clear()
        with pytest.raises(RuntimeError) as exc_info:
            get_engine()
        assert "definitely not a url" not in str(exc_info.value)  # no DSN echo
    finally:
        get_settings.cache_clear()


def test_model_metadata_tables() -> None:
    """Model registry sanity: every expected table is declared (no DB needed)."""
    from app.models.base import Base

    assert set(Base.metadata.tables) == {
        "users",
        "documents",
        "analyses",
        "requirements",
        "issues",
        "ai_provider_credentials",
        "user_preferences",
        "refresh_tokens",
        "email_verification_tokens",
        "password_reset_tokens",
    }


# --- Migrations -------------------------------------------------------------


def test_migration_head_is_0006(migrated_db: str) -> None:
    from alembic.migration import MigrationContext

    async def _heads() -> tuple[str, ...]:
        from app.core.database import dispose_engine as _dispose
        from app.core.database import get_engine as _engine

        try:
            async with _engine().connect() as conn:
                return await conn.run_sync(
                    lambda c: tuple(MigrationContext.configure(c).get_current_heads())
                )
        finally:
            await _dispose()

    assert run(_heads()) == ("0006",)  # Stage 23: user_preferences privacy settings


def test_tables_exist(migrated_db: str) -> None:
    async def _tables() -> list[str]:
        from app.core.database import dispose_engine as _dispose
        from app.core.database import get_engine as _engine

        try:
            async with _engine().connect() as conn:
                return await conn.run_sync(lambda c: inspect(c).get_table_names())
        finally:
            await _dispose()

    names = run(_tables())
    for expected in (
        "users",
        "analyses",
        "requirements",
        "issues",
        "documents",
        "ai_provider_credentials",
        "refresh_tokens",
        "email_verification_tokens",
        "password_reset_tokens",
        "alembic_version",
    ):
        assert expected in names


# --- Models, constraints, relationships --------------------------------------


def test_uuid_and_defaults(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            s.add(_user())
            await s.commit()
            row = (await s.execute(select(User))).scalar_one()
            assert isinstance(row.id, uuid.UUID)
            assert row.created_at is not None and row.updated_at is not None
            assert row.is_active is True and row.is_verified is False
            assert row.identity_provider == "local"

    run(_case())


def test_email_unique(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            s.add(_user("dupe@example.com"))
            await s.commit()
            s.add(_user("dupe@example.com"))
            with pytest.raises(IntegrityError):
                await s.commit()

    run(_case())


def test_fk_rejects_unknown_owner(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            s.add(_analysis(uuid.uuid4()))
            with pytest.raises(IntegrityError):
                await s.commit()

    run(_case())


def test_score_check_rejects_out_of_range(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            s.add(_user())
            await s.commit()
            owner = (await s.execute(select(User))).scalar_one()
            owner_id = owner.id  # capture: rollback() below expires ORM state
            for bad in (-1, 101):
                s.add(_analysis(owner_id, score=bad, band="low"))
                with pytest.raises(IntegrityError):
                    await s.commit()
                await s.rollback()

    run(_case())


def test_issue_offset_order_checked(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            user = _user()
            s.add(user)
            await s.commit()
            analysis = _analysis(user.id, score=10, band="low")
            s.add(analysis)
            await s.commit()
            req = Requirement(
                owner_id=user.id,
                analysis_id=analysis.id,
                position=0,
                text="Be fast.",
                score=10,
            )
            s.add(req)
            await s.commit()
            s.add(
                Issue(
                    owner_id=user.id,
                    requirement_id=req.id,
                    analysis_id=analysis.id,
                    detector_id="vague-term",
                    category="Vague",
                    severity="medium",
                    phrase="fast",
                    start_offset=3,
                    end_offset=3,  # invalid: must be > start
                    reason="r",
                    recommendation="s",
                )
            )
            with pytest.raises(IntegrityError):
                await s.commit()

    run(_case())


def test_position_unique_per_analysis(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            user = _user()
            s.add(user)
            await s.commit()
            analysis = _analysis(user.id, score=10, band="low")
            s.add(analysis)
            await s.commit()
            s.add(
                Requirement(
                    owner_id=user.id,
                    analysis_id=analysis.id,
                    position=0,
                    text="a",
                    score=1,
                )
            )
            await s.commit()
            s.add(
                Requirement(
                    owner_id=user.id,
                    analysis_id=analysis.id,
                    position=0,
                    text="b",
                    score=1,
                )
            )
            with pytest.raises(IntegrityError):
                await s.commit()

    run(_case())


def test_enabled_provider_unique_but_disabling_frees_it(migrated_db: str) -> None:
    def _cred(owner_id: uuid.UUID, fingerprint: str) -> AICredential:
        return AICredential(
            owner_id=owner_id,
            provider="groq",
            encrypted_api_key="v1:ciphertext-fixture",
            key_fingerprint=fingerprint,
            last4="AB12",
        )

    async def _case() -> None:
        async with db_test_session() as s:
            user = _user()
            s.add(user)
            await s.commit()
            owner_id = user.id  # capture: rollback() below expires ORM state
            first = _cred(owner_id, "fp11111111111111")
            s.add(first)
            await s.commit()
            s.add(_cred(owner_id, "fp22222222222222"))
            with pytest.raises(IntegrityError):
                await s.commit()
            await s.rollback()
            first.is_enabled = False
            await s.commit()
            s.add(_cred(owner_id, "fp22222222222222"))
            await s.commit()  # now allowed: previous row disabled

    run(_case())


def test_cascade_delete_analysis(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            user = _user()
            s.add(user)
            await s.commit()
            doc = Document(
                owner_id=user.id,
                filename="srs.pdf",
                mime_type="application/pdf",
                byte_size=12,
                sha256="a" * 64,
                storage_path="uuid-key-1",
            )
            analysis = _analysis(user.id, source_type="document", score=10, band="low")
            s.add_all([doc, analysis])
            await s.commit()
            analysis.document_id = doc.id
            req = Requirement(
                owner_id=user.id, analysis_id=analysis.id, position=0, text="a", score=1
            )
            s.add(req)
            await s.commit()
            s.add(
                Issue(
                    owner_id=user.id,
                    requirement_id=req.id,
                    analysis_id=analysis.id,
                    detector_id="d",
                    category="c",
                    severity="low",
                    phrase="p",
                    start_offset=0,
                    end_offset=1,
                    reason="r",
                    recommendation="s",
                )
            )
            await s.commit()
            await s.delete(analysis)
            await s.commit()
            for model in (Requirement, Issue):
                assert await s.scalar(select(func.count()).select_from(model)) == 0
            assert await s.scalar(select(func.count()).select_from(Document)) == 1
            assert await s.scalar(select(func.count()).select_from(User)) == 1

    run(_case())


def test_cascade_delete_user_removes_everything(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            user = _user()
            s.add(user)
            await s.commit()
            s.add(_analysis(user.id, score=1, band="low"))
            live = datetime.now(UTC) + timedelta(hours=1)
            s.add(
                RefreshToken(
                    owner_id=user.id,
                    token_hash="c" * 64,
                    family_id=uuid.uuid4(),
                    expires_at=live,
                )
            )
            s.add(EmailVerificationToken(owner_id=user.id, token_hash="d" * 64, expires_at=live))
            s.add(PasswordResetToken(owner_id=user.id, token_hash="e" * 64, expires_at=live))
            s.add(
                Document(
                    owner_id=user.id,
                    filename="s.txt",
                    mime_type="text/plain",
                    byte_size=1,
                    sha256="b" * 64,
                    storage_path="uuid-key-2",
                )
            )
            s.add(
                AICredential(
                    owner_id=user.id,
                    provider="groq",
                    encrypted_api_key="v1:x",
                    key_fingerprint="fp33333333333333",
                    last4="EF56",
                )
            )
            await s.commit()
            await s.delete(user)
            await s.commit()
            for model in (
                Analysis,
                Document,
                AICredential,
                Requirement,
                Issue,
                RefreshToken,
                EmailVerificationToken,
                PasswordResetToken,
            ):
                assert await s.scalar(select(func.count()).select_from(model)) == 0

    run(_case())


def test_ready_reports_ok_when_configured(migrated_db: str) -> None:
    """Endpoint wiring: /ready returns ok against the migrated test database."""
    from app.api.v1.endpoints.health import ready

    async def _probe() -> None:
        from app.core.database import dispose_engine as _dispose

        try:
            res = await ready()
            assert res.status == "ready"
            assert res.checks == {"database": "ok"}
        finally:
            await _dispose()

    run(_probe())
