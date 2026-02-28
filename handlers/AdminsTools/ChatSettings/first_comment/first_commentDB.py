import logging
from typing import Optional, Dict, Any, List

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)



async def set_first_comment(channel_id: int, comment_text: str, buttons: List[Dict[str, str]] = None) -> bool:
    """Установка первого комментария для канала"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Сохраняем или обновляем текст комментария
                await conn.execute('''
                    INSERT INTO first_comments (channel_id, comment_text)
                    VALUES ($1, $2)
                    ON CONFLICT (channel_id) 
                    DO UPDATE SET comment_text = $2
                ''', channel_id, comment_text)

                # Удаляем старые кнопки
                await conn.execute(
                    'DELETE FROM first_comment_buttons WHERE channel_id = $1',
                    channel_id
                )

                # Добавляем новые кнопки (максимум 5)
                if buttons:
                    for i, button in enumerate(buttons[:5]):
                        await conn.execute('''
                            INSERT INTO first_comment_buttons (channel_id, button_index, button_text, button_url)
                            VALUES ($1, $2, $3, $4)
                        ''', channel_id, i, button['text'], button['url'])

                return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def get_first_comment(channel_id: int) -> Optional[Dict[str, Any]]:
    """Получение первого комментария для канала"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем текст комментария
            comment_row = await conn.fetchrow(
                'SELECT comment_text FROM first_comments WHERE channel_id = $1',
                channel_id
            )

            if not comment_row:
                return None

            # Получаем кнопки
            button_rows = await conn.fetch(
                'SELECT button_text, button_url FROM first_comment_buttons WHERE channel_id = $1 ORDER BY button_index',
                channel_id
            )

            buttons = [
                {
                    'text': row['button_text'],
                    'url': row['button_url']
                }
                for row in button_rows
            ]

            return {
                'comment_text': comment_row['comment_text'],
                'buttons': buttons
            }
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def delete_first_comment(channel_id: int) -> bool:
    """Удаление первого комментария для канала"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM first_comments WHERE channel_id = $1',
                channel_id
            )
            return result.split()[-1] != '0'
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def add_pending_first_comment(channel_id: int, comment_text: str, buttons: List[Dict[str, str]],
                                    user_message_id: int, user_id: int) -> bool:
    """Добавление первого комментария на модерацию"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Сохраняем в таблицу модерации
                await conn.execute('''
                    INSERT INTO first_comment_moderation (channel_id, comment_text, user_message_id, user_id, status)
                    VALUES ($1, $2, $3, $4, 'pending')
                    ON CONFLICT (channel_id) 
                    DO UPDATE SET 
                        comment_text = $2, 
                        user_message_id = $3, 
                        user_id = $4, 
                        status = 'pending',
                        admin_message_id = NULL,
                        created_at = NOW()
                ''', channel_id, comment_text, user_message_id, user_id)

                # Удаляем старые кнопки на модерации
                await conn.execute(
                    'DELETE FROM first_comment_moderation_buttons WHERE channel_id = $1',
                    channel_id
                )

                # Добавляем новые кнопки на модерацию
                if buttons:
                    for i, button in enumerate(buttons[:5]):
                        await conn.execute('''
                            INSERT INTO first_comment_moderation_buttons (channel_id, button_index, button_text, button_url)
                            VALUES ($1, $2, $3, $4)
                        ''', channel_id, i, button['text'], button['url'])

                return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def get_pending_first_comment(channel_id: int) -> Optional[Dict[str, Any]]:
    """Получение первого комментария на модерации"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем текст комментария на модерации
            comment_row = await conn.fetchrow(
                '''SELECT * FROM first_comment_moderation 
                WHERE channel_id = $1 AND status = 'pending''',
                channel_id
            )

            if not comment_row:
                return None

            # Получаем кнопки на модерации
            button_rows = await conn.fetch(
                '''SELECT button_text, button_url 
                FROM first_comment_moderation_buttons 
                WHERE channel_id = $1 ORDER BY button_index''',
                channel_id
            )

            buttons = [
                {
                    'text': row['button_text'],
                    'url': row['button_url']
                }
                for row in button_rows
            ]

            return {
                'comment_text': comment_row['comment_text'],
                'buttons': buttons,
                'user_message_id': comment_row['user_message_id'],
                'admin_message_id': comment_row['admin_message_id'],
                'user_id': comment_row['user_id']
            }
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def update_pending_first_comment_admin_message(channel_id: int, admin_message_id: int) -> bool:
    """Обновление ID сообщения админа для модерации"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''UPDATE first_comment_moderation 
                SET admin_message_id = $1 
                WHERE channel_id = $2 AND status = 'pending''',
                admin_message_id, channel_id
            )
            return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def approve_first_comment(channel_id: int) -> bool:
    """Одобрение первого комментария"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Получаем данные из модерации
                pending = await get_pending_first_comment(channel_id)
                if not pending:
                    return False

                # Переносим в основную таблицу
                success = await set_first_comment(channel_id, pending['comment_text'], pending['buttons'])
                if not success:
                    return False

                # Обновляем статус в модерации
                await conn.execute(
                    '''UPDATE first_comment_moderation 
                    SET status = 'approved' 
                    WHERE channel_id = $1''',
                    channel_id
                )

                return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def reject_first_comment(channel_id: int) -> bool:
    """Отклонение первого комментария"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                '''UPDATE first_comment_moderation 
                SET status = 'rejected' 
                WHERE channel_id = $1''',
                channel_id
            )
            return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def delete_pending_first_comment(channel_id: int) -> bool:
    """Удаление первого комментария из модерации"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM first_comment_moderation WHERE channel_id = $1',
                channel_id
            )
            return result.split()[-1] != '0'
    except Exception as e:
        logger.error(e, exc_info=True)
        return False