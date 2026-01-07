import logging

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

async def add_note(chat_id: int, notes_name: str, notes_text: str) -> dict:
    """Добавление новой заметки"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Проверяем, существует ли уже заметка с таким названием в этом чате
            existing_note = await conn.fetchrow(
                'SELECT notes_name FROM notes WHERE chat_id = $1 AND notes_name = $2',
                chat_id, notes_name
            )

            if existing_note:
                return {'success': False, 'error': 'Заметка с таким названием уже существует'}

            # Получаем следующий ID для этого чата
            result = await conn.fetchval(
                'SELECT COALESCE(MAX(notes_id), 0) + 1 FROM notes WHERE chat_id = $1',
                chat_id
            )
            next_id = result or 1

            # Добавляем заметку
            await conn.execute(
                'INSERT INTO notes (notes_id, chat_id, notes_name, notes_text) VALUES ($1, $2, $3, $4)',
                next_id, chat_id, notes_name, notes_text
            )

            return {'success': True, 'notes_id': next_id}
    except Exception as e:
        logger.error(e, exc_info=True)
        return {'success': False, 'error': str(e)}


async def delete_note(chat_id: int, identifier: str) -> bool:
    """Удаление заметки по ID или названию"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Пробуем удалить по ID (если identifier число)
            if identifier.isdigit():
                result = await conn.execute(
                    'DELETE FROM notes WHERE chat_id = $1 AND notes_id = $2',
                    chat_id, int(identifier)
                )
                if result.split()[-1] != '0':
                    return True

            # Удаляем по названию
            result = await conn.execute(
                'DELETE FROM notes WHERE chat_id = $1 AND notes_name = $2',
                chat_id, identifier
            )
            return result.split()[-1] != '0'
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def get_note(chat_id: int, identifier: str) -> dict:
    """Получение заметки по ID или названию"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Ищем по ID
            if identifier.isdigit():
                row = await conn.fetchrow(
                    'SELECT * FROM notes WHERE chat_id = $1 AND notes_id = $2',
                    chat_id, int(identifier)
                )
            else:
                # Ищем по названию
                row = await conn.fetchrow(
                    'SELECT * FROM notes WHERE chat_id = $1 AND notes_name = $2',
                    chat_id, identifier
                )

            if row:
                return {
                    'notes_id': row['notes_id'],
                    'notes_name': row['notes_name'],
                    'notes_text': row['notes_text'],
                    'chat_id': row['chat_id']
                }
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_all_notes(chat_id: int) -> list:
    """Получение всех заметок чата"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT * FROM notes WHERE chat_id = $1 ORDER BY notes_id',
                chat_id
            )
            return [
                {
                    'notes_id': row['notes_id'],
                    'notes_name': row['notes_name'],
                    'notes_text': row['notes_text']
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def search_notes(chat_id: int, search_term: str) -> list:
    """Поиск заметок по названию или тексту"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''SELECT * FROM notes 
                WHERE chat_id = $1 AND (notes_name ILIKE $2 OR notes_text ILIKE $2)
                ORDER BY notes_id''',
                chat_id, f'%{search_term}%'
            )
            return [
                {
                    'notes_id': row['notes_id'],
                    'notes_name': row['notes_name'],
                    'notes_text': row['notes_text']
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_note_by_name(chat_id: int, notes_name: str) -> dict:
    """Получение заметки по названию"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM notes WHERE chat_id = $1 AND notes_name = $2',
                chat_id, notes_name
            )
            if row:
                return {
                    'notes_id': row['notes_id'],
                    'notes_name': row['notes_name'],
                    'notes_text': row['notes_text'],
                    'chat_id': row['chat_id']
                }
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None