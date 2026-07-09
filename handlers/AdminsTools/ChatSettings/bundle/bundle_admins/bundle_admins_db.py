import logging
from typing import List, Dict, Any, Optional

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def add_bundle_admin(bundle_id: int, admin_user_id: int, added_by: int, rank: int = 1) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bundle_admins (bundle_id, user_id, added_by, rank)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (bundle_id, user_id) DO UPDATE SET rank = EXCLUDED.rank, added_by = EXCLUDED.added_by
            ''', bundle_id, admin_user_id, added_by, rank)
            return True
    except Exception as e:
        logger.error(f"add_bundle_admin error: {e}", exc_info=True)
        return False


async def remove_bundle_admin(bundle_id: int, admin_user_id: int) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM bundle_admins WHERE bundle_id = $1 AND user_id = $2",
                bundle_id, admin_user_id
            )
            return True
    except Exception as e:
        logger.error(f"remove_bundle_admin error: {e}", exc_info=True)
        return False


async def get_bundle_admins(bundle_id: int) -> List[Dict[str, Any]]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT user_id, rank FROM bundle_admins WHERE bundle_id = $1 ORDER BY rank DESC, user_id
            ''', bundle_id)
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"get_bundle_admins error: {e}", exc_info=True)
        return []


async def is_bundle_admin(bundle_id: int, user_id: int, required_rank: int = 1) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT rank FROM bundle_admins WHERE bundle_id = $1 AND user_id = $2",
                bundle_id, user_id
            )
            return row is not None and row['rank'] >= required_rank
    except Exception as e:
        logger.error(f"is_bundle_admin error: {e}", exc_info=True)
        return False


async def add_bundle_log(bundle_id: int, admin_id: int, target_user_id: int, action: str,
                         reason: str = "", duration: str = "", success: bool = True) -> None:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bundle_action_log (bundle_id, admin_id, target_user_id, action, reason, duration, success)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', bundle_id, admin_id, target_user_id, action, reason, duration, success)
    except Exception as e:
        logger.error(f"add_bundle_log error: {e}", exc_info=True)


async def get_bundle_logs(bundle_id: int, user_id: Optional[int] = None, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            if user_id:
                rows = await conn.fetch('''
                    SELECT admin_id, target_user_id, action, reason, duration, success, created_at
                    FROM bundle_action_log
                    WHERE bundle_id = $1 AND target_user_id = $2
                    ORDER BY created_at DESC
                    OFFSET $3 LIMIT $4
                ''', bundle_id, user_id, offset, limit)
            else:
                rows = await conn.fetch('''
                    SELECT admin_id, target_user_id, action, reason, duration, success, created_at
                    FROM bundle_action_log
                    WHERE bundle_id = $1
                    ORDER BY created_at DESC
                    OFFSET $2 LIMIT $3
                ''', bundle_id, offset, limit)
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"get_bundle_logs error: {e}", exc_info=True)
        return []


async def get_bundle_logs_count(bundle_id: int, user_id: Optional[int] = None) -> int:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            if user_id:
                count = await conn.fetchval('''
                    SELECT COUNT(*) FROM bundle_action_log
                    WHERE bundle_id = $1 AND target_user_id = $2
                ''', bundle_id, user_id)
            else:
                count = await conn.fetchval('''
                    SELECT COUNT(*) FROM bundle_action_log WHERE bundle_id = $1
                ''', bundle_id)
            return count or 0
    except Exception as e:
        logger.error(f"get_bundle_logs_count error: {e}", exc_info=True)
        return 0