# STUB -- replace with Part D's real implementation. Interface must not change.
"""
Placeholder authentication + thread-ownership check for backend/routers/copilot.py.

No real session/token validation exists yet. get_current_user() trusts an
X-User-Id header outright, and owns_thread() checks an in-memory map that
tests/dev code populate via register_thread_owner(). Replace both with real
auth (verified session/JWT) and a real DB-backed ownership lookup once
available -- the function names and signatures below should stay stable
so callers (copilot.py) don't need to change.
"""

from fastapi import Header, HTTPException, status

# thread_id -> owning user_id. In-memory only, per-process. A real
# implementation would look this up against the thread/run record in the
# database.
_THREAD_OWNERS: dict[str, str] = {}


async def get_current_user(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    """Returns the caller's user id. Currently just trusts the X-User-Id
    header -- no signature/session verification. Replace with real auth."""
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return x_user_id


def register_thread_owner(thread_id: str, user_id: str) -> None:
    """Test/dev helper to seed ownership until real thread creation wiring
    (protocol_planning kicking off a run under a specific user) exists."""
    _THREAD_OWNERS[thread_id] = user_id


def owns_thread(user_id: str, thread_id: str) -> bool:
    """True if `user_id` owns `thread_id`.

    A thread_id with no registered owner is treated as unowned/unknown
    rather than forbidden, so early local dev/demo threads created before
    this stub existed aren't locked out. Part D's real implementation
    should make this a strict DB lookup with no such default-allow case.
    """
    owner = _THREAD_OWNERS.get(thread_id)
    if owner is None:
        return True
    return owner == user_id


def require_thread_ownership(user_id: str, thread_id: str) -> None:
    """Raises 403 if `user_id` does not own `thread_id`. Call this first,
    before doing anything else, in every copilot endpoint."""
    if not owns_thread(user_id, thread_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this research thread.",
        )
