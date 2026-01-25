
import logging
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.ConnectDataBaseCache import auto_cache_update
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# Лимиты для псевдонимов
MAX_PSEUDONYM_LENGTH = 64  # Максимальная длина псевдонима
MIN_PSEUDONYM_LENGTH = 0  # Минимальная длина псевдонима


@auto_cache_update('users_chats', 'user_id')
async def update_user_pseudonym(chat_id: int, user_id: int, pseudonym: str) -> None:
    """Обновляет или добавляет псевдоним пользователя в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users_chats (chat_id, user_id, pseudonym) 
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id, user_id) 
                DO UPDATE SET pseudonym = EXCLUDED.pseudonym
            ''', chat_id, user_id, pseudonym)
    except Exception as e:
        logger.error(f"Ошибка при обновлении псевдонима: {e}", exc_info=True)
        raise


async def get_user_pseudonym(chat_id: int, user_id: int) -> str:
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