import logging
from typing import Optional
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# Лимиты для псевдонимов
MAX_PSEUDONYM_LENGTH = 64  # Максимальная длина псевдонима (как указано в обработчике)
MIN_PSEUDONYM_LENGTH = 1  # Минимальная длина псевдонима


@auto_cache_update('users_chats', 'user_id')
async def update_user_pseudonym(chat_id: int, user_id: int, pseudonym: str) -> bool:
    """Обновляет или добавляет псевдоним пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Проверяем, не занят ли уже этот псевдоним другим пользователем
            existing_user = await conn.fetchrow(
                '''
                SELECT user_id FROM users_chats 
                WHERE chat_id = $1 
                AND pseudonym = $2 
                AND user_id != $3
                ''',
                chat_id, pseudonym, user_id
            )

            if existing_user:
                return False  # Псевдоним уже занят

            # Обновляем псевдоним
            await conn.execute('''
                INSERT INTO users_chats (chat_id, user_id, pseudonym) 
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, user_id) 
                DO UPDATE SET pseudonym = EXCLUDED.pseudonym
            ''', chat_id, user_id, pseudonym)
            return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении псевдонима: {e}", exc_info=True)
        raise


async def get_user_pseudonym(chat_id: int, user_id: int) -> Optional[str]:
    """Получает псевдоним пользователя в конкретном чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT pseudonym FROM users_chats WHERE chat_id = $1 AND user_id = $2',
                chat_id, user_id
            )
            return row['pseudonym'] if row and row['pseudonym'] else None
    except Exception as e:
        logger.error(f"Ошибка при получении псевдонима: {e}", exc_info=True)
        return None


async def delete_user_pseudonym(chat_id: int, user_id: int) -> bool:
    """Удаляет псевдоним пользователя в чате (обнуляет поле pseudonym)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Обновляем запись, устанавливая pseudonym = NULL
            result = await conn.execute(
                '''
                UPDATE users_chats 
                SET pseudonym = NULL 
                WHERE chat_id = $1 AND user_id = $2
                ''',
                chat_id, user_id
            )
            # Проверяем, была ли обновлена хотя бы одна запись
            return "UPDATE 1" in result or "UPDATE 0" in result
    except Exception as e:
        logger.error(f"Ошибка при удалении псевдонима: {e}", exc_info=True)
        return False


async def get_chat_pseudonyms(chat_id: int) -> dict:
    """Получает все псевдонимы в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT user_id, pseudonym FROM users_chats WHERE chat_id = $1',
                chat_id
            )
            return {row['user_id']: row['pseudonym'] for row in rows if row['pseudonym']}
    except Exception as e:
        logger.error(f"Ошибка при получении псевдонимов чата: {e}", exc_info=True)
        return {}


def validate_pseudonym(pseudonym: str) -> tuple[bool, str]:
    """Проверяет валидность псевдонима."""
    if not pseudonym or not pseudonym.strip():
        return False, "Псевдоним не может быть пустым"

    pseudonym = pseudonym.strip()

    if len(pseudonym) > MAX_PSEUDONYM_LENGTH:
        return False, f"Слишком длинный псевдоним. Максимум {MAX_PSEUDONYM_LENGTH} символов"

    if len(pseudonym) < MIN_PSEUDONYM_LENGTH:
        return False, f"Слишком короткий псевдоним. Минимум {MIN_PSEUDONYM_LENGTH} символа"

    # Проверка на только пробелы
    if pseudonym.isspace():
        return False, "Псевдоним не может состоять только из пробелов"

    return True, pseudonym


async def is_pseudonym_taken(chat_id: int, pseudonym: str, exclude_user_id: int = None) -> tuple[bool, Optional[int]]:
    """Проверяет, занят ли псевдоним в чате.

    Returns:
        tuple[bool, Optional[int]]: (занят_ли, id_пользователя_владельца)
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            if exclude_user_id:
                row = await conn.fetchrow(
                    '''
                    SELECT user_id FROM users_chats 
                    WHERE chat_id = $1 
                    AND pseudonym = $2 
                    AND user_id != $3
                    ''',
                    chat_id, pseudonym, exclude_user_id
                )
            else:
                row = await conn.fetchrow(
                    '''
                    SELECT user_id FROM users_chats 
                    WHERE chat_id = $1 
                    AND pseudonym = $2
                    ''',
                    chat_id, pseudonym
                )

            if row:
                return True, row['user_id']
            return False, None
    except Exception as e:
        logger.error(f"Ошибка при проверке псевдонима: {e}", exc_info=True)
        return False, None