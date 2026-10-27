"""Predictable transaction strategy (ARCHITECTURE §6): one transaction per service call.

Services needing atomicity wrap their session-taking coroutine with @transactional:
commit on success, rollback + re-raise on failure. Orchestrators needing atomicity
across several services skip the decorator, share one session, and commit once —
no code for that path until a caller needs it.
"""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar, cast

from sqlalchemy.ext.asyncio import AsyncSession

P = ParamSpec("P")
T = TypeVar("T")


def transactional(
    fn: Callable[Concatenate[AsyncSession, P], Awaitable[T]],
) -> Callable[Concatenate[AsyncSession, P], Awaitable[T]]:
    """Commit the session on success; rollback and re-raise on failure.

    The wrapped coroutine MUST take its AsyncSession as the first argument.
    A function that must persist state AND raise (e.g. the refresh-reuse theft
    response) commits explicitly before raising — the rollback then no-ops.
    """

    @wraps(fn)
    async def wrapper(session: AsyncSession, *args: P.args, **kwargs: P.kwargs) -> T:
        try:
            result = await fn(session, *args, **kwargs)
        except Exception:
            await session.rollback()
            raise
        await session.commit()
        return result

    # cast: @wraps erases the Concatenate proof mypy needs; runtime type is exact.
    return cast(Callable[Concatenate[AsyncSession, P], Awaitable[T]], wrapper)
