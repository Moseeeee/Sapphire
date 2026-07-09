import logging
from typing import List, Dict, Any, Optional
from pytz import timezone

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone('Europe/Moscow')


async def create_bundle(owner_id: int, name: str) -> Optional[int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM bundles WHERE owner_id = $1 AND name = $2",
                owner_id, name
            )
            if existing:
                return None
            row = await conn.fetchrow(
                "INSERT INTO bundles (owner_id, name) VALUES ($1, $2) RETURNING id",
                owner_id, name
            )
            return row['id'] if row else None
    except Exception as e:
        logger.error(f"create_bundle error: {e}", exc_info=True)
        return None


async def get_user_bundles(owner_id: int) -> List[Dict[str, Any]]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT b.id, b.name, b.created_at, COUNT(bc.chat_id) as chat_count
                FROM bundles b
                LEFT JOIN bundle_chats bc ON b.id = bc.bundle_id
                WHERE b.owner_id = $1
                GROUP BY b.id
                ORDER BY b.created_at DESC
            """, owner_id)
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"get_user_bundles error: {e}", exc_info=True)
        return []


async def get_bundle_by_name(owner_id: int, name: str) -> Optional[int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM bundles WHERE owner_id = $1 AND name = $2",
                owner_id, name
            )
            return row['id'] if row else None
    except Exception as e:
        logger.error(f"get_bundle_by_name error: {e}", exc_info=True)
        return None


async def get_bundle_owner(bundle_id: int) -> Optional[int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT owner_id FROM bundles WHERE id = $1",
                bundle_id
            )
            return row['owner_id'] if row else None
    except Exception as e:
        logger.error(f"get_bundle_owner error: {e}", exc_info=True)
        return None


async def delete_bundle(bundle_id: int) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM bundles WHERE id = $1", bundle_id)
            return True
    except Exception as e:
        logger.error(f"delete_bundle error: {e}", exc_info=True)
        return False


async def is_chat_in_any_bundle(chat_id: int) -> Optional[int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT bundle_id FROM bundle_chats WHERE chat_id = $1",
                chat_id
            )
            return row['bundle_id'] if row else None
    except Exception as e:
        logger.error(f"is_chat_in_any_bundle error: {e}", exc_info=True)
        return None


async def is_chat_in_bundle(chat_id: int, bundle_id: int) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM bundle_chats WHERE bundle_id = $1 AND chat_id = $2",
                bundle_id, chat_id
            )
            return row is not None
    except Exception as e:
        logger.error(f"is_chat_in_bundle error: {e}", exc_info=True)
        return False


async def add_chat_to_bundle(bundle_id: int, chat_id: int, added_by: int, description: str = "") -> bool:
    existing = await is_chat_in_any_bundle(chat_id)
    if existing is not None:
        return False
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bundle_chats (bundle_id, chat_id, added_by, description)
                VALUES ($1, $2, $3, $4)
            ''', bundle_id, chat_id, added_by, description)
            return True
    except Exception as e:
        logger.error(f"add_chat_to_bundle error: {e}", exc_info=True)
        return False

async def move_chat_to_bundle(chat_id: int, new_bundle_id: int, added_by: int, description: str = "") -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM bundle_chats WHERE chat_id = $1", chat_id)
            await conn.execute('''
                INSERT INTO bundle_chats (bundle_id, chat_id, added_by, description)
                VALUES ($1, $2, $3, $4)
            ''', new_bundle_id, chat_id, added_by, description)
            return True
    except Exception as e:
        logger.error(f"move_chat_to_bundle error: {e}", exc_info=True)
        return False

async def remove_chat_from_bundle(bundle_id: int, chat_id: int) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM bundle_chats WHERE bundle_id = $1 AND chat_id = $2",
                bundle_id, chat_id
            )
            return True
    except Exception as e:
        logger.error(f"remove_chat_from_bundle error: {e}", exc_info=True)
        return False


async def get_bundle_chats(bundle_id: int) -> List[int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT chat_id FROM bundle_chats WHERE bundle_id = $1",
                bundle_id
            )
            return [row['chat_id'] for row in rows]
    except Exception as e:
        logger.error(f"get_bundle_chats error: {e}", exc_info=True)
        return []


async def get_bundle_info(bundle_id: int) -> Optional[Dict[str, Any]]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            bundle_row = await conn.fetchrow(
                "SELECT id, owner_id, name, created_at FROM bundles WHERE id = $1",
                bundle_id
            )
            if not bundle_row:
                return None
            chats = await get_bundle_chats(bundle_id)
            return {
                'id': bundle_row['id'],
                'owner_id': bundle_row['owner_id'],
                'name': bundle_row['name'],
                'created_at': bundle_row['created_at'],
                'chats': chats
            }
    except Exception as e:
        logger.error(f"get_bundle_info error: {e}", exc_info=True)
        return None


async def get_bundle_by_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT b.id, b.owner_id, b.name, b.created_at
                FROM bundles b
                JOIN bundle_chats bc ON b.id = bc.bundle_id
                WHERE bc.chat_id = $1
            """, chat_id)
            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"get_bundle_by_chat error: {e}", exc_info=True)
        return None


async def set_selected_bundle(user_id: int, bundle_id: int) -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_selected_bundle (user_id, bundle_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET bundle_id = EXCLUDED.bundle_id, updated_at = NOW()
            """, user_id, bundle_id)
            return True
    except Exception as e:
        logger.error(f"set_selected_bundle error: {e}", exc_info=True)
        return False


async def get_selected_bundle(user_id: int) -> Optional[int]:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT bundle_id FROM user_selected_bundle WHERE user_id = $1",
                user_id
            )
            return row['bundle_id'] if row else None
    except Exception as e:
        logger.error(f"get_selected_bundle error: {e}", exc_info=True)
        return None


# Добавим в конец файла:

async def add_chat_to_bundle_with_desc(bundle_id: int, chat_id: int, added_by: int, description: str = "") -> bool:
    existing = await is_chat_in_any_bundle(chat_id)
    if existing is not None:
        return False
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bundle_chats (bundle_id, chat_id, added_by, description)
                VALUES ($1, $2, $3, $4)
            ''', bundle_id, chat_id, added_by, description)
            return True
    except Exception as e:
        logger.error(f"add_chat_to_bundle_with_desc error: {e}", exc_info=True)
        return False


async def move_chat_to_bundle_with_desc(chat_id: int, new_bundle_id: int, added_by: int, description: str = "") -> bool:
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM bundle_chats WHERE chat_id = $1", chat_id)
            await conn.execute('''
                INSERT INTO bundle_chats (bundle_id, chat_id, added_by, description)
                VALUES ($1, $2, $3, $4)
            ''', new_bundle_id, chat_id, added_by, description)
            return True
    except Exception as e:
        logger.error(f"move_chat_to_bundle_with_desc error: {e}", exc_info=True)
        return False


async def get_bundle_chats_with_descriptions(bundle_id: int) -> List[Dict[str, Any]]:
    """Возвращает список чатов связки с их описаниями."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT chat_id, description, added_at
                FROM bundle_chats
                WHERE bundle_id = $1
                ORDER BY added_at ASC
            ''', bundle_id)
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"get_bundle_chats_with_descriptions error: {e}", exc_info=True)
        return []