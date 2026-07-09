import logging
from typing import List, Dict, Any, Optional

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def add_dk_for_chats(ChatId: int, CommandId: int, AccessLevel: int) -> None:
    """Добавляет или обновляет уровень доступа команды в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO commands_chats (ChatId, CommandId, AccessLevel)
                VALUES ($1, $2, $3)
                ON CONFLICT (ChatId, CommandId) DO UPDATE SET AccessLevel = EXCLUDED.AccessLevel
            ''', ChatId, CommandId, AccessLevel)
    except Exception as e:
        logger.error(e, exc_info=True)


async def update_dk_for_chats(ChatId: int, CommandId: int, rang: int) -> None:
    """Обновляет уровень доступа команды в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE commands_chats 
                SET AccessLevel = $1 
                WHERE CommandId = $2 AND ChatId = $3
            ''', rang, CommandId, ChatId)
    except Exception as e:
        logger.error(e, exc_info=True)


async def check_command_chat(CommandId: int, ChatId: int) -> bool:
    """Проверяет, настроена ли команда в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM commands_chats WHERE CommandId = $1 AND ChatId = $2',
                CommandId, ChatId
            )
            return row is not None
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def check_command_for_bd_int(command_id: int) -> Optional[int]:
    """Проверяет существование команды по ID."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT CommandId FROM commands WHERE CommandId = $1',
                command_id
            )
            return row['commandid'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def check_command_for_bd_str(command_name: str) -> Optional[int]:
    """Проверяет существование команды по имени (регистронезависимо)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT CommandId FROM commands WHERE LOWER(CommandName) = LOWER($1)',
                command_name
            )
            return row['commandid'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_command_info(command_id: Optional[int] = None, command_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Получает информацию о команде по ID или имени (регистронезависимо)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            if command_id is not None:
                row = await conn.fetchrow(
                    'SELECT CommandId, CommandName, AccessLevel, UnderSectionId FROM commands WHERE CommandId = $1',
                    command_id
                )
            elif command_name is not None:
                row = await conn.fetchrow(
                    'SELECT CommandId, CommandName, AccessLevel, UnderSectionId FROM commands WHERE LOWER(CommandName) = LOWER($1)',
                    command_name
                )
            else:
                return None

            if row:
                return {
                    'CommandId': row['commandid'],
                    'CommandName': row['commandname'],
                    'AccessLevel': row['accesslevel'],
                    'UnderSectionId': row['undersectionid']
                }
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_commands_by_section(section_id: int) -> List[Dict[str, Any]]:
    """Получает все команды раздела."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT c.CommandId, c.CommandName, c.AccessLevel, c.UnderSectionId
                FROM commands c
                JOIN under_sections us ON c.UnderSectionId = us.UnderSectionId
                WHERE us.SectionId = $1
            ''', section_id)
            return [
                {
                    'CommandId': row['commandid'],
                    'CommandName': row['commandname'],
                    'AccessLevel': row['accesslevel'],
                    'UnderSectionId': row['undersectionid']
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_section_info(section_id: Optional[int] = None, section_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Получает информацию о разделе (регистронезависимо)."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            if section_id is not None:
                row = await conn.fetchrow(
                    'SELECT SectionId, SectionName FROM sections WHERE SectionId = $1',
                    section_id
                )
            elif section_name is not None:
                row = await conn.fetchrow(
                    'SELECT SectionId, SectionName FROM sections WHERE LOWER(SectionName) = LOWER($1)',
                    section_name
                )
            else:
                return None

            if row:
                return {
                    'SectionId': row['sectionid'],
                    'SectionName': row['sectionname']
                }
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def check_section_chat(section_id: int, chat_id: int) -> Optional[bool]:
    """Проверяет состояние раздела в чате."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT IsActive FROM chat_sections WHERE SectionId = $1 AND ChatId = $2',
                section_id, chat_id
            )
            return row['isactive'] if row else None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def add_section_for_chat(chat_id: int, section_id: int, is_active: bool) -> None:
    """Добавляет настройку раздела для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO chat_sections (ChatId, SectionId, IsActive)
                VALUES ($1, $2, $3)
                ON CONFLICT (ChatId, SectionId) DO UPDATE SET IsActive = EXCLUDED.IsActive
            ''', chat_id, section_id, is_active)
    except Exception as e:
        logger.error(e, exc_info=True)


async def update_section_for_chat(chat_id: int, section_id: int, is_active: bool) -> None:
    """Обновляет настройку раздела для чата."""
    await add_section_for_chat(chat_id, section_id, is_active)


async def get_under_section_info(
    under_section_name: Optional[str] = None,
    section_name: Optional[str] = None,
    under_section_id: Optional[int] = None,
    section_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Получает информацию о подразделе."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            if under_section_id is not None:
                query = '''
                    SELECT us.UnderSectionId, us.UnderName, us.SectionId, s.SectionName 
                    FROM under_sections us
                    JOIN sections s ON us.SectionId = s.SectionId
                    WHERE us.UnderSectionId = $1
                '''
                params = [under_section_id]
                if section_id is not None:
                    query += ' AND us.SectionId = $2'
                    params.append(section_id)
                row = await conn.fetchrow(query, *params)
            else:
                if under_section_name and section_name:
                    row = await conn.fetchrow('''
                        SELECT us.UnderSectionId, us.UnderName, us.SectionId, s.SectionName 
                        FROM under_sections us
                        JOIN sections s ON us.SectionId = s.SectionId
                        WHERE LOWER(us.UnderName) = LOWER($1) AND LOWER(s.SectionName) = LOWER($2)
                    ''', under_section_name, section_name)
                elif under_section_name:
                    row = await conn.fetchrow('''
                        SELECT us.UnderSectionId, us.UnderName, us.SectionId, s.SectionName 
                        FROM under_sections us
                        JOIN sections s ON us.SectionId = s.SectionId
                        WHERE LOWER(us.UnderName) = LOWER($1)
                    ''', under_section_name)
                else:
                    return None

            if row:
                return {
                    'UnderSectionId': row['undersectionid'],
                    'UnderName': row['undername'],
                    'SectionId': row['sectionid'],
                    'SectionName': row['sectionname']
                }
            return None
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


async def get_commands_by_under_section(under_section_id: int) -> List[Dict[str, Any]]:
    """Получает все команды подраздела."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT CommandId, CommandName, AccessLevel, UnderSectionId
                FROM commands 
                WHERE UnderSectionId = $1
            ''', under_section_id)
            return [
                {
                    'CommandId': row['commandid'],
                    'CommandName': row['commandname'],
                    'AccessLevel': row['accesslevel'],
                    'UnderSectionId': row['undersectionid']
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_all_sections() -> List[Dict[str, Any]]:
    """Получает все разделы."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT SectionId, SectionName FROM sections ORDER BY SectionId'
            )
            return [
                {
                    'SectionId': row['sectionid'],
                    'SectionName': row['sectionname']
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_under_sections_by_section(section_id: int) -> List[Dict[str, Any]]:
    """Получает подразделы по ID раздела."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT UnderSectionId, UnderName FROM under_sections WHERE SectionId = $1 ORDER BY UnderSectionId',
                section_id
            )
            return [
                {
                    'UnderSectionId': row['undersectionid'],
                    'UnderName': row['undername']
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_command_access_level(chat_id: int, command_id: int) -> int:
    """Получает уровень доступа команды с приоритетом для чата."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT AccessLevel FROM commands_chats WHERE CommandId = $1 AND ChatId = $2',
                command_id, chat_id
            )
            if row:
                return row['accesslevel']

        command_info = await get_command_info(command_id=command_id)
        if command_info:
            return command_info['AccessLevel']

        return 6
    except Exception as e:
        logger.error(e, exc_info=True)
        return 6