from typing import Optional, Dict, Any, List
import json
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool


# =============================================================================
# МОДЕРАЦИЯ ПРАВИЛ И ПРИВЕТСТВИЙ (Таблица: await_checks_approvals)
# =============================================================================

async def get_pending_moderation(chat_id: int, content_type: str) -> Optional[Dict[str, Any]]:
    """Получить запись на модерацию для правил или приветствия"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM await_checks_approvals WHERE chat_id = $1 AND type = $2",
            chat_id, content_type
        )


async def add_pending_moderation(chat_id: int, content_type: str, text: str,
                                 message_id: int, admin_message_id: int, user_id: int):
    """Добавить или обновить запись на модерацию для правил/приветствия"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO await_checks_approvals "
            "(chat_id, type, text, message_id, admin_message_id, user_id) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "ON CONFLICT (chat_id, type) DO UPDATE SET "
            "text = $3, message_id = $4, admin_message_id = $5, user_id = $6",
            chat_id, content_type, text, message_id, admin_message_id, user_id
        )


async def delete_pending_moderation(chat_id: int, content_type: str):
    """Удалить запись из модерации после обработки"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM await_checks_approvals WHERE chat_id = $1 AND type = $2",
            chat_id, content_type
        )


# =============================================================================
# МОДЕРАЦИЯ ЗАМЕТОК (Таблица: await_checks_approvals_notes)
# =============================================================================

async def get_pending_moderation_note(chat_id: int, notes_name: str) -> Optional[Dict[str, Any]]:
    """Получить запись на модерацию для заметки"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM await_checks_approvals_notes WHERE chat_id = $1 AND notes_name = $2",
            chat_id, notes_name
        )


async def add_pending_moderation_note(chat_id: int, notes_name: str, notes_text: str,
                                      message_id: int, admin_message_id: int,
                                      user_id: int, is_edit: bool = False):
    """Добавить или обновить запись на модерацию для заметки"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO await_checks_approvals_notes "
            "(chat_id, notes_name, notes_text, message_id, admin_message_id, user_id, is_edit) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) "
            "ON CONFLICT (chat_id, notes_name) DO UPDATE SET "
            "notes_text = $3, message_id = $4, admin_message_id = $5, user_id = $6, is_edit = $7",
            chat_id, notes_name, notes_text, message_id, admin_message_id, user_id, is_edit
        )


async def delete_pending_moderation_note(chat_id: int, notes_name: str):
    """Удалить запись заметки из модерации после обработки"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM await_checks_approvals_notes WHERE chat_id = $1 AND notes_name = $2",
            chat_id, notes_name
        )


# =============================================================================
# МОДЕРАЦИЯ ПЕРВОГО КОММЕНТАРИЯ (Таблица: await_checks_approvals_first_comment)
# =============================================================================

async def get_pending_first_comment(channel_id: int) -> Optional[Dict[str, Any]]:
    """Получить запись на модерацию для первого комментария"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT channel_id, comment_text, message_id, admin_message_id, user_id, buttons "
            "FROM await_checks_approvals_first_comment WHERE channel_id = $1",
            channel_id
        )


async def add_pending_first_comment(channel_id: int, comment_text: str,
                                    message_id: int, admin_message_id: int,
                                    user_id: int, buttons: Optional[List[Dict[str, str]]] = None):
    """
    Добавить или обновить запись на модерацию для первого комментария.
    Принимает 6 аргументов: channel_id, comment_text, message_id, admin_message_id, user_id, buttons
    """
    pool = get_db_pool()
    async with pool.acquire() as conn:
        buttons_json = json.dumps(buttons) if buttons else None

        await conn.execute(
            "INSERT INTO await_checks_approvals_first_comment "
            "(channel_id, comment_text, message_id, admin_message_id, user_id, buttons) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "ON CONFLICT (channel_id) DO UPDATE SET "
            "comment_text = $2, message_id = $3, admin_message_id = $4, "
            "user_id = $5, buttons = $6, updated_at = CURRENT_TIMESTAMP",
            channel_id, comment_text, message_id, admin_message_id, user_id, buttons_json
        )


async def delete_pending_first_comment(channel_id: int):
    """Удалить запись первого комментария из модерации после обработки"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM await_checks_approvals_first_comment WHERE channel_id = $1",
            channel_id
        )


async def approve_first_comment(channel_id: int) -> bool:
    """
    Одобрить первый комментарий: применить изменения в основную таблицу.
    Возвращает True при успехе, False при ошибке.
    """
    pool = get_db_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT comment_text, buttons FROM await_checks_approvals_first_comment WHERE channel_id = $1",
            channel_id
        )
        if not record:
            return False

        comment_text = record['comment_text']
        buttons_json = record['buttons']
        buttons = json.loads(buttons_json) if buttons_json else None

        try:
            from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import set_first_comment
            await set_first_comment(channel_id, comment_text, buttons)
            return True
        except Exception as e:
            print(f"Ошибка при одобрении первого комментария (канал {channel_id}): {e}")
            return False


async def reject_first_comment(channel_id: int) -> bool:
    """
    Отклонить первый комментарий: просто удаляем из очереди модерации.
    Возвращает True при успехе.
    """
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM await_checks_approvals_first_comment WHERE channel_id = $1",
            channel_id
        )
        return True


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

async def clear_all_pending_moderation():
    """Очистить ВСЕ очереди модерации"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM await_checks_approvals")
        await conn.execute("DELETE FROM await_checks_approvals_notes")
        await conn.execute("DELETE FROM await_checks_approvals_first_comment")