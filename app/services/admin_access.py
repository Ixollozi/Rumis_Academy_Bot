"""
Runtime admin list: DB + env owners.

- ADMIN_IDS from .env are permanent owners (cannot be removed in UI).
- Extra admins live in bot_admins and are managed from the admin panel.
- In-memory cache keeps settings.is_admin() sync and fast.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo

logger = logging.getLogger(__name__)

_admin_ids: set[int] = set()
_owner_ids: set[int] = set()


def cached_admin_ids() -> list[int]:
    return sorted(_admin_ids)


def cached_owner_ids() -> set[int]:
    return set(_owner_ids)


def is_admin(user_id: int) -> bool:
    return user_id in _admin_ids


def is_owner(user_id: int) -> bool:
    return user_id in _owner_ids


async def sync_admins(session: AsyncSession, env_owner_ids: list[int]) -> list[int]:
    """Upsert env owners into DB, refresh cache. Returns current admin tg_ids."""
    global _admin_ids, _owner_ids
    await repo.sync_owner_admins(session, env_owner_ids)
    rows = await repo.list_bot_admins(session)
    _owner_ids = {r.tg_id for r in rows if r.is_owner} | set(env_owner_ids)
    _admin_ids = {r.tg_id for r in rows} | set(env_owner_ids)
    logger.info("Admins synced: %s (owners=%s)", sorted(_admin_ids), sorted(_owner_ids))
    return cached_admin_ids()


async def refresh_cache(session: AsyncSession, env_owner_ids: list[int] | None = None) -> None:
    rows = await repo.list_bot_admins(session)
    global _admin_ids, _owner_ids
    owners = {r.tg_id for r in rows if r.is_owner}
    if env_owner_ids:
        owners |= set(env_owner_ids)
    _owner_ids = owners
    _admin_ids = {r.tg_id for r in rows} | owners
