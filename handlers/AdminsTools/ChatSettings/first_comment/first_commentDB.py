import logging
from typing import Optional, Dict, Any, List
import json

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def set_first_comment(chat_id: int, comment_text: str, buttons: List[Dict[str, str]] = None) -> bool:
    """
    Установка первого комментария.
    :param chat_id: ID ГРУППЫ
    :param comment_text: Текст комментария
    :param buttons: Кнопки
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Сохраняем по ID ГРУППЫ
                await conn.execute('''
                    INSERT INTO first_comments (chat_id, comment_text)
                    VALUES ($1, $2)
                    ON CONFLICT (chat_id) 
                    DO UPDATE SET comment_text = $2
                ''', chat_id, comment_text)

                await conn.execute(
                    'DELETE FROM first_comment_buttons WHERE chat_id = $1',
                    chat_id
                )

                if buttons:
                    for i, button in enumerate(buttons[:5]):
                        await conn.execute('''
                            INSERT INTO first_comment_buttons (chat_id, button_index, button_text, button_url)
                            VALUES ($1, $2, $3, $4)
                        ''', chat_id, i, button['text'], button['url'])

                return True
    except Exception as e:
        logger.error(f"❌ Ошибка в set_first_comment: {e}", exc_info=True)
        return False


async def get_first_comment(chat_id: int) -> Optional[Dict[str, Any]]:
    """Получение первого комментария по ID ГРУППЫ"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            comment_row = await conn.fetchrow(
                'SELECT comment_text FROM first_comments WHERE chat_id = $1',
                chat_id
            )

            if not comment_row:
                return None

            button_rows = await conn.fetch(
                'SELECT button_text, button_url FROM first_comment_buttons WHERE chat_id = $1 ORDER BY button_index',
                chat_id
            )

            buttons = [
                {'text': row['button_text'], 'url': row['button_url']}
                for row in button_rows
            ]

            return {
                'comment_text': comment_row['comment_text'],
                'buttons': buttons
            }
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def delete_first_comment(chat_id: int) -> bool:
    """Удаление первого комментария по ID ГРУППЫ"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM first_comments WHERE chat_id = $1',
                chat_id
            )
            return result.split()[-1] != '0'
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def add_pending_first_comment(chat_id: int, comment_text: str,
                                    message_id: int, admin_message_id: int,
                                    user_id: int, buttons: List[Dict[str, str]] = None) -> bool:
    """
    Добавление первого комментария на модерацию.
    :param chat_id: ID ГРУППЫ
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                buttons_json = json.dumps(buttons) if buttons else None

                await conn.execute('''
                    INSERT INTO await_checks_approvals_first_comment 
                    (chat_id, comment_text, message_id, admin_message_id, user_id, buttons)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (chat_id) 
                    DO UPDATE SET 
                        comment_text = $2, 
                        message_id = $3, 
                        admin_message_id = $4, 
                        user_id = $5,
                        buttons = $6
                ''', chat_id, comment_text, message_id, admin_message_id, user_id, buttons_json)

                return True
    except Exception as e:
        logger.error(f"❌ Ошибка в add_pending_first_comment: {e}", exc_info=True)
        return False


async def get_pending_first_comment(chat_id: int) -> Optional[Dict[str, Any]]:
    """Получение первого комментария на модерации по ID ГРУППЫ"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            comment_row = await conn.fetchrow(
                '''SELECT chat_id, comment_text, message_id, admin_message_id, user_id, buttons
                FROM await_checks_approvals_first_comment 
                WHERE chat_id = $1''',
                chat_id
            )

            if not comment_row:
                return None


            buttons = json.loads(comment_row['buttons']) if comment_row['buttons'] else []

            return {
                'comment_text': comment_row['comment_text'],
                'buttons': buttons,
                'message_id': comment_row['message_id'],
                'admin_message_id': comment_row['admin_message_id'],
                'user_id': comment_row['user_id']
            }
    except Exception as e:
        logger.error(f"❌ Ошибка в get_pending_first_comment: {e}", exc_info=True)
        return None


async def approve_first_comment(chat_id: int) -> bool:
    """Одобрение первого комментария"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                pending = await get_pending_first_comment(chat_id)
                if not pending:
                    return False

                success = await set_first_comment(
                    chat_id,
                    pending['comment_text'],
                    pending['buttons']
                )
                if not success:
                    return False

                await conn.execute(
                    'DELETE FROM await_checks_approvals_first_comment WHERE chat_id = $1',
                    chat_id
                )

                return True
    except Exception as e:
        logger.error(f"❌ Ошибка в approve_first_comment: {e}", exc_info=True)
        return False


async def reject_first_comment(chat_id: int) -> bool:
    """Отклонение первого комментария"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM await_checks_approvals_first_comment WHERE chat_id = $1',
                chat_id
            )
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка в reject_first_comment: {e}", exc_info=True)
        return False


async def delete_pending_first_comment(chat_id: int) -> bool:
    """Удаление первого комментария из модерации"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM await_checks_approvals_first_comment WHERE chat_id = $1',
                chat_id
            )
            return result.split()[-1] != '0'
    except Exception as e:
        logger.error(e, exc_info=True)
        return False