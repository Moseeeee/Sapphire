from typing import Optional, Dict, Any
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool


async def get_pending_moderation(chat_id: int, content_type: str) -> Optional[Dict[str, Any]]:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            'SELECT * FROM await_checks_approvals WHERE chat_id = $1 AND type = $2',
            chat_id, content_type
        )

async def add_pending_moderation(chat_id: int, content_type: str, text: str,
                               message_id: int, admin_message_id: int, user_id: int):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO await_checks_approvals (chat_id, type, text, message_id, admin_message_id, user_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (chat_id, type) 
            DO UPDATE SET text = $3, message_id = $4, admin_message_id = $5, user_id = $6
        ''', chat_id, content_type, text, message_id, admin_message_id, user_id)

async def delete_pending_moderation(chat_id: int, content_type: str):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'DELETE FROM await_checks_approvals WHERE chat_id = $1 AND type = $2',
            chat_id, content_type
        )





# Функции для модерации заметок
async def get_pending_moderation_note(chat_id: int, notes_name: str) -> Optional[Dict[str, Any]]:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            'SELECT * FROM await_checks_approvals_notes WHERE chat_id = $1 AND notes_name = $2',
            chat_id, notes_name
        )

async def add_pending_moderation_note(chat_id: int, notes_name: str, notes_text: str,
                                    message_id: int, admin_message_id: int, user_id: int):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO await_checks_approvals_notes (chat_id, notes_name, notes_text, message_id, admin_message_id, user_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (chat_id, notes_name) 
            DO UPDATE SET notes_text = $3, message_id = $4, admin_message_id = $5, user_id = $6
        ''', chat_id, notes_name, notes_text, message_id, admin_message_id, user_id)

async def delete_pending_moderation_note(chat_id: int, notes_name: str):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'DELETE FROM await_checks_approvals_notes WHERE chat_id = $1 AND notes_name = $2',
            chat_id, notes_name
        )